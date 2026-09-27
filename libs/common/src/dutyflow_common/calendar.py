"""Проекция производственного календаря org (ADR-0011) и тип дня для таблиц и лимитов.

Хранятся только исключения (`holiday`, `workday` — рабочий перенос, `preholiday`); обычные
выходные вычисляются по дню недели, как в org (`docs/data-model.md` §3).
Отдельный модуль, а не `projections`: таблица нужна не всем сервисам.
"""

import datetime as dt
from collections.abc import Sequence
from typing import Any, Literal

from sqlalchemy import Date, String, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from dutyflow_common.db import Base
from dutyflow_common.events import Event
from dutyflow_common.internal import InternalClient

type DayKind = Literal["workday", "weekend", "holiday", "preholiday"]


class CalendarProjection(Base):
    __tablename__ = "calendar_projection"

    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str | None] = mapped_column(String(200))


def day_kind(day: dt.date, exceptions: dict[dt.date, str]) -> DayKind:
    """Тип дня: исключение календаря важнее дня недели."""
    kind = exceptions.get(day)
    if kind == "holiday":
        return "holiday"
    if kind == "workday":
        return "workday"
    if day.weekday() >= 5:
        return "weekend"
    if kind == "preholiday":
        return "preholiday"
    return "workday"


async def upsert_calendar(session: AsyncSession, days: Sequence[dict[str, Any]]) -> None:
    if not days:
        return
    rows = [
        {"date": dt.date.fromisoformat(str(d["date"])), "kind": d["kind"], "name": d.get("name")}
        for d in days
    ]
    stmt = insert(CalendarProjection).values(rows)
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[CalendarProjection.date],
            set_={"kind": stmt.excluded.kind, "name": stmt.excluded.name},
        )
    )


async def handle_calendar_event(session: AsyncSession, event: Event) -> None:
    if event.type != "calendar.changed":
        return
    if event.payload.get("deleted"):
        day = dt.date.fromisoformat(str(event.payload["date"]))
        await session.execute(delete(CalendarProjection).where(CalendarProjection.date == day))
    else:
        await upsert_calendar(session, [event.payload])


async def resync_calendar(
    sessionmaker: async_sessionmaker[AsyncSession], org: InternalClient
) -> None:
    """Полная загрузка календаря из org (при первом запуске консьюмера)."""
    days = await org.post("/internal/calendar", {})
    async with sessionmaker() as session, session.begin():
        await session.execute(delete(CalendarProjection))
        await upsert_calendar(session, days)
