"""Факты нарядов для аналитики (фаза 6c): событие на каждое назначение и выгрузка пачками.

Событие `assignment.created` / `assignment.removed` несёт всё, что нужно read-model
`analytics` без обращений назад: человек и его краткое имя, подразделение-исполнитель,
график и его статус, наряд и роль, дата и интервал, занятые сутки, нагрузка
(нарядо-сутки × вес наряда), выходной или праздник по производственному календарю,
источник (вручную / автоматически). Поля только добавлялись к прежнему формату.

Все пути, которые создают или удаляют назначения, публикуют события через `emit_*` —
в том числе массовые: пересборка автораспределением и делегирование со снятием людей.
Данные собираются одним запросом на пачку назначений.
"""

import datetime as dt
import uuid
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from dutyflow_common.calendar import CalendarProjection, day_kind
from dutyflow_common.outbox import add_event
from scheduling.models import Assignment, DayPlan, DutyType, Schedule


def occupied_count(days: Range[dt.date]) -> int:
    if days.lower is None or days.upper is None:
        return 1
    span = (days.upper - days.lower).days
    return span + (1 if days.upper_inc else 0) - (0 if days.lower_inc else 1)


def _query() -> Select[Assignment, DayPlan, DutyType, Schedule]:
    return (
        select(Assignment, DayPlan, DutyType, Schedule)
        .join(DayPlan, DayPlan.id == Assignment.day_plan_id)
        .join(DutyType, DutyType.id == DayPlan.duty_type_id)
        .join(Schedule, Schedule.id == DayPlan.schedule_id)
    )


async def _kinds(session: AsyncSession, dates: Iterable[dt.date]) -> dict[dt.date, str]:
    ds = set(dates)
    if not ds:
        return {}
    return dict(
        (
            await session.execute(
                select(CalendarProjection.date, CalendarProjection.kind).where(
                    CalendarProjection.date.in_(ds)
                )
            )
        ).all()
    )


def payload(
    a: Assignment,
    cell: DayPlan,
    duty_type: DutyType,
    schedule: Schedule,
    kinds: dict[dt.date, str],
) -> dict[str, Any]:
    occupied = occupied_count(a.occupied_days)
    return {
        "assignment_id": a.id,
        "day_plan_id": cell.id,
        "schedule_id": schedule.id,
        "schedule_status": schedule.status,
        "person_id": a.person_id,
        "person_name": a.person_name,
        # Подразделение, которое закрывает ячейку своими людьми (подразделение графика)
        "unit_id": schedule.unit_id,
        "duty_type_id": cell.duty_type_id,
        "duty_role_id": cell.duty_role_id,
        "date": cell.date,
        "start_at": a.start_at,
        "end_at": a.end_at,
        "occupied_days": occupied,
        "load": round(occupied * float(duty_type.load_weight), 4),
        "holiday": day_kind(cell.date, kinds) in ("weekend", "holiday"),
        "source": a.source,
    }


async def payloads(
    session: AsyncSession, assignments: Sequence[Assignment]
) -> list[dict[str, Any]]:
    """Данные событий для назначений (уже в сессии: после flush или загруженных)."""
    if not assignments:
        return []
    cells = {
        c.id: (c, t, s)
        for c, t, s in await session.execute(
            select(DayPlan, DutyType, Schedule)
            .join(DutyType, DutyType.id == DayPlan.duty_type_id)
            .join(Schedule, Schedule.id == DayPlan.schedule_id)
            .where(DayPlan.id.in_({a.day_plan_id for a in assignments}))
        )
    }
    kinds = await _kinds(session, (c.date for c, _, _ in cells.values()))
    return [payload(a, *cells[a.day_plan_id], kinds) for a in assignments]


async def emit_created(session: AsyncSession, assignments: Sequence[Assignment]) -> None:
    for a, data in zip(assignments, await payloads(session, assignments), strict=True):
        add_event(session, "assignment.created", "assignment", a.id, data)


async def emit_removed(session: AsyncSession, assignments: Sequence[Assignment]) -> None:
    """Вызывается до удаления: данные ещё в БД."""
    for a, data in zip(assignments, await payloads(session, assignments), strict=True):
        add_event(session, "assignment.removed", "assignment", a.id, data)


async def export(
    session: AsyncSession, *, after: uuid.UUID | None, limit: int
) -> list[dict[str, Any]]:
    """Все назначения по возрастанию id — пачками, для перестроения read-model."""
    stmt = _query().order_by(Assignment.id).limit(limit)
    if after is not None:
        stmt = stmt.where(Assignment.id > after)
    rows = (await session.execute(stmt)).all()
    kinds = await _kinds(session, (r.DayPlan.date for r in rows))
    return [payload(r.Assignment, r.DayPlan, r.DutyType, r.Schedule, kinds) for r in rows]
