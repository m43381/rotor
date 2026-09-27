"""Данные для печатных форм (фаза 6b): график на месяц и суточный наряд на дату.

Печать делает `documents`, данные он берёт здесь от имени оператора (ADR-0014): права —
как на чтение графика. Звание и полное ФИО берутся у personnel одним batch-запросом, как
для списков кандидатов, — в назначении хранится только краткое имя.
"""

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Iterable
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dutyflow_common.calendar import CalendarProjection, day_kind
from dutyflow_common.context import Operator
from dutyflow_common.errors import NotFoundError
from dutyflow_common.ltree import is_descendant_or_self
from dutyflow_common.policy import Policy, default_policy
from dutyflow_common.projections import UnitProjection
from scheduling.checks import PersonInfo, interval
from scheduling.models import Assignment, DayPlan, DutyRole, DutyType, Schedule
from scheduling.people import PeopleLoader
from scheduling.schedules import ScheduleService
from scheduling.schemas import (
    DailyRosterOut,
    PrintCell,
    PrintPerson,
    PrintRow,
    PrintScheduleOut,
    RosterDuty,
    RosterRole,
    ScheduleStatus,
)


class PrintService(ScheduleService):
    def __init__(
        self,
        session: AsyncSession,
        operator: Operator,
        people: PeopleLoader,
        tz: ZoneInfo,
        policy: Policy = default_policy,
    ) -> None:
        super().__init__(session, operator, policy)
        self.people = people
        self.tz = tz

    async def _people(
        self, person_ids: Iterable[uuid.UUID], day_from: dt.date, day_to: dt.date
    ) -> tuple[dict[uuid.UUID, PersonInfo], dict[uuid.UUID, str]]:
        ids = sorted(set(person_ids))
        if not ids:
            return {}, {}
        info = {
            p.id: p for p in await self.people(date_from=day_from, date_to=day_to, person_ids=ids)
        }
        names = dict(
            (
                await self.session.execute(
                    select(UnitProjection.unit_id, UnitProjection.name).where(
                        UnitProjection.unit_id.in_({p.unit_id for p in info.values()})
                    )
                )
            ).all()
        )
        return info, names

    @staticmethod
    def _person(
        person_id: uuid.UUID,
        fallback: str,
        conflict: str | None,
        info: dict[uuid.UUID, PersonInfo],
        units: dict[uuid.UUID, str],
    ) -> PrintPerson:
        p = info.get(person_id)
        if p is None:  # человек недоступен в personnel — печатается сохранённое имя
            return PrintPerson(
                person_id=person_id,
                rank_name=None,
                last_name=fallback,
                first_name="",
                middle_name=None,
                short_name=fallback,
                unit_name=None,
                conflict=conflict,
            )
        return PrintPerson(
            person_id=person_id,
            rank_name=p.rank_name,
            last_name=p.last_name,
            first_name=p.first_name,
            middle_name=p.middle_name,
            short_name=p.short_name,
            unit_name=units.get(p.unit_id),
            conflict=conflict,
        )

    # --- график на месяц ---------------------------------------------------------------------

    async def schedule_print(self, schedule_id: uuid.UUID) -> PrintScheduleOut:
        table = await self.table(schedule_id)
        schedule_unit = table.schedule.unit_id
        cell_ids = [c.id for row in table.rows for c in row.cells if c is not None]
        rows = (
            await self.session.execute(
                select(
                    Assignment.day_plan_id,
                    Assignment.person_id,
                    Assignment.person_name,
                    Assignment.conflict,
                )
                .where(Assignment.day_plan_id.in_(cell_ids))
                .order_by(Assignment.assigned_at)
            )
        ).all()
        days = [d.date for d in table.days]
        info, units = await self._people((r.person_id for r in rows), days[0], days[-1])
        by_cell: dict[uuid.UUID, list[PrintPerson]] = defaultdict(list)
        for r in rows:
            by_cell[r.day_plan_id].append(
                self._person(r.person_id, r.person_name, r.conflict, info, units)
            )
        out_rows = []
        for row in table.rows:
            cells: list[PrintCell | None] = []
            for c in row.cells:
                if c is None or c.state == "inactive":
                    cells.append(None)
                elif c.executor_unit_id != schedule_unit:
                    unit = table.units.get(c.executor_unit_id)
                    cells.append(
                        PrintCell(
                            executor_unit_name=(unit.short_name or unit.name) if unit else None
                        )
                    )
                else:
                    people = by_cell.get(c.id, [])
                    cells.append(
                        PrintCell(people=people, missing=max(0, row.headcount - len(people)))
                    )
            out_rows.append(
                PrintRow(
                    duty_type_name=row.duty_type_name,
                    duty_type_short_name=row.duty_type_short_name,
                    owner_unit_name=row.owner_unit_name,
                    role_name=row.role_name,
                    start_time=row.start_time,
                    duration_minutes=row.duration_minutes,
                    headcount=row.headcount,
                    cells=cells,
                )
            )
        return PrintScheduleOut(schedule=table.schedule, days=table.days, rows=out_rows)

    # --- суточный наряд --------------------------------------------------------------------

    async def daily_roster(self, unit_id: uuid.UUID, date: dt.date) -> DailyRosterOut:
        """Наряды с датой заступления `date`, которые закрывают подразделение и его
        поддерево своими людьми (ячейка у исполнителя, не переданная дальше)."""
        unit = await self._unit(unit_id)
        if not await self._can("read", unit.path):
            raise NotFoundError("Подразделение не найдено")
        cells = (
            await self.session.execute(
                select(DayPlan, Schedule.status, DutyType, DutyRole, UnitProjection.name)
                .join(Schedule, Schedule.id == DayPlan.schedule_id)
                .join(UnitProjection, UnitProjection.unit_id == Schedule.unit_id)
                .join(DutyType, DutyType.id == DayPlan.duty_type_id)
                .join(DutyRole, DutyRole.id == DayPlan.duty_role_id)
                .where(
                    DayPlan.date == date,
                    DayPlan.executor_unit_id == Schedule.unit_id,
                    DutyType.is_active,
                    DutyRole.is_active,
                    is_descendant_or_self(UnitProjection.path, unit.path),
                )
            )
        ).all()
        ids = [c.DayPlan.id for c in cells]
        assigned = (
            await self.session.execute(
                select(
                    Assignment.day_plan_id,
                    Assignment.person_id,
                    Assignment.person_name,
                    Assignment.conflict,
                )
                .where(Assignment.day_plan_id.in_(ids))
                .order_by(Assignment.assigned_at)
            )
        ).all()
        info, units = await self._people((a.person_id for a in assigned), date, date)
        people: dict[uuid.UUID, list[PrintPerson]] = defaultdict(list)
        for a in assigned:
            people[a.day_plan_id].append(
                self._person(a.person_id, a.person_name, a.conflict, info, units)
            )
        owners = dict(
            (
                await self.session.execute(
                    select(UnitProjection.unit_id, UnitProjection.name).where(
                        UnitProjection.unit_id.in_({c.DutyType.owner_unit_id for c in cells})
                    )
                )
            ).all()
        )
        duties: dict[tuple[uuid.UUID, str], RosterDuty] = {}
        order: dict[tuple[uuid.UUID, str], tuple[dt.time, str, str]] = {}
        role_order: dict[tuple[uuid.UUID, str], list[tuple[int, str, RosterRole]]] = defaultdict(
            list
        )
        for c in sorted(cells, key=lambda c: (c.DutyType.start_time, c.DutyType.name)):
            key = (c.DutyType.id, c.name)
            if key not in duties:
                span = interval(date, c.DutyType.start_time, c.DutyType.duration_minutes, self.tz)
                duties[key] = RosterDuty(
                    duty_type_name=c.DutyType.name,
                    owner_unit_name=owners.get(c.DutyType.owner_unit_id),
                    executor_unit_name=c.name,
                    start_at=span.start_at,
                    end_at=span.end_at,
                    roles=[],
                )
                order[key] = (c.DutyType.start_time, c.DutyType.name, c.name)
            got = people.get(c.DayPlan.id, [])
            role_order[key].append(
                (
                    c.DutyRole.sort_order,
                    c.DutyRole.name,
                    RosterRole(
                        role_name=c.DutyRole.name,
                        headcount=c.DutyRole.headcount,
                        people=got,
                        missing=max(0, c.DutyRole.headcount - len(got)),
                    ),
                )
            )
        for key, items in role_order.items():
            duties[key].roles = [r for _, _, r in sorted(items, key=lambda x: (x[0], x[1]))]
        calendar = await self.session.get(CalendarProjection, date)
        statuses: list[ScheduleStatus] = sorted({c.status for c in cells})
        return DailyRosterOut(
            unit_id=unit.unit_id,
            unit_name=unit.name,
            date=date,
            day_kind=day_kind(date, {date: calendar.kind} if calendar else {}),
            day_name=calendar.name if calendar else None,
            statuses=statuses,
            duties=[duties[k] for k in sorted(duties, key=lambda k: order[k])],
        )
