"""Консьюмер доменных событий из Redis Streams (ADR-0004).

Гарантии:
- at-least-once со стороны Redis (consumer group, XACK только после фиксации транзакции);
- **ровно один эффект** на стороне сервиса: отметка в `processed_event` пишется в той же
  транзакции, что и изменения обработчика, поэтому повторная доставка ничего не меняет;
- сообщение, которое не удаётся обработать `max_attempts` раз, уходит в `dlq:<stream>` и
  подтверждается, чтобы не блокировать поток (разбор — вручную по логу и DLQ).

Порядок событий внутри одного stream сохраняется, если у группы один экземпляр консьюмера —
так и запускается в compose (проекции чувствительны к порядку).
"""

import asyncio
import contextlib
import json
import logging
import socket
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dutyflow_common.heartbeat import beat
from dutyflow_common.outbox import ProcessedEvent

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Event:
    id: uuid.UUID
    type: str
    aggregate_id: uuid.UUID
    payload: dict[str, Any]

    @classmethod
    def from_fields(cls, fields: Mapping[bytes | str, bytes | str]) -> "Event":
        f = {_s(k): _s(v) for k, v in fields.items()}
        return cls(
            id=uuid.UUID(f["event_id"]),
            type=f["event_type"],
            aggregate_id=uuid.UUID(f["aggregate_id"]),
            payload=json.loads(f["payload"]),
        )


def _s(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


type Handler = Callable[[AsyncSession, Event], Awaitable[None]]


class EventConsumer:
    """`handlers`: {stream: обработчик}. Обработчик сам решает, какие `event.type` ему нужны."""

    def __init__(
        self,
        group: str,
        sessionmaker: async_sessionmaker[AsyncSession],
        redis: Redis,
        handlers: Mapping[str, Handler],
        *,
        consumer_name: str | None = None,
        max_attempts: int = 5,
        batch: int = 100,
    ) -> None:
        self.group = group
        self.sessionmaker = sessionmaker
        self.redis = redis
        self.handlers = dict(handlers)
        self.consumer = consumer_name or socket.gethostname()
        self.max_attempts = max_attempts
        self.batch = batch
        self._failures: dict[str, int] = {}

    async def ensure_groups(self) -> None:
        for stream in self.handlers:
            try:
                # id=0: новая группа читает всю сохранённую историю stream
                await self.redis.xgroup_create(stream, self.group, id="0", mkstream=True)
            except ResponseError as exc:
                if "BUSYGROUP" not in str(exc):
                    raise

    async def process_batch(
        self, stream: str, messages: list[tuple[str, Mapping[Any, Any]]]
    ) -> tuple[int, bool]:
        """Обрабатывает пачку сообщений одного stream одной транзакцией: у каждого события
        своя точка сохранения, фиксация и XACK — один раз на пачку (фаза 7d: транзакция на
        событие упиралась в fsync PostgreSQL, ~190 событий/с на консьюмер).

        Возвращает (сколько подтверждено, дошли ли до конца пачки). На первом сбое
        обработчика пачка обрывается: успешные до него фиксируются, остальные остаются
        неподтверждёнными и будут прочитаны снова — порядок сохраняется."""
        done: list[str] = []
        confirmed = 0
        failed: tuple[str, Mapping[Any, Any], Event, BaseException] | None = None
        try:
            async with self.sessionmaker() as session, session.begin():
                for message_id, fields in messages:
                    if not fields:  # запись удалена из stream (обрезка по MAXLEN до фазы 7d)
                        done.append(message_id)
                        continue
                    try:
                        event = Event.from_fields(fields)
                    except (KeyError, ValueError) as exc:
                        log.error("Некорректное сообщение %s в %s: %s", message_id, stream, exc)
                        await self._dead_letter(stream, message_id, fields, "malformed")
                        confirmed += 1
                        continue
                    try:
                        async with session.begin_nested():
                            inserted = await session.execute(
                                insert(ProcessedEvent)
                                .values(consumer=self.group, event_id=event.id)
                                .on_conflict_do_nothing()
                                .returning(ProcessedEvent.event_id)
                            )
                            if inserted.first() is not None:
                                await self.handlers[stream](session, event)
                    except Exception as exc:
                        failed = (message_id, fields, event, exc)
                        break
                    done.append(message_id)
                    confirmed += 1
        except Exception:
            log.exception("Не удалось зафиксировать пачку событий %s, повтор", stream)
            return 0, False
        if done:
            await self.redis.xack(stream, self.group, *done)
            for message_id in done:
                self._failures.pop(message_id, None)
        if failed is None:
            return confirmed, True
        message_id, fields, event, error = failed
        attempts = self._failures.get(message_id, 0) + 1
        self._failures[message_id] = attempts
        log.error(
            "Ошибка обработки %s (%s), попытка %d",
            event.type,
            message_id,
            attempts,
            exc_info=error,
        )
        if attempts >= self.max_attempts:
            await self._dead_letter(stream, message_id, fields, "max_attempts")
            confirmed += 1
        return confirmed, False

    async def _dead_letter(
        self, stream: str, message_id: str, fields: Mapping[Any, Any], reason: str
    ) -> None:
        payload: dict[Any, Any] = {_s(k): _s(v) for k, v in fields.items()}
        payload.update({"dlq_reason": reason, "dlq_group": self.group, "source_id": message_id})
        await self.redis.xadd(f"dlq:{stream}", payload, maxlen=10_000, approximate=True)
        await self.redis.xack(stream, self.group, message_id)
        self._failures.pop(message_id, None)

    async def run_once(self, block_ms: int = 1000) -> int:
        """Сначала свои неподтверждённые сообщения (после сбоя), затем новые."""
        handled = 0
        for start in ("0", ">"):
            response = await self.redis.xreadgroup(
                self.group,
                self.consumer,
                dict.fromkeys(self.handlers, start),
                count=self.batch,
                block=None if start == "0" else block_ms,
            )
            batches = cast(list[tuple[Any, list[tuple[Any, dict[Any, Any]]]]], response or [])
            for raw_stream, messages in batches:
                confirmed, complete = await self.process_batch(
                    _s(raw_stream), [(_s(i), f) for i, f in messages]
                )
                handled += confirmed
                if not complete:
                    return handled  # сохраняем порядок: повторим с этого места
        return handled

    async def run(self, stop: asyncio.Event) -> None:
        await self.ensure_groups()
        log.info("Консьюмер %s/%s слушает %s", self.group, self.consumer, list(self.handlers))
        while not stop.is_set():
            try:
                await self.run_once()
                beat()
            except Exception:
                log.exception("Сбой чтения событий, повтор через 5 с")
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=5)
