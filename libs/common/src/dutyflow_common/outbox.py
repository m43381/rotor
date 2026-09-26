"""Transactional outbox (ADR-0004): событие пишется в ту же транзакцию, что и изменение домена,
а отдельный релей публикует его в Redis Streams."""

import json
import uuid
from datetime import datetime
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import DateTime, Index, String, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from dutyflow_common.db import Base
from dutyflow_common.ids import uuid7


class OutboxEvent(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        Index("ix_outbox_unpublished", "id", postgresql_where=text("published_at IS NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    event_type: Mapped[str] = mapped_column(String(100))
    aggregate_type: Mapped[str] = mapped_column(String(50))
    aggregate_id: Mapped[uuid.UUID]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProcessedEvent(Base):
    """Идемпотентность консьюмеров: событие с тем же id повторно не обрабатывается."""

    __tablename__ = "processed_event"

    consumer: Mapped[str] = mapped_column(String(100), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


def add_event(
    session: AsyncSession,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
) -> OutboxEvent:
    event = OutboxEvent(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=jsonable_encoder(payload),
    )
    session.add(event)
    return event


def stream_name(event_type: str) -> str:
    """Один stream на агрегат: `unit.created` → `events:unit`."""
    return "events:" + event_type.split(".", 1)[0]


async def relay_once(
    sessionmaker: async_sessionmaker[AsyncSession], redis: Any, *, batch: int = 100
) -> int:
    """Публикует пачку неотправленных событий. `FOR UPDATE SKIP LOCKED` позволяет
    безопасно запускать несколько релеев. Возвращает число опубликованных событий."""
    async with sessionmaker() as session, session.begin():
        rows = (
            await session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.id)
                .limit(batch)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for ev in rows:
            await redis.xadd(
                stream_name(ev.event_type),
                {
                    "event_id": str(ev.id),
                    "event_type": ev.event_type,
                    "aggregate_id": str(ev.aggregate_id),
                    "payload": json.dumps(ev.payload, ensure_ascii=False),
                },
                maxlen=100_000,
                approximate=True,
            )
            ev.published_at = func.now()
        return len(rows)
