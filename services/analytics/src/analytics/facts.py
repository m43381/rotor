"""Обработчики событий scheduling для read-model: `assignment.*` и `schedule.*`.

Обработчики идемпотентны: создание — upsert по id назначения, снятие — удаление по id,
смена статуса графика — обновление всех его фактов. Повторная доставка ничего не меняет
(и так отсекается по `processed_event`).
"""

import datetime as dt
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.models import DutyFact
from dutyflow_common.events import Event

COLUMNS = (
    "person_id",
    "person_name",
    "unit_id",
    "schedule_id",
    "schedule_status",
    "duty_type_id",
    "duty_role_id",
    "duty_type_name",
    "role_name",
    "date",
    "start_at",
    "end_at",
    "occupied_days",
    "load",
    "holiday",
    "source",
)


def row(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "assignment_id": uuid.UUID(str(payload["assignment_id"])),
        "person_id": uuid.UUID(str(payload["person_id"])),
        "person_name": str(payload["person_name"]),
        "unit_id": uuid.UUID(str(payload["unit_id"])),
        "schedule_id": uuid.UUID(str(payload["schedule_id"])),
        "schedule_status": str(payload["schedule_status"]),
        "duty_type_id": uuid.UUID(str(payload["duty_type_id"])),
        "duty_role_id": uuid.UUID(str(payload["duty_role_id"])),
        # Названия есть в событиях с фазы 8
        "duty_type_name": payload.get("duty_type_name"),
        "role_name": payload.get("role_name"),
        "date": dt.date.fromisoformat(str(payload["date"])),
        "start_at": dt.datetime.fromisoformat(str(payload["start_at"])),
        "end_at": dt.datetime.fromisoformat(str(payload["end_at"])),
        "occupied_days": int(payload["occupied_days"]),
        "load": float(payload["load"]),
        "holiday": bool(payload["holiday"]),
        "source": str(payload["source"]),
    }


async def upsert_facts(session: AsyncSession, payloads: Iterable[dict[str, Any]]) -> int:
    rows = [row(p) for p in payloads]
    for i in range(0, len(rows), 1_000):  # лимит параметров asyncpg
        stmt = insert(DutyFact).values(rows[i : i + 1_000])
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[DutyFact.assignment_id],
                set_={c: stmt.excluded[c] for c in COLUMNS},
            )
        )
    return len(rows)


async def handle_assignment_event(session: AsyncSession, event: Event) -> None:
    if "occupied_days" not in event.payload:
        # Событие старого формата (до фазы 6c) — факт восстановит перестроение read-model
        return
    if event.type == "assignment.created":
        await upsert_facts(session, [event.payload])
    elif event.type == "assignment.removed":
        await session.execute(
            delete(DutyFact).where(
                DutyFact.assignment_id == uuid.UUID(str(event.payload["assignment_id"]))
            )
        )


STATUSES = {"schedule.published": "published", "schedule.archived": "archived"}


async def handle_schedule_event(session: AsyncSession, event: Event) -> None:
    status = STATUSES.get(event.type)
    if status is None:
        return
    await session.execute(
        update(DutyFact)
        .where(DutyFact.schedule_id == uuid.UUID(str(event.payload["schedule_id"])))
        .values(schedule_status=status)
    )
