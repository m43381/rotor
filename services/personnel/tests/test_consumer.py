"""Консьюмер событий на настоящем Redis: доставка, идемпотентность, DLQ, пересинхронизация."""

import json
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from conftest import Org, unit_payload
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dutyflow_common.events import EventConsumer
from dutyflow_common.ids import uuid7
from dutyflow_common.internal import InternalClient
from dutyflow_common.projections import (
    RankProjection,
    UnitProjection,
    handle_rank_event,
    handle_unit_event,
)
from dutyflow_common.sync import resync_org


@pytest.fixture
async def redis(redis_url: str) -> AsyncIterator[Redis]:
    client = Redis.from_url(redis_url)
    await client.flushdb()
    yield client
    await client.aclose()


def consumer(
    sessionmaker: async_sessionmaker[AsyncSession], redis: Redis, max_attempts: int = 5
) -> EventConsumer:
    return EventConsumer(
        "personnel-test",
        sessionmaker,
        redis,
        {"events:unit": handle_unit_event, "events:rank": handle_rank_event},
        consumer_name="t1",
        max_attempts=max_attempts,
    )


async def publish(
    redis: Redis,
    event_type: str,
    aggregate: uuid.UUID,
    payload: dict[str, object],
    event_id: uuid.UUID | None = None,
) -> None:
    """Так публикует релей outbox (dutyflow_common.outbox.relay_once)."""
    await redis.xadd(
        "events:" + event_type.split(".")[0],
        {
            "event_id": str(event_id or uuid7()),
            "event_type": event_type,
            "aggregate_id": str(aggregate),
            "payload": json.dumps(payload),
        },
    )


async def unit_name(sessionmaker: async_sessionmaker[AsyncSession], unit_id: uuid.UUID) -> str:
    async with sessionmaker() as s:
        return str(
            await s.scalar(select(UnitProjection.name).where(UnitProjection.unit_id == unit_id))
        )


async def test_delivery_and_idempotency(
    sessionmaker: async_sessionmaker[AsyncSession], redis: Redis, org: Org
) -> None:
    c = consumer(sessionmaker, redis)
    await c.ensure_groups()
    new_unit = uuid7()
    event_id = uuid7()
    await publish(
        redis,
        "unit.created",
        new_unit,
        unit_payload(new_unit, org.fac_a, "1.2.9", "Новый курс"),
        event_id,
    )
    # Та же доставка повторно (at-least-once) — эффекта быть не должно
    await publish(
        redis,
        "unit.updated",
        new_unit,
        unit_payload(new_unit, org.fac_a, "1.2.9", "Переименованный", version=2),
    )
    await publish(
        redis,
        "unit.created",
        new_unit,
        unit_payload(new_unit, org.fac_a, "1.2.9", "Новый курс"),
        event_id,
    )

    assert await c.run_once(block_ms=100) == 3
    assert await unit_name(sessionmaker, new_unit) == "Переименованный"
    pending = await redis.xpending("events:unit", "personnel-test")
    assert pending["pending"] == 0


async def test_malformed_and_failing_go_to_dlq(
    sessionmaker: async_sessionmaker[AsyncSession], redis: Redis, org: Org
) -> None:
    c = consumer(sessionmaker, redis, max_attempts=2)
    await c.ensure_groups()
    await redis.xadd("events:unit", {"garbage": "1"})
    # Событие, на котором обработчик падает (нет обязательного поля path)
    await publish(redis, "unit.created", uuid7(), {"unit_id": str(uuid7()), "name": "x"})
    ok_unit = uuid7()
    await publish(redis, "unit.created", ok_unit, unit_payload(ok_unit, org.root, "1.77", "После"))

    for _ in range(4):
        await c.run_once(block_ms=100)
    assert await redis.xlen("dlq:events:unit") == 2
    # Порядок сохранён: событие после «плохого» обработано только после его ухода в DLQ
    assert await unit_name(sessionmaker, ok_unit) == "После"


async def test_rank_event(sessionmaker: async_sessionmaker[AsyncSession], redis: Redis) -> None:
    c = consumer(sessionmaker, redis)
    await c.ensure_groups()
    rid = uuid7()
    await publish(redis, "rank.changed", rid, {"name": "Капитан", "order": 90, "is_active": True})
    await c.run_once(block_ms=100)
    async with sessionmaker() as s:
        assert (await s.get(RankProjection, rid)) is not None


async def test_resync_from_org(sessionmaker: async_sessionmaker[AsyncSession], org: Org) -> None:
    """Пустая проекция заполняется из batch-API org; непустая — не трогается."""
    extra = uuid7()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/internal/units/batch":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(extra),
                        "parent_id": str(org.root),
                        "path": "1.50",
                        "name": "Из org",
                        "short_name": None,
                        "is_active": True,
                        "version": 1,
                        "unit_type_id": str(uuid7()),
                    }
                ],
            )
        return httpx.Response(200, json=[])

    client = InternalClient("http://org", "t", transport=httpx.MockTransport(handler))
    assert await resync_org(sessionmaker, client, only_if_empty=True) is False
    assert await resync_org(sessionmaker, client, only_if_empty=False) is True
    assert await unit_name(sessionmaker, extra) == "Из org"
    await client.aclose()
