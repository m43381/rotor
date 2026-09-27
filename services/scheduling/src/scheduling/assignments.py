"""Ручные назначения людей в ячейки и пометка конфликтов (фаза 3b).

- Назначает только конечный исполнитель ячейки: подразделение графика, если роль не
  передана дальше. Назначение во входящую непринятую ячейку принимает её.
- Кандидаты — люди поддерева исполнителя (open-questions №37) из снимка personnel.
- Проверки — `scheduling.checks`; всё грузится пакетом: люди — одним запросом в personnel,
  наряды людей, календарь и лимиты — по одному запросу в свою БД.
- «Не больше одного наряда в сутки» дополнительно гарантирует exclusion-ограничение БД.
- Изменения у людей после назначения не снимают его, а помечают конфликтом (№39).
"""

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from dutyflow_common import audit
from dutyflow_common.calendar import CalendarProjection, day_kind
from dutyflow_common.context import Operator
from dutyflow_common.errors import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
)
from dutyflow_common.ids import uuid7
from dutyflow_common.ltree import is_ancestor_or_self, is_descendant_or_self
from dutyflow_common.policy import Policy, default_policy
from dutyflow_common.projections import UnitProjection, unit_path
from dutyflow_common.scope import in_scope
from scheduling.checks import (
    Busy,
    Interval,
    LimitRule,
    Slot,
    Violation,
    evaluate,
    interval,
    resolve_limit,
)
from scheduling.facts import emit_created, emit_removed
from scheduling.models import Assignment, DayPlan, DutyLimit, DutyRole, DutyType, Schedule
from scheduling.people import PeopleLoader
from scheduling.schedules import assigned_out, month_days
from scheduling.schemas import (
    AssignedOut,
    AssignIn,
    CandidateOut,
    CandidatesOut,
    CellInfo,
    ViolationOut,
)

ONE_PER_DAY = "ex_assignment_one_per_day"
# Окно вокруг месяца ячейки: соседние наряды для проверки отдыха (отдых — до 30 суток)
WINDOW = dt.timedelta(days=31)


class AssignmentBlockedError(AppError):
    """Есть нарушения, которые нельзя подтвердить (нет допуска, освобождён, занят …)."""

    status_code = 422
    code = "assignment_blocked"


class OverrideRequiredError(AppError):
    """Нарушены отдых или лимит — назначить можно с подтверждением и комментарием."""

    status_code = 422
    code = "override_required"


def _violations(items: Iterable[Violation]) -> list[ViolationOut]:
    return [ViolationOut(kind=v.kind, message=v.message, overridable=v.overridable) for v in items]


@dataclass(slots=True)
class CellContext:
    cell: DayPlan
    schedule: Schedule
    unit: UnitProjection
    role: DutyRole
    duty_type: DutyType
    slot: Slot
    can_assign: bool


class AssignmentService:
    def __init__(
        self,
        session: AsyncSession,
        operator: Operator,
        people: PeopleLoader,
        tz: ZoneInfo,
        policy: Policy = default_policy,
    ) -> None:
        self.session = session
        self.operator = operator
        self.people = people
        self.tz = tz
        self.policy = policy
        self._op_path: str | None = None

    async def _can(self, action: str, path: str) -> bool:
        if self._op_path is None:
            self._op_path = await unit_path(self.session, self.operator.unit_id)
        scope = self.policy.scope_for(self.operator.roles, "schedule", action)
        return in_scope(path, self._op_path, scope)

    # --- контекст ячейки -------------------------------------------------------------------

    async def _context(self, day_plan_id: uuid.UUID, action: str) -> CellContext:
        row = (
            await self.session.execute(
                select(DayPlan, Schedule, UnitProjection, DutyRole, DutyType)
                .join(Schedule, Schedule.id == DayPlan.schedule_id)
                .join(UnitProjection, UnitProjection.unit_id == Schedule.unit_id)
                .join(DutyRole, DutyRole.id == DayPlan.duty_role_id)
                .join(DutyType, DutyType.id == DayPlan.duty_type_id)
                .where(DayPlan.id == day_plan_id)
            )
        ).first()
        if row is None or not await self._can("read", row[2].path):
            raise NotFoundError("Ячейка не найдена")
        cell, schedule, unit, role, duty_type = row
        can_assign = (
            await self._can("update", unit.path)
            and schedule.status != "archived"
            and cell.executor_unit_id == unit.unit_id
            and role.is_active
            and duty_type.is_active
        )
        if action == "update" and not can_assign:
            if not await self._can("update", unit.path):
                raise ForbiddenError("Назначать может подразделение графика и вышестоящие")
            if schedule.status == "archived":
                raise ValidationFailedError("График в архиве — только просмотр")
            if cell.executor_unit_id != unit.unit_id:
                raise ValidationFailedError(
                    "Роль передана нижестоящему подразделению — людей назначает оно"
                )
            raise ValidationFailedError("Роль или наряд выведены из действия")
        kinds = await self._day_kinds(cell.date, cell.date)
        slot = Slot(
            duty_role_id=role.id,
            date=cell.date,
            interval=interval(cell.date, duty_type.start_time, duty_type.duration_minutes, self.tz),
            rest_hours=duty_type.rest_hours,
            is_holiday=kinds[cell.date] in ("weekend", "holiday"),
            executor_path=unit.path,
        )
        return CellContext(cell, schedule, unit, role, duty_type, slot, can_assign)

    async def _day_kinds(self, first: dt.date, last: dt.date) -> dict[dt.date, str]:
        exceptions = dict(
            (
                await self.session.execute(
                    select(CalendarProjection.date, CalendarProjection.kind).where(
                        CalendarProjection.date >= first, CalendarProjection.date <= last
                    )
                )
            ).all()
        )
        days = (last - first).days + 1
        return {
            first + dt.timedelta(days=i): day_kind(first + dt.timedelta(days=i), exceptions)
            for i in range(days)
        }

    def _window(self, day: dt.date) -> tuple[dt.date, dt.date]:
        days = month_days(day.replace(day=1))
        return days[0] - WINDOW, days[-1] + WINDOW

    async def _busy(
        self, person_ids: Iterable[uuid.UUID], day: dt.date, exclude_cell: uuid.UUID
    ) -> dict[uuid.UUID, list[Busy]]:
        """Наряды людей в окне вокруг месяца ячейки — одним запросом."""
        ids = set(person_ids)
        if not ids:
            return {}
        first, last = self._window(day)
        rows = (
            await self.session.execute(
                select(Assignment, DayPlan.date, DutyType.name, DutyType.rest_hours)
                .join(DayPlan, DayPlan.id == Assignment.day_plan_id)
                .join(DutyType, DutyType.id == DayPlan.duty_type_id)
                .where(
                    Assignment.person_id.in_(ids),
                    Assignment.day_plan_id != exclude_cell,
                    DayPlan.date >= first,
                    DayPlan.date <= last,
                )
            )
        ).all()
        kinds = await self._day_kinds(first, last)
        result: dict[uuid.UUID, list[Busy]] = defaultdict(list)
        for a, date, name, rest in rows:
            result[a.person_id].append(
                Busy(
                    a.day_plan_id,
                    _interval_of(a),
                    rest,
                    name,
                    kinds.get(date) in ("weekend", "holiday"),
                )
            )
        return result

    async def _limits(self, executor: UnitProjection) -> list[LimitRule]:
        """Правила вышестоящих подразделений и поддерева исполнителя."""
        rows = await self.session.execute(
            select(DutyLimit, UnitProjection.path)
            .join(UnitProjection, UnitProjection.unit_id == DutyLimit.unit_id)
            .where(
                or_(
                    is_ancestor_or_self(UnitProjection.path, executor.path),
                    is_descendant_or_self(UnitProjection.path, executor.path),
                )
            )
        )
        return [
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
            for r, path in rows
        ]

    async def _paths(self, unit_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, tuple[str, str]]:
        rows = await self.session.execute(
            select(UnitProjection.unit_id, UnitProjection.path, UnitProjection.name).where(
                UnitProjection.unit_id.in_(set(unit_ids))
            )
        )
        return {u: (p, n) for u, p, n in rows}

    async def _assigned(self, ctx: CellContext) -> list[AssignedOut]:
        rows = await self.session.scalars(
            select(Assignment)
            .where(Assignment.day_plan_id == ctx.cell.id)
            .order_by(Assignment.assigned_at)
        )
        return [assigned_out(a, ctx.schedule.published_at) for a in rows]

    # --- кандидаты ----------------------------------------------------------------------------

    async def candidates(self, day_plan_id: uuid.UUID) -> CandidatesOut:
        ctx = await self._context(day_plan_id, "read")
        first, last = self._window(ctx.cell.date)
        people = await self.people(unit_ids=[ctx.unit.unit_id], date_from=first, date_to=last)
        paths = await self._paths(p.unit_id for p in people)
        ctx.slot.unit_paths = {u: p for u, (p, _) in paths.items()}
        busy = await self._busy((p.id for p in people), ctx.cell.date, ctx.cell.id)
        limits = await self._limits(ctx.unit)
        assigned = await self._assigned(ctx)
        taken = {a.person_id for a in assigned}
        month = (ctx.cell.date.year, ctx.cell.date.month)
        result = []
        for p in people:
            if p.id in taken:
                continue
            path, unit_name = paths.get(p.unit_id, ("", None))
            limit = resolve_limit(limits, p.unit_id, path, p)
            own = busy.get(p.id, [])
            violations = evaluate(p, ctx.slot, own, limit)
            in_month = [
                b for b in own if (b.interval.first_day.year, b.interval.first_day.month) == month
            ]
            past = [b.interval.first_day for b in own if b.interval.first_day < ctx.cell.date]
            result.append(
                CandidateOut(
                    person_id=p.id,
                    name=" ".join(filter(None, [p.last_name, p.first_name, p.middle_name])),
                    rank_name=p.rank_name,
                    unit_id=p.unit_id,
                    unit_name=unit_name,
                    month_total=len(in_month),
                    month_holiday=sum(b.is_holiday for b in in_month),
                    last_duty=max(past) if past else None,
                    violations=_violations(violations),
                    eligible=all(v.overridable for v in violations),
                )
            )
        # Сначала пригодные без нарушений, затем по нагрузке за месяц и ФИО
        result.sort(key=lambda c: (not c.eligible, bool(c.violations), c.month_total, c.name))
        return CandidatesOut(
            cell=CellInfo(
                id=ctx.cell.id,
                schedule_id=ctx.schedule.id,
                date=ctx.cell.date,
                duty_type_name=ctx.duty_type.name,
                role_name=ctx.role.name,
                headcount=ctx.role.headcount,
                start_at=ctx.slot.interval.start_at,
                end_at=ctx.slot.interval.end_at,
                executor_unit_id=ctx.cell.executor_unit_id,
                can_assign=ctx.can_assign,
            ),
            assigned=assigned,
            candidates=result,
        )

    # --- назначение и снятие ------------------------------------------------------------------

    async def assign(self, day_plan_id: uuid.UUID, data: AssignIn) -> Assignment:
        ctx = await self._context(day_plan_id, "update")
        cell = (
            await self.session.scalars(
                select(DayPlan).where(DayPlan.id == ctx.cell.id).with_for_update()
            )
        ).one()
        count = len(
            (
                await self.session.scalars(
                    select(Assignment.id).where(Assignment.day_plan_id == cell.id)
                )
            ).all()
        )
        if count >= ctx.role.headcount:
            raise ValidationFailedError(f"Роль уже укомплектована: {count} из {ctx.role.headcount}")
        first, last = self._window(cell.date)
        found = await self.people(person_ids=[data.person_id], date_from=first, date_to=last)
        if not found:
            raise NotFoundError("Человек не найден")
        person = found[0]
        paths = await self._paths([person.unit_id])
        ctx.slot.unit_paths = {u: p for u, (p, _) in paths.items()}
        busy = (await self._busy([person.id], cell.date, cell.id)).get(person.id, [])
        limit = resolve_limit(
            await self._limits(ctx.unit),
            person.unit_id,
            paths.get(person.unit_id, ("", ""))[0],
            person,
        )
        violations = evaluate(person, ctx.slot, busy, limit)
        blocking = [v for v in violations if not v.overridable]
        if blocking:
            raise AssignmentBlockedError(
                f"{person.short_name}: назначить нельзя",
                details={"violations": [v.model_dump() for v in _violations(violations)]},
            )
        if violations and not data.confirm_override:
            raise OverrideRequiredError(
                f"{person.short_name}: назначение нарушает отдых или лимит — "
                "подтвердите с комментарием",
                details={"violations": [v.model_dump() for v in _violations(violations)]},
            )
        rest = any(v.kind == "rest" for v in violations)
        limit_hit = any(v.kind in ("limit", "holiday_limit") for v in violations)
        iv = ctx.slot.interval
        assignment = Assignment(
            id=uuid7(),
            day_plan_id=cell.id,
            person_id=person.id,
            person_name=person.short_name,
            start_at=iv.start_at,
            end_at=iv.end_at,
            occupied_days=Range(iv.first_day, iv.last_day, bounds="[]"),
            source="manual",
            is_pinned=False,
            rest_override=rest,
            limit_override=limit_hit,
            override_comment=(data.override_comment or "").strip() if violations else None,
            assigned_by=self.operator.subject,
            assigned_by_name=self.operator.full_name or self.operator.username,
        )
        self.session.add(assignment)
        if cell.delegation_status == "pending":  # назначить во входящую — значит принять её
            cell.delegation_status = "accepted"
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            if ONE_PER_DAY in str(exc.orig):
                raise ConflictError(
                    f"{person.short_name} уже в наряде в эти сутки (назначен другим оператором)"
                ) from exc
            raise ConflictError(f"{person.short_name} уже назначен в эту ячейку") from exc
        override = rest or limit_hit
        audit.record(
            self.session,
            action="assignment.override" if override else "assignment.create",
            entity_type="assignment",
            entity_id=assignment.id,
            scope_unit_id=ctx.unit.unit_id,
            after={
                **assignment.snapshot(),
                "violations": [v.message for v in violations] or None,
            },
            comment=assignment.override_comment,
            require_comment=override,
        )
        await emit_created(self.session, [assignment])
        await self.session.commit()
        return assignment

    async def _assignment(self, assignment_id: uuid.UUID) -> tuple[Assignment, CellContext]:
        a = await self.session.get(Assignment, assignment_id)
        if a is None:
            raise NotFoundError("Назначение не найдено")
        ctx = await self._context(a.day_plan_id, "update")
        return a, ctx

    async def remove(self, assignment_id: uuid.UUID) -> uuid.UUID:
        a, ctx = await self._assignment(assignment_id)
        audit.record(
            self.session,
            action="assignment.delete",
            entity_type="assignment",
            entity_id=a.id,
            scope_unit_id=ctx.unit.unit_id,
            before=a.snapshot(),
        )
        await emit_removed(self.session, [a])
        await self.session.delete(a)
        await self.session.commit()
        return ctx.cell.id

    async def pin(self, assignment_id: uuid.UUID, pinned: bool) -> uuid.UUID:
        a, ctx = await self._assignment(assignment_id)
        if a.is_pinned != pinned:
            before = a.snapshot()
            a.is_pinned = pinned
            audit.record(
                self.session,
                action="assignment.pin" if pinned else "assignment.unpin",
                entity_type="assignment",
                entity_id=a.id,
                scope_unit_id=ctx.unit.unit_id,
                before=before,
                after=a.snapshot(),
            )
            await self.session.commit()
        return ctx.cell.id


def _interval_of(a: Assignment) -> Interval:
    days = a.occupied_days
    assert days.lower is not None
    assert days.upper is not None
    # PostgreSQL нормализует daterange к виду [lower, upper)
    last = days.upper - dt.timedelta(days=1) if days.upper_inc is False else days.upper
    return Interval(a.start_at, a.end_at, days.lower, last)


# --- конфликты (open-questions №39) ------------------------------------------------------------


async def recompute_conflicts(
    session: AsyncSession, people: PeopleLoader, person_ids: Sequence[uuid.UUID]
) -> int:
    """Перепроверяет будущие назначения людей после изменений в personnel: исключение из
    списков, перевод, освобождение, допуск. Назначения не снимаются — только помечаются
    (и пометка снимается, если причина ушла). Возвращает число изменённых назначений."""
    now = dt.datetime.now(dt.UTC)
    rows = (
        await session.execute(
            select(Assignment, DayPlan.date, DayPlan.duty_role_id, UnitProjection.path)
            .join(DayPlan, DayPlan.id == Assignment.day_plan_id)
            .join(Schedule, Schedule.id == DayPlan.schedule_id)
            .join(UnitProjection, UnitProjection.unit_id == Schedule.unit_id)
            .where(Assignment.person_id.in_(set(person_ids)), Assignment.end_at > now)
        )
    ).all()
    if not rows:
        return 0
    dates = [date for _, date, _, _ in rows]
    found = {
        p.id: p
        for p in await people(
            person_ids=list({a.person_id for a, *_ in rows}),
            date_from=min(dates),
            date_to=max(dates) + dt.timedelta(days=8),
        )
    }
    unit_paths = dict(
        (
            await session.execute(
                select(UnitProjection.unit_id, UnitProjection.path).where(
                    UnitProjection.unit_id.in_({p.unit_id for p in found.values()})
                )
            )
        ).all()
    )
    changed = 0
    for a, date, role_id, executor_path in rows:
        p = found.get(a.person_id)
        if p is None:
            conflict: str | None = "Человек не найден в личном составе"
        else:
            slot = Slot(role_id, date, _interval_of(a), 0, False, executor_path, unit_paths)
            hard = [v.message for v in evaluate(p, slot, [], None) if not v.overridable]
            conflict = "; ".join(hard) or None
        if conflict != a.conflict:
            await session.execute(
                update(Assignment).where(Assignment.id == a.id).values(conflict=conflict)
            )
            changed += 1
    return changed
