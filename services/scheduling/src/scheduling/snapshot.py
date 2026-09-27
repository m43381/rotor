"""Снимок задачи распределения для подразделения на месяц (фаза 3c, ADR-0013).

Самодостаточный JSON со словарями и индексами: движок (фаза 4) и бенчмарки работают с ним
без сервисов и БД. Сборка — один batch-запрос в personnel и по одному запросу на раздел в
свою БД. Порядок элементов фиксирован, поэтому `hash` одинаков для одинакового входа.
"""

import datetime as dt
import hashlib
import uuid
from typing import Any
from zoneinfo import ZoneInfo

from pydantic_core import to_json
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from dutyflow_common.calendar import CalendarProjection, day_kind
from dutyflow_common.db import in_array
from dutyflow_common.ltree import is_ancestor_or_self, is_descendant_or_self
from dutyflow_common.projections import UnitProjection
from scheduling.checks import LimitRule, resolve_limit
from scheduling.models import Assignment, DayPlan, DutyLimit, DutyRole, DutyType, Schedule
from scheduling.people import PeopleLoader
from scheduling.schedules import month_days

SNAPSHOT_VERSION = 1
# Хвост истории: хватает на max(duration) + max(rest_hours) (ADR-0008) и окно затухания
HISTORY_DAYS = 90


def _occupied_days(a: Assignment) -> tuple[dt.date, dt.date]:
    days = a.occupied_days
    assert days.lower is not None
    assert days.upper is not None
    last = days.upper if days.upper_inc else days.upper - dt.timedelta(days=1)
    return days.lower, last


async def build_snapshot(
    session: AsyncSession,
    people: PeopleLoader,
    schedule: Schedule,
    unit: UnitProjection,
    *,
    timezone: str,
    history_days: int = HISTORY_DAYS,
) -> dict[str, Any]:
    month = month_days(schedule.month)
    first, last = month[0] - dt.timedelta(days=history_days), month[-1]
    days = [first + dt.timedelta(days=i) for i in range((last - first).days + 1)]
    day_index = {d: i for i, d in enumerate(days)}
    exceptions = dict(
        (
            await session.execute(
                select(CalendarProjection.date, CalendarProjection.kind).where(
                    CalendarProjection.date >= first, CalendarProjection.date <= last
                )
            )
        ).all()
    )

    def day(value: dt.date | None, *, clamp: bool) -> int | None:
        """Номер дня горизонта; за пределами — `None` (для границ интервалов — «открыто»)."""
        if value is None:
            return None
        if value in day_index:
            return day_index[value]
        if clamp:
            return None
        raise ValueError(value)

    # --- подразделения поддерева ------------------------------------------------------------
    units = list(
        await session.scalars(
            select(UnitProjection)
            .where(is_descendant_or_self(UnitProjection.path, unit.path))
            .order_by(UnitProjection.path)
        )
    )
    unit_index = {u.unit_id: i for i, u in enumerate(units)}
    paths = {u.unit_id: u.path for u in units}

    # --- ячейки графиков поддерева за месяц --------------------------------------------------
    schedules = {
        s.id: s
        for s in await session.scalars(
            select(Schedule).where(
                in_array(Schedule.unit_id, unit_index), Schedule.month == schedule.month
            )
        )
    }
    cells = list(
        await session.scalars(
            select(DayPlan)
            .where(in_array(DayPlan.schedule_id, schedules))
            .order_by(DayPlan.date, DayPlan.duty_role_id, DayPlan.id)
        )
    )
    cell_index = {c.id: i for i, c in enumerate(cells)}

    # --- роли в ячейках -------------------------------------------------------------------------
    role_rows = (
        await session.execute(
            select(DutyRole, DutyType)
            .join(DutyType, DutyType.id == DutyRole.duty_type_id)
            .where(in_array(DutyRole.id, {c.duty_role_id for c in cells}))
            .order_by(DutyRole.id)
        )
    ).all()
    role_index = {r.id: i for i, (r, _) in enumerate(role_rows)}

    # --- люди поддерева ---------------------------------------------------------------------
    persons = sorted(
        await people(unit_ids=[unit.unit_id], date_from=first, date_to=last),
        key=lambda p: str(p.id),
    )
    person_index = {p.id: i for i, p in enumerate(persons)}
    limits = [
        LimitRule(
            r.id,
            path,
            r.unit_id,
            r.applies_to_subtree,
            r.rank_id,
            r.position_id,
            r.max_duties,
            r.max_holiday_duties,
        )
        for r, path in await session.execute(
            select(DutyLimit, UnitProjection.path)
            .join(UnitProjection, UnitProjection.unit_id == DutyLimit.unit_id)
            .where(
                or_(
                    is_ancestor_or_self(UnitProjection.path, unit.path),
                    is_descendant_or_self(UnitProjection.path, unit.path),
                )
            )
            .order_by(DutyLimit.id)
        )
    ]

    def person_out(p: Any) -> dict[str, Any]:
        clearances = []
        for role, start, end in p.clearances:
            if role not in role_index or (start and start > last) or (end and end < first):
                continue
            clearances.append([role_index[role], day(start, clamp=True), day(end, clamp=True)])
        exemptions = [
            [day(max(start, first), clamp=False), day(min(end, last), clamp=False)]
            for start, end in p.exemptions
            if end >= first and start <= last
        ]
        rule = resolve_limit(limits, p.unit_id, paths.get(p.unit_id, ""), p)
        return {
            "id": p.id,
            "u": unit_index.get(p.unit_id),
            "c": sorted(clearances, key=lambda c: c[0]),
            "x": exemptions,
            "limit": [rule.max_duties, rule.max_holiday_duties] if rule else None,
        }

    # --- назначения людей за горизонт ---------------------------------------------------------
    assignments = (
        await session.execute(
            select(
                Assignment,
                DayPlan.date,
                DayPlan.duty_role_id,
                DutyType.load_weight,
                DutyType.id,
                DutyType.rest_hours,
            )
            .join(DayPlan, DayPlan.id == Assignment.day_plan_id)
            .join(DutyType, DutyType.id == DayPlan.duty_type_id)
            .where(
                in_array(Assignment.person_id, person_index),
                DayPlan.date >= first,
                DayPlan.date <= last,
            )
            .order_by(Assignment.start_at, Assignment.id)
        )
    ).all()

    origin = dt.datetime.combine(first, dt.time(0), tzinfo=ZoneInfo(timezone))

    def minutes(moment: dt.datetime) -> int:
        """Местное время от полуночи первого дня горизонта, в минутах."""
        return int((moment - origin).total_seconds() // 60)

    def assignment_out(
        a: Assignment, date: dt.date, role: uuid.UUID, weight: float, type_id: uuid.UUID, rest: int
    ) -> dict[str, Any]:
        occ_first, occ_last = _occupied_days(a)
        occupied = (occ_last - occ_first).days + 1
        return {
            "id": a.id,
            "p": person_index[a.person_id],
            "cell": cell_index.get(a.day_plan_id),
            "d": day_index[date],
            "r": role_index.get(role),
            "dt": type_id,
            # Интервал и отдых — для нарядов вне ролей снимка (история других нарядов)
            "t": [minutes(a.start_at), minutes(a.end_at)],
            "rest": rest,
            # Занятые сутки могут выходить за конец горизонта (наряд 30-го до 1-го)
            "days": [day_index[date], day_index[date] + occupied - 1],
            "load": round(occupied * weight, 2),
            "pinned": a.is_pinned,
            "auto": a.source == "auto",
            "override": a.rest_override or a.limit_override,
        }

    content: dict[str, Any] = {
        "snapshot_version": SNAPSHOT_VERSION,
        "timezone": timezone,
        "schedule": {
            "id": schedule.id,
            "unit": unit_index[unit.unit_id],
            "month": schedule.month,
            "status": schedule.status,
        },
        "horizon": {"from": first, "to": last, "month_start": day_index[month[0]]},
        "days": [[d, day_kind(d, exceptions)] for d in days],
        "units": [
            {
                "id": u.unit_id,
                "parent": unit_index.get(u.parent_id) if u.parent_id else None,
                "name": u.name,
            }
            for u in units
        ],
        "roles": [
            {
                "id": r.id,
                "duty_type_id": t.id,
                "duty_type": t.name,
                "name": r.name,
                "headcount": r.headcount,
                "start_time": t.start_time,
                "duration_minutes": t.duration_minutes,
                "rest_hours": t.rest_hours,
                "load_weight": t.load_weight,
                "active": r.is_active and t.is_active,
            }
            for r, t in role_rows
        ],
        "people": [person_out(p) for p in persons],
        "cells": [
            {
                "id": c.id,
                "d": day_index[c.date],
                "r": role_index[c.duty_role_id],
                "s": unit_index[schedules[c.schedule_id].unit_id],
                "e": unit_index.get(c.executor_unit_id),
                "origin": c.origin,
                "status": c.delegation_status,
                "pinned": c.is_pinned,
                "parent": cell_index.get(c.parent_day_plan_id) if c.parent_day_plan_id else None,
            }
            for c in cells
        ],
        "assignments": [assignment_out(*row) for row in assignments],
    }
    digest = hashlib.sha256(to_json(content)).hexdigest()
    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "hash": digest,
        "created_at": dt.datetime.now(dt.UTC),
        **{k: v for k, v in content.items() if k != "snapshot_version"},
    }
