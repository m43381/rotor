"""Графики подразделений и делегирование ролей вниз по дереву (фаза 3a, ADR-0009).

Процесс повторяет legacy (`docs/legacy-analysis.md` §2.1–2.2) на новой модели:
- у графика подразделения на месяц явно хранятся ячейки «дата × роль» своих нарядов;
- ячейку можно делегировать прямому дочернему подразделению (open-questions №35): у ячейки
  меняется исполнитель, а в графике дочернего появляется входящая ячейка `pending`;
- дочернее принимает её или делегирует дальше (это тоже принятие); отклонения и сроков нет;
- смена решения удаляет цепочку вниз каскадом БД;
- состояние ячейки для таблицы (8 классов legacy) вычисляется одним JOIN с дочерней ячейкой;
- ячейки роли, закреплённой за подразделением (ADR-0018), сами проходят цепочку до него:
  промежуточные звенья принимают и передают дальше, закреплённое ждёт принятия. Звенья
  до закреплённого подразделения поменять решение не могут.

Все операции пакетные: одна операция — несколько запросов независимо от числа ячеек.
"""

import calendar as cal
import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import ColumnElement, delete, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import StaleDataError

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
from dutyflow_common.outbox import add_event
from dutyflow_common.policy import Policy, default_policy
from dutyflow_common.projections import UnitProjection, unit_path
from dutyflow_common.scope import in_scope, scope_clause
from scheduling.facts import emit_removed
from scheduling.models import Assignment, DayPlan, DutyRole, DutyType, Schedule
from scheduling.schemas import (
    AssignedOut,
    CellOut,
    CellPerson,
    CellState,
    PendingWarning,
    ScheduleOut,
    TableDay,
    TableOut,
    TableRow,
    UnitRef,
)

INSERT_CHUNK = 1000


class RoleLockedError(ValidationFailedError):
    """Ячейки закреплённой роли передаются автоматически — вручную их не переставить."""


class AssignmentsExistError(AppError):
    """Смена решения снимет назначенных людей — нужно явное согласие."""

    status_code = 409
    code = "assignments_exist"


def chain_cte(root_filter: Any) -> Any:
    """Рекурсивный CTE (id, root): ячейки, отобранные условием, и вся цепочка
    делегирования под каждой из них."""
    base = select(DayPlan.id.label("id"), DayPlan.id.label("root")).where(root_filter)
    chain = base.cte("chain", recursive=True)
    child = aliased(DayPlan)
    return chain.union_all(
        select(child.id, chain.c.root).join(chain, child.parent_day_plan_id == chain.c.id)
    )


def month_start(day: dt.date) -> dt.date:
    return day.replace(day=1)


def month_days(month: dt.date) -> list[dt.date]:
    last = cal.monthrange(month.year, month.month)[1]
    return [month.replace(day=d) for d in range(1, last + 1)]


def cell_state(
    cell: DayPlan, schedule_unit: uuid.UUID, child_status: str | None, active: bool
) -> CellState:
    if not active:
        return "inactive"
    delegated = cell.executor_unit_id != schedule_unit
    if cell.origin == "own":
        if not delegated:
            return "own"
        return "delegated_accepted" if child_status == "accepted" else "delegated_pending"
    if not delegated:
        return "incoming_pending" if cell.delegation_status == "pending" else "incoming_active"
    if child_status == "accepted":
        return "incoming_delegated_accepted"
    return "incoming_delegated_pending"


# --- материализация своих ячеек ---------------------------------------------------------------


async def _insert_cells(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> int:
    inserted = 0
    for i in range(0, len(rows), INSERT_CHUNK):
        result = await session.execute(
            insert(DayPlan)
            .values(list(rows[i : i + INSERT_CHUNK]))
            .on_conflict_do_nothing(
                index_elements=[DayPlan.schedule_id, DayPlan.date, DayPlan.duty_role_id]
            )
            .returning(DayPlan.id)
        )
        inserted += len(result.all())
    return inserted


def _own_cell(
    schedule: Schedule, day: dt.date, type_id: uuid.UUID, role_id: uuid.UUID
) -> dict[str, Any]:
    return {
        "id": uuid7(),
        "schedule_id": schedule.id,
        "date": day,
        "duty_type_id": type_id,
        "duty_role_id": role_id,
        "origin": "own",
        "parent_day_plan_id": None,
        "executor_unit_id": schedule.unit_id,
        "delegation_status": "none",
        "is_pinned": False,
        "version": 1,
    }


async def materialize_own_cells(
    session: AsyncSession,
    schedules: Sequence[Schedule],
    role_ids: Iterable[uuid.UUID] | None = None,
    *,
    route_from: dt.date | None = None,
) -> int:
    """Добавляет недостающие ячейки действующих ролей своих нарядов и проводит ячейки
    закреплённых ролей до закреплённого подразделения (с даты `route_from`). Идемпотентно."""
    if not schedules:
        return 0
    if role_ids is not None:
        role_ids = set(role_ids)
    owners = {s.unit_id for s in schedules}
    stmt = (
        select(DutyRole.id, DutyRole.duty_type_id, DutyType.owner_unit_id)
        .join(DutyType, DutyType.id == DutyRole.duty_type_id)
        .where(DutyType.owner_unit_id.in_(owners), DutyType.is_active, DutyRole.is_active)
    )
    if role_ids is not None:
        stmt = stmt.where(DutyRole.id.in_(set(role_ids)))
    roles: dict[uuid.UUID, list[tuple[uuid.UUID, uuid.UUID]]] = defaultdict(list)
    for role_id, type_id, owner in await session.execute(stmt):
        roles[owner].append((type_id, role_id))
    rows = [
        _own_cell(s, day, type_id, role_id)
        for s in schedules
        for type_id, role_id in roles.get(s.unit_id, [])
        for day in month_days(s.month)
    ]
    inserted = await _insert_cells(session, rows)
    await route_pinned_cells(session, schedules, role_ids, from_date=route_from)
    return inserted


# --- закреплённые роли (ADR-0018) --------------------------------------------------------------


async def get_or_create_schedule(
    session: AsyncSession, unit_id: uuid.UUID, month: dt.date
) -> tuple[Schedule, bool]:
    """График подразделения на месяц; новый — с ячейками своих нарядов. Без проверки прав:
    графики создаются и автоматически, при делегировании."""
    month = month_start(month)
    # Вставка «если нет» — два оператора не должны получить два графика одного месяца.
    result = await session.execute(
        insert(Schedule)
        .values(id=uuid7(), unit_id=unit_id, month=month, status="draft", version=1)
        .on_conflict_do_nothing(index_elements=[Schedule.unit_id, Schedule.month])
        .returning(Schedule.id)
    )
    created_id = result.scalar_one_or_none()
    schedule = await session.scalar(
        select(Schedule).where(Schedule.unit_id == unit_id, Schedule.month == month)
    )
    assert schedule is not None
    if created_id is not None:
        await materialize_own_cells(session, [schedule])
        audit.record(
            session,
            action="schedule.create",
            entity_type="schedule",
            entity_id=schedule.id,
            scope_unit_id=unit_id,
            after={"unit_id": unit_id, "month": month},
        )
    return schedule, created_id is not None


async def pin_hops(
    session: AsyncSession, owner_unit_id: uuid.UUID, assigned_unit_id: uuid.UUID
) -> list[UnitProjection] | None:
    """Звенья цепочки от прямого дочернего владельца до закреплённого подразделения включительно.
    [] — роль закреплена за самим владельцем; None — закреплённое подразделение не найдено,
    расформировано или вне поддерева владельца (ячейки тогда остаются у владельца)."""
    if assigned_unit_id == owner_unit_id:
        return []
    owner = await session.get(UnitProjection, owner_unit_id)
    target = await session.get(UnitProjection, assigned_unit_id)
    if owner is None or target is None or not target.is_active:
        return None
    if not _is_below(owner.path, target.path):
        return None
    units = list(
        await session.scalars(
            select(UnitProjection).where(
                is_ancestor_or_self(UnitProjection.path, target.path),
                is_descendant_or_self(UnitProjection.path, owner.path),
                UnitProjection.unit_id != owner_unit_id,
            )
        )
    )
    return sorted(units, key=lambda u: len(u.path.split(".")))


def _is_below(ancestor: str, path: str) -> bool:
    a, p = ancestor.split("."), path.split(".")
    return len(p) > len(a) and p[: len(a)] == a


async def route_pinned_cells(
    session: AsyncSession,
    schedules: Sequence[Schedule],
    role_ids: Iterable[uuid.UUID] | None = None,
    *,
    from_date: dt.date | None = None,
) -> int:
    """Проводит свои ячейки закреплённых ролей по цепочке до закреплённого подразделения:
    у владельца и промежуточных звеньев ячейка передана дальше и закреплена (`is_pinned`),
    у закреплённого — входящая и ждёт принятия. Правильные цепочки не трогает.

    Возвращает число ячеек, которые перестроить нельзя: в их цепочке уже назначены люди
    (снимать людей молча нельзя) или график звена в архиве. Все операции пакетные."""
    owners = {s.unit_id for s in schedules if s.status != "archived"}
    if not owners:
        return 0
    stmt = (
        select(DutyRole.id, DutyRole.assigned_unit_id, DutyType.owner_unit_id)
        .join(DutyType, DutyType.id == DutyRole.duty_type_id)
        .where(
            DutyType.owner_unit_id.in_(owners),
            DutyRole.is_active,
            DutyType.is_active,
            DutyRole.assigned_unit_id.is_not(None),
            DutyRole.assigned_unit_id != DutyType.owner_unit_id,
        )
    )
    if role_ids is not None:
        stmt = stmt.where(DutyRole.id.in_(set(role_ids)))
    roles = (await session.execute(stmt)).all()
    skipped = 0
    for role_id, assigned_id, owner_id in roles:
        assert assigned_id is not None  # отобраны только закреплённые
        hops = await pin_hops(session, owner_id, assigned_id)
        if not hops:
            continue
        own = {s.id: s for s in schedules if s.unit_id == owner_id and s.status != "archived"}
        skipped += await _route_role(session, own, role_id, hops, from_date)
    return skipped


async def _route_role(
    session: AsyncSession,
    own: dict[uuid.UUID, Schedule],
    role_id: uuid.UUID,
    hops: list[UnitProjection],
    from_date: dt.date | None,
) -> int:
    root_filter: list[ColumnElement[bool]] = [
        DayPlan.schedule_id.in_(list(own)),
        DayPlan.duty_role_id == role_id,
        DayPlan.origin == "own",
    ]
    if from_date is not None:
        root_filter.append(DayPlan.date >= from_date)
    roots = {c.id: c for c in await session.scalars(select(DayPlan).where(*root_filter))}
    if not roots:
        return 0
    chain = chain_cte(DayPlan.id.in_(list(roots)))
    below: dict[uuid.UUID, DayPlan] = {}  # родитель → дочерняя ячейка цепочки
    for cell in await session.scalars(
        select(DayPlan).join(chain, chain.c.id == DayPlan.id).where(DayPlan.id.not_in(roots))
    ):
        if cell.parent_day_plan_id is not None:
            below[cell.parent_day_plan_id] = cell
    busy: set[uuid.UUID] = set(
        await session.scalars(
            select(chain.c.root).join(Assignment, Assignment.day_plan_id == chain.c.id).distinct()
        )
    )
    targets = [h.unit_id for h in hops]

    def correct(root: DayPlan) -> bool:
        cell: DayPlan | None = root
        for hop in targets:
            if cell is None or cell.executor_unit_id != hop or not cell.is_pinned:
                return False
            cell = below.get(cell.id)
        return cell is not None  # ячейка у закреплённого подразделения есть

    wrong = [c for c in roots.values() if not correct(c)]
    skipped = sum(c.id in busy for c in wrong)
    wrong = [c for c in wrong if c.id not in busy]
    if not wrong:
        return skipped

    # Графики звеньев по месяцам; архивный график звена — цепочку не построить
    months = {own[c.schedule_id].month for c in wrong}
    chain_schedules: dict[dt.date, list[Schedule]] = {}
    for month in sorted(months):
        linked = [(await get_or_create_schedule(session, h, month))[0] for h in targets]
        if any(s.status == "archived" for s in linked):
            continue
        chain_schedules[month] = linked
    ready = [c for c in wrong if own[c.schedule_id].month in chain_schedules]
    skipped += len(wrong) - len(ready)
    if not ready:
        return skipped
    ids = [c.id for c in ready]
    # Прежние цепочки вниз удаляются (дальше — каскадом по parent_day_plan_id)
    await session.execute(
        delete(DayPlan)
        .where(DayPlan.parent_day_plan_id.in_(ids))
        .execution_options(synchronize_session=False)
    )
    await session.execute(
        update(DayPlan)
        .where(DayPlan.id.in_(ids))
        .values(executor_unit_id=targets[0], is_pinned=True, version=DayPlan.version + 1)
        .execution_options(synchronize_session=False)
    )
    parents = {c.id: c.id for c in ready}  # корень → ячейка предыдущего звена
    last = len(targets) - 1
    for level, hop in enumerate(targets):
        rows = []
        for c in ready:
            cell_id = uuid7()
            rows.append(
                {
                    "id": cell_id,
                    "schedule_id": chain_schedules[own[c.schedule_id].month][level].id,
                    "date": c.date,
                    "duty_type_id": c.duty_type_id,
                    "duty_role_id": c.duty_role_id,
                    "origin": "incoming",
                    "parent_day_plan_id": parents[c.id],
                    "executor_unit_id": targets[level + 1] if level < last else hop,
                    "delegation_status": "accepted" if level < last else "pending",
                    "is_pinned": level < last,
                    "version": 1,
                }
            )
            parents[c.id] = cell_id
        await _insert_cells(session, rows)
    for schedule_id in {c.schedule_id for c in ready}:
        audit.record(
            session,
            action="day_plan.route",
            entity_type="schedule",
            entity_id=schedule_id,
            scope_unit_id=own[schedule_id].unit_id,
            after={
                "duty_role_id": role_id,
                "executor_unit_id": targets[-1],
                "cells": sum(c.schedule_id == schedule_id for c in ready),
            },
        )
    return skipped


async def unpin_role_cells(session: AsyncSession, role_id: uuid.UUID, from_date: dt.date) -> None:
    """Роль открепили: цепочки остаются как есть, но звенья снова могут менять решение."""
    await session.execute(
        update(DayPlan)
        .where(
            DayPlan.duty_role_id == role_id,
            DayPlan.date >= from_date,
            DayPlan.is_pinned,
        )
        .values(is_pinned=False, version=DayPlan.version + 1)
        .execution_options(synchronize_session=False)
    )


async def locked_cells(
    session: AsyncSession, cells: Sequence[DayPlan], unit_path: str
) -> str | None:
    """Сообщение, если среди ячеек графика подразделения `unit_path` есть ячейки роли,
    закреплённой за нижестоящим подразделением: решение по ним принимает не график."""
    role_ids = {c.duty_role_id for c in cells}
    if not role_ids:
        return None
    for name, target, target_path in await session.execute(
        select(DutyRole.name, UnitProjection.name, UnitProjection.path)
        .join(UnitProjection, UnitProjection.unit_id == DutyRole.assigned_unit_id)
        .where(DutyRole.id.in_(role_ids))
    ):
        if _is_below(unit_path, target_path):
            return (
                f"Роль «{name}» закреплена за подразделением «{target}»: её ячейки передаются "
                "ему автоматически. Чтобы изменить исполнителя, снимите закрепление в наряде."
            )
    return None


async def sync_owner_cells(
    session: AsyncSession, owner_unit_id: uuid.UUID, role_ids: Iterable[uuid.UUID]
) -> None:
    """После изменения ролей или наряда: в неархивных графиках владельца с текущего месяца
    добавить ячейки действующих ролей и убрать ячейки выключенных, если роль ещё не
    делегирована. Делегированные ячейки остаются — таблица покажет их как «не действует»."""
    ids = set(role_ids)
    schedules = list(
        await session.scalars(
            select(Schedule).where(
                Schedule.unit_id == owner_unit_id,
                Schedule.status != "archived",
                Schedule.month >= month_start(dt.date.today()),
            )
        )
    )
    if not schedules or not ids:
        return
    await materialize_own_cells(session, schedules, ids, route_from=dt.date.today())
    inactive = (
        select(DutyRole.id)
        .join(DutyType, DutyType.id == DutyRole.duty_type_id)
        .where(DutyRole.id.in_(ids), ~(DutyRole.is_active & DutyType.is_active))
    )
    await session.execute(
        delete(DayPlan)
        .where(
            DayPlan.schedule_id.in_([s.id for s in schedules]),
            DayPlan.origin == "own",
            DayPlan.executor_unit_id == owner_unit_id,
            DayPlan.duty_role_id.in_(inactive),
            ~exists().where(Assignment.day_plan_id == DayPlan.id),
        )
        .execution_options(synchronize_session=False)
    )


# --- сервис ------------------------------------------------------------------------------------


class ScheduleService:
    def __init__(
        self, session: AsyncSession, operator: Operator, policy: Policy = default_policy
    ) -> None:
        self.session = session
        self.operator = operator
        self.policy = policy
        self._op_path: str | None = None

    async def operator_path(self) -> str:
        if self._op_path is None:
            self._op_path = await unit_path(self.session, self.operator.unit_id)
        return self._op_path

    async def _unit(self, unit_id: uuid.UUID) -> UnitProjection:
        unit = await self.session.get(UnitProjection, unit_id)
        if unit is None:
            raise ValidationFailedError("Подразделение не найдено")
        return unit

    async def _can(self, action: str, path: str) -> bool:
        scope = self.policy.scope_for(self.operator.roles, "schedule", action)
        return in_scope(path, await self.operator_path(), scope)

    async def access(self, schedule_id: uuid.UUID, action: str) -> tuple[Schedule, UnitProjection]:
        """График и его подразделение с проверкой права (для других сервисов модуля)."""
        return await self._schedule(schedule_id, action)

    async def _schedule(
        self, schedule_id: uuid.UUID, action: str
    ) -> tuple[Schedule, UnitProjection]:
        schedule = await self.session.get(Schedule, schedule_id)
        if schedule is None:
            raise NotFoundError("График не найден")
        unit = await self._unit(schedule.unit_id)
        if not await self._can("read", unit.path):
            raise NotFoundError("График не найден")
        if action != "read":
            if not await self._can(action, unit.path):
                raise ForbiddenError(
                    "Изменять этот график может только его подразделение и вышестоящие"
                )
            if schedule.status == "archived":
                raise ValidationFailedError("График в архиве — только просмотр")
        return schedule, unit

    # --- графики ----------------------------------------------------------------------------

    async def _out(self, schedules: Sequence[Schedule]) -> list[ScheduleOut]:
        if not schedules:
            return []
        units = {
            u.unit_id: u
            for u in await self.session.scalars(
                select(UnitProjection).where(
                    UnitProjection.unit_id.in_({s.unit_id for s in schedules})
                )
            )
        }
        pending = dict(
            (
                await self.session.execute(
                    select(DayPlan.schedule_id, func.count())
                    .where(
                        DayPlan.schedule_id.in_([s.id for s in schedules]),
                        DayPlan.delegation_status == "pending",
                        DayPlan.origin == "incoming",
                    )
                    .group_by(DayPlan.schedule_id)
                )
            ).all()
        )
        fill = await self._fill_stats([s.id for s in schedules])
        result = []
        for s in schedules:
            unit = units.get(s.unit_id)
            can_edit = (
                unit is not None and s.status != "archived" and await self._can("update", unit.path)
            )
            result.append(
                ScheduleOut(
                    id=s.id,
                    unit_id=s.unit_id,
                    unit_name=unit.name if unit else None,
                    month=s.month,
                    status=s.status,
                    published_at=s.published_at,
                    published_by=s.published_by,
                    version=s.version,
                    can_edit=can_edit,
                    pending_incoming=pending.get(s.id, 0),
                    to_fill=fill.get(s.id, (0, 0))[0],
                    unfilled=fill.get(s.id, (0, 0))[1],
                )
            )
        return result

    async def _fill_stats(self, schedule_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
        """По графикам: сколько ячеек подразделение закрывает само и сколько из них
        не укомплектовано. Один запрос на пачку графиков."""
        filled = (
            select(Assignment.day_plan_id, func.count().label("n"))
            .join(DayPlan, DayPlan.id == Assignment.day_plan_id)
            .where(DayPlan.schedule_id.in_(schedule_ids))
            .group_by(Assignment.day_plan_id)
            .subquery()
        )
        rows = await self.session.execute(
            select(
                DayPlan.schedule_id,
                func.count(),
                func.count().filter(func.coalesce(filled.c.n, 0) < DutyRole.headcount),
            )
            .join(Schedule, Schedule.id == DayPlan.schedule_id)
            .join(DutyRole, DutyRole.id == DayPlan.duty_role_id)
            .join(DutyType, DutyType.id == DayPlan.duty_type_id)
            .outerjoin(filled, filled.c.day_plan_id == DayPlan.id)
            .where(
                DayPlan.schedule_id.in_(schedule_ids),
                DayPlan.executor_unit_id == Schedule.unit_id,
                DutyRole.is_active,
                DutyType.is_active,
            )
            .group_by(DayPlan.schedule_id)
        )
        return {sid: (total, open_) for sid, total, open_ in rows}

    async def list_schedules(
        self, month: dt.date, unit_id: uuid.UUID | None = None
    ) -> list[ScheduleOut]:
        scope = self.policy.require(self.operator.roles, "schedule", "read")
        stmt = (
            select(Schedule)
            .join(UnitProjection, UnitProjection.unit_id == Schedule.unit_id)
            .where(
                Schedule.month == month_start(month),
                scope_clause(UnitProjection.path, await self.operator_path(), scope),
            )
            .order_by(UnitProjection.path)
        )
        if unit_id is not None:
            stmt = stmt.where(Schedule.unit_id == unit_id)
        return await self._out(list(await self.session.scalars(stmt)))

    async def get(self, schedule_id: uuid.UUID) -> ScheduleOut:
        schedule, _ = await self._schedule(schedule_id, "read")
        return (await self._out([schedule]))[0]

    async def _get_or_create(self, unit_id: uuid.UUID, month: dt.date) -> tuple[Schedule, bool]:
        return await get_or_create_schedule(self.session, unit_id, month)

    async def create(self, unit_id: uuid.UUID, month: dt.date) -> Schedule:
        unit = await self._unit(unit_id)
        if not await self._can("create", unit.path):
            raise ForbiddenError("Подразделение вне зоны ответственности оператора")
        if not unit.is_active:
            raise ValidationFailedError("Подразделение расформировано")
        schedule, created = await self._get_or_create(unit_id, month)
        if not created:
            raise ConflictError("График на этот месяц уже есть")
        await self.session.commit()
        return schedule

    # --- таблица месяца -----------------------------------------------------------------------

    async def table(self, schedule_id: uuid.UUID) -> TableOut:
        schedule, unit = await self._schedule(schedule_id, "read")
        days = month_days(schedule.month)
        exceptions = {
            c.date: c
            for c in await self.session.scalars(
                select(CalendarProjection).where(
                    CalendarProjection.date >= days[0], CalendarProjection.date <= days[-1]
                )
            )
        }
        kinds = {c.date: c.kind for c in exceptions.values()}
        child = aliased(DayPlan)
        cells = (
            await self.session.execute(
                select(DayPlan, child.delegation_status)
                .outerjoin(child, child.parent_day_plan_id == DayPlan.id)
                .where(DayPlan.schedule_id == schedule.id)
            )
        ).all()
        role_ids = {c.duty_role_id for c, _ in cells}
        owner = aliased(UnitProjection)
        pinned_to = aliased(UnitProjection)
        roles = {}
        pins: dict[uuid.UUID, tuple[str | None, str | None]] = {}
        role_rows = await self.session.execute(
            select(DutyRole, DutyType, owner.path, owner.name, pinned_to.name, pinned_to.path)
            .join(DutyType, DutyType.id == DutyRole.duty_type_id)
            .outerjoin(owner, owner.unit_id == DutyType.owner_unit_id)
            .outerjoin(pinned_to, pinned_to.unit_id == DutyRole.assigned_unit_id)
            .where(DutyRole.id.in_(role_ids))
        )
        for role, duty_type, owner_path, owner_name, pin_name, pin_path in role_rows:
            roles[role.id] = (role, duty_type, owner_path, owner_name)
            pins[role.id] = (pin_name, pin_path)
        chain = chain_cte(DayPlan.schedule_id == schedule.id)
        filled: dict[uuid.UUID, int] = dict(
            (
                await self.session.execute(
                    select(chain.c.root, func.count(Assignment.id))
                    .join(Assignment, Assignment.day_plan_id == chain.c.id)
                    .group_by(chain.c.root)
                )
            ).all()
        )
        assigned: dict[uuid.UUID, list[CellPerson]] = defaultdict(list)
        for day_plan_id, name, conflict in await self.session.execute(
            select(Assignment.day_plan_id, Assignment.person_name, Assignment.conflict)
            .join(DayPlan, DayPlan.id == Assignment.day_plan_id)
            .where(DayPlan.schedule_id == schedule.id)
            .order_by(Assignment.assigned_at)
        ):
            assigned[day_plan_id].append(CellPerson(person_name=name, conflict=conflict))
        index = {d: i for i, d in enumerate(days)}
        by_role: dict[uuid.UUID, list[CellOut | None]] = {r: [None] * len(days) for r in role_ids}
        executors = {schedule.unit_id}
        for c, child_status in cells:
            role, duty_type, _, _ = roles[c.duty_role_id]
            active = role.is_active and duty_type.is_active
            by_role[c.duty_role_id][index[c.date]] = CellOut(
                id=c.id,
                state=cell_state(c, schedule.unit_id, child_status, active),
                executor_unit_id=c.executor_unit_id,
                is_pinned=c.is_pinned,
                filled=filled.get(c.id, 0),
                assigned=assigned.get(c.id, []),
                has_conflict=any(p.conflict for p in assigned.get(c.id, [])),
            )
            executors.add(c.executor_unit_id)

        # Сначала наряды вышестоящих (короче путь владельца), затем свои; внутри — по имени
        ordered = sorted(
            roles.values(),
            key=lambda x: (len((x[2] or "").split(".")), x[1].name, x[0].sort_order, x[0].name),
        )
        rows = [
            TableRow(
                duty_type_id=duty_type.id,
                duty_type_name=duty_type.name,
                duty_type_short_name=duty_type.short_name,
                owner_unit_id=duty_type.owner_unit_id,
                owner_unit_name=owner_name,
                start_time=duty_type.start_time,
                duration_minutes=duty_type.duration_minutes,
                duty_role_id=role.id,
                role_name=role.name,
                headcount=role.headcount,
                is_active=role.is_active and duty_type.is_active,
                assigned_unit_id=role.assigned_unit_id,
                assigned_unit_name=pins[role.id][0],
                # Решение по ячейкам роли принимает не этот график, а закреплённое подразделение
                locked=bool(pins[role.id][1] and _is_below(unit.path, pins[role.id][1] or "")),
                cells=by_role[role.id],
            )
            for role, duty_type, _, owner_name in ordered
        ]
        children = list(
            await self.session.scalars(
                select(UnitProjection)
                .where(UnitProjection.parent_id == unit.unit_id, UnitProjection.is_active)
                .order_by(UnitProjection.name)
            )
        )
        named = {
            u.unit_id: u
            for u in await self.session.scalars(
                select(UnitProjection).where(UnitProjection.unit_id.in_(executors))
            )
        }
        return TableOut(
            schedule=(await self._out([schedule]))[0],
            days=[
                TableDay(
                    date=d,
                    kind=day_kind(d, kinds),
                    name=exceptions[d].name if d in exceptions else None,
                )
                for d in days
            ],
            rows=rows,
            children=[
                UnitRef(id=u.unit_id, name=u.name, short_name=u.short_name) for u in children
            ],
            units={
                k: UnitRef(id=u.unit_id, name=u.name, short_name=u.short_name)
                for k, u in named.items()
            },
        )

    # --- делегирование и принятие -------------------------------------------------------------

    async def _cells(self, schedule: Schedule, cell_ids: Iterable[uuid.UUID]) -> list[DayPlan]:
        ids = set(cell_ids)
        cells = list(
            await self.session.scalars(
                select(DayPlan)
                .where(DayPlan.id.in_(ids), DayPlan.schedule_id == schedule.id)
                .order_by(DayPlan.date)
                .with_for_update()
            )
        )
        if len(cells) != len(ids):
            raise NotFoundError("Часть ячеек не найдена в этом графике")
        return cells

    async def delegate(
        self,
        schedule_id: uuid.UUID,
        cell_ids: Sequence[uuid.UUID],
        executor_unit_id: uuid.UUID,
        *,
        drop_assignments: bool = False,
        commit: bool = True,
    ) -> int:
        """Передать ячейки прямому дочернему подразделению или вернуть себе."""
        schedule, unit = await self._schedule(schedule_id, "update")
        if executor_unit_id != unit.unit_id:
            executor = await self.session.get(UnitProjection, executor_unit_id)
            if executor is None or executor.parent_id != unit.unit_id:
                raise ValidationFailedError(
                    "Делегировать можно только прямому дочернему подразделению"
                )
            if not executor.is_active:
                raise ValidationFailedError("Подразделение расформировано")
        cells = await self._cells(schedule, cell_ids)
        locked = await locked_cells(self.session, cells, unit.path)
        if locked:
            raise RoleLockedError(locked)
        active = set(
            await self.session.scalars(
                select(DutyRole.id)
                .join(DutyType, DutyType.id == DutyRole.duty_type_id)
                .where(
                    DutyRole.id.in_({c.duty_role_id for c in cells}),
                    DutyRole.is_active,
                    DutyType.is_active,
                )
            )
        )
        if executor_unit_id != unit.unit_id and any(c.duty_role_id not in active for c in cells):
            raise ValidationFailedError("Роль или наряд выведены из действия — делегировать нельзя")
        changed = [c for c in cells if c.executor_unit_id != executor_unit_id]
        if not changed:
            return 0

        ids = [c.id for c in changed]
        chain = chain_cte(DayPlan.id.in_(ids))
        dropped = await self.session.scalar(
            select(func.count(Assignment.id)).join(chain, chain.c.id == Assignment.day_plan_id)
        )
        if dropped and not drop_assignments:
            raise AssignmentsExistError(
                f"В выбранных ячейках и ниже по цепочке уже назначено людей: {dropped}. "
                "Смена решения снимет эти назначения.",
                details={"assignments": dropped},
            )
        if dropped:
            # События о снятых людях — и в самих ячейках, и ниже по цепочке (там их удалит
            # каскад вместе с ячейками): read-model аналитики не должна расходиться
            gone = list(
                await self.session.scalars(
                    select(Assignment).join(chain, chain.c.id == Assignment.day_plan_id)
                )
            )
            await emit_removed(self.session, gone)
        # Назначения в самих ячейках (ниже по цепочке их удалит каскад вместе с ячейками)
        await self.session.execute(
            delete(Assignment)
            .where(Assignment.day_plan_id.in_(ids))
            .execution_options(synchronize_session=False)
        )
        before = {str(c.id): str(c.executor_unit_id) for c in changed}
        # Прежние цепочки вниз удаляются, дальше — каскадом по parent_day_plan_id
        await self.session.execute(
            delete(DayPlan)
            .where(DayPlan.parent_day_plan_id.in_([c.id for c in changed]))
            .execution_options(synchronize_session=False)
        )
        # Делегировать входящую ячейку дальше — значит принять её
        await self.session.execute(
            update(DayPlan)
            .where(DayPlan.id.in_(ids))
            .values(
                executor_unit_id=executor_unit_id,
                delegation_status=func.coalesce(
                    func.nullif(DayPlan.delegation_status, "pending"), "accepted"
                ),
                version=DayPlan.version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        if executor_unit_id != unit.unit_id:
            child_schedule, _ = await self._get_or_create(executor_unit_id, schedule.month)
            if child_schedule.status == "archived":
                raise ValidationFailedError("График подразделения-исполнителя в архиве")
            await _insert_cells(
                self.session,
                [
                    {
                        "id": uuid7(),
                        "schedule_id": child_schedule.id,
                        "date": c.date,
                        "duty_type_id": c.duty_type_id,
                        "duty_role_id": c.duty_role_id,
                        "origin": "incoming",
                        "parent_day_plan_id": c.id,
                        "executor_unit_id": executor_unit_id,
                        "delegation_status": "pending",
                        "is_pinned": False,
                        "version": 1,
                    }
                    for c in changed
                ],
            )
        audit.record(
            self.session,
            action="day_plan.delegate",
            entity_type="schedule",
            entity_id=schedule.id,
            scope_unit_id=unit.unit_id,
            before={"executors": before},
            after={
                "executor_unit_id": executor_unit_id,
                "cells": len(changed),
                "dropped_assignments": dropped or None,
            },
        )
        add_event(
            self.session,
            "day_plan.delegated",
            "schedule",
            schedule.id,
            {
                "schedule_id": schedule.id,
                "unit_id": unit.unit_id,
                "month": schedule.month,
                "executor_unit_id": executor_unit_id,
                "day_plan_ids": ids,
            },
        )
        if commit:
            await self._commit()
        return len(changed)

    async def accept(self, schedule_id: uuid.UUID, cell_ids: Sequence[uuid.UUID] | None) -> int:
        schedule, unit = await self._schedule(schedule_id, "update")
        stmt = (
            update(DayPlan)
            .where(
                DayPlan.schedule_id == schedule.id,
                DayPlan.origin == "incoming",
                DayPlan.delegation_status == "pending",
            )
            .values(delegation_status="accepted", version=DayPlan.version + 1)
            .returning(DayPlan.id)
            .execution_options(synchronize_session=False)
        )
        if cell_ids is not None:
            await self._cells(schedule, cell_ids)
            stmt = stmt.where(DayPlan.id.in_(set(cell_ids)))
        ids = list((await self.session.execute(stmt)).scalars())
        if not ids:
            return 0
        audit.record(
            self.session,
            action="day_plan.accept",
            entity_type="schedule",
            entity_id=schedule.id,
            scope_unit_id=unit.unit_id,
            after={"accepted": len(ids)},
        )
        add_event(
            self.session,
            "day_plan.accepted",
            "schedule",
            schedule.id,
            {"schedule_id": schedule.id, "unit_id": unit.unit_id, "day_plan_ids": ids},
        )
        await self._commit()
        return len(ids)

    async def pin(self, schedule_id: uuid.UUID, cell_ids: Sequence[uuid.UUID], pinned: bool) -> int:
        """Закрепить выбор исполнителя: автораспределение (фаза 4) его не пересматривает."""
        schedule, unit = await self._schedule(schedule_id, "update")
        cells = [c for c in await self._cells(schedule, cell_ids) if c.is_pinned != pinned]
        if not pinned:
            locked = await locked_cells(self.session, cells, unit.path)
            if locked:
                raise RoleLockedError(locked)
        for c in cells:
            c.is_pinned = pinned
        if not cells:
            return 0
        audit.record(
            self.session,
            action="day_plan.pin" if pinned else "day_plan.unpin",
            entity_type="schedule",
            entity_id=schedule.id,
            scope_unit_id=unit.unit_id,
            after={"cells": len(cells)},
        )
        await self._commit()
        return len(cells)

    async def snapshot(self, schedule_id: uuid.UUID, people: Any, timezone: str) -> dict[str, Any]:
        """Снимок задачи для движка (ADR-0013). Данные — в пределах права чтения графика."""
        from scheduling.snapshot import build_snapshot  # снимок импортирует этот модуль

        schedule, unit = await self._schedule(schedule_id, "read")
        return await build_snapshot(self.session, people, schedule, unit, timezone=timezone)

    # --- статус графика ----------------------------------------------------------------------

    async def pending_in_subtree(
        self, schedule: Schedule, unit: UnitProjection
    ) -> list[PendingWarning]:
        rows = await self.session.execute(
            select(UnitProjection.unit_id, UnitProjection.name, func.count())
            .select_from(DayPlan)
            .join(Schedule, Schedule.id == DayPlan.schedule_id)
            .join(UnitProjection, UnitProjection.unit_id == Schedule.unit_id)
            .where(
                Schedule.month == schedule.month,
                is_descendant_or_self(UnitProjection.path, unit.path),
                DayPlan.delegation_status == "pending",
            )
            .group_by(UnitProjection.unit_id, UnitProjection.name, UnitProjection.path)
            .order_by(UnitProjection.path)
        )
        return [PendingWarning(unit_id=u, unit_name=n, count=c) for u, n, c in rows]

    async def publish(
        self, schedule_id: uuid.UUID, version: int
    ) -> tuple[Schedule, list[PendingWarning]]:
        schedule, unit = await self._schedule(schedule_id, "publish")
        _check_version(schedule.version, version)
        if schedule.status != "draft":
            raise ValidationFailedError("Опубликовать можно только черновик")
        warnings = await self.pending_in_subtree(schedule, unit)
        schedule.status = "published"
        schedule.published_at = dt.datetime.now(dt.UTC)
        schedule.published_by = self.operator.full_name or self.operator.username
        await self._flush()
        audit.record(
            self.session,
            action="schedule.publish",
            entity_type="schedule",
            entity_id=schedule.id,
            scope_unit_id=unit.unit_id,
            before={"status": "draft"},
            after={"status": "published", "pending_in_subtree": sum(w.count for w in warnings)},
        )
        add_event(
            self.session,
            "schedule.published",
            "schedule",
            schedule.id,
            {"schedule_id": schedule.id, "unit_id": unit.unit_id, "month": schedule.month},
        )
        await self._commit()
        return schedule, warnings

    async def archive(self, schedule_id: uuid.UUID, version: int) -> Schedule:
        schedule, unit = await self._schedule(schedule_id, "publish")
        _check_version(schedule.version, version)
        before = schedule.status
        schedule.status = "archived"
        await self._flush()
        audit.record(
            self.session,
            action="schedule.archive",
            entity_type="schedule",
            entity_id=schedule.id,
            scope_unit_id=unit.unit_id,
            before={"status": before},
            after={"status": "archived"},
        )
        add_event(
            self.session,
            "schedule.archived",
            "schedule",
            schedule.id,
            {"schedule_id": schedule.id, "unit_id": unit.unit_id, "month": schedule.month},
        )
        await self._commit()
        return schedule

    async def unarchive(self, schedule_id: uuid.UUID, version: int) -> Schedule:
        """Вернуть архивный график в «опубликован» (суперадминистратор, ADR-0023): например,
        чтобы исправить назначения задним числом. Дальше — как с опубликованным (№36)."""
        self.policy.require(self.operator.roles, "schedule", "unarchive")
        schedule, unit = await self._schedule(schedule_id, "read")
        _check_version(schedule.version, version)
        if schedule.status != "archived":
            raise ValidationFailedError("График не в архиве")
        schedule.status = "published"
        await self._flush()
        audit.record(
            self.session,
            action="schedule.unarchive",
            entity_type="schedule",
            entity_id=schedule.id,
            scope_unit_id=unit.unit_id,
            before={"status": "archived"},
            after={"status": "published"},
        )
        add_event(
            self.session,
            "schedule.unarchived",
            "schedule",
            schedule.id,
            {"schedule_id": schedule.id, "unit_id": unit.unit_id, "month": schedule.month},
        )
        await self._commit()
        return schedule

    async def delete(
        self, schedule_id: uuid.UUID, version: int, *, drop_assignments: bool = False
    ) -> None:
        """Удалить черновик вместе с его ячейками. Переданное дочерним уходит каскадом, как
        при смене решения; график с входящими ячейками удалить нельзя — их передало
        вышестоящее, и вернуть их себе должно оно."""
        schedule, unit = await self._schedule(schedule_id, "create")
        _check_version(schedule.version, version)
        if schedule.status != "draft":
            raise ValidationFailedError("Удалить можно только неопубликованный график")
        incoming = await self.session.scalar(
            select(func.count())
            .select_from(DayPlan)
            .where(DayPlan.schedule_id == schedule.id, DayPlan.origin == "incoming")
        )
        if incoming:
            raise ValidationFailedError(
                f"В график переданы наряды вышестоящего подразделения (ячеек: {incoming}). "
                "Удалить его можно, когда вышестоящее вернёт их себе."
            )
        chain = chain_cte(DayPlan.schedule_id == schedule.id)
        gone = list(
            await self.session.scalars(
                select(Assignment).join(chain, chain.c.id == Assignment.day_plan_id)
            )
        )
        if gone and not drop_assignments:
            raise AssignmentsExistError(
                f"В графике и у подразделений, которым переданы наряды, назначено людей: "
                f"{len(gone)}. Удаление графика снимет эти назначения.",
                details={"assignments": len(gone)},
            )
        await emit_removed(self.session, gone)
        audit.record(
            self.session,
            action="schedule.delete",
            entity_type="schedule",
            entity_id=schedule.id,
            scope_unit_id=unit.unit_id,
            before={"unit_id": unit.unit_id, "month": schedule.month, "status": schedule.status},
            after={"dropped_assignments": len(gone) or None},
        )
        # Ячейки, назначения и цепочки делегирования вниз удаляет каскад БД
        await self.session.delete(schedule)
        await self._commit()

    # --- вспомогательное -----------------------------------------------------------------------

    async def _flush(self) -> None:
        try:
            await self.session.flush()
        except StaleDataError as exc:
            await self.session.rollback()
            raise ConflictError("График уже изменён другим пользователем") from exc

    async def _commit(self) -> None:
        try:
            await self.session.commit()
        except StaleDataError as exc:
            await self.session.rollback()
            raise ConflictError("Данные уже изменены другим пользователем") from exc
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(
                "Ячейки уже изменены другим пользователем. Обновите таблицу."
            ) from exc


def _check_version(current: int, given: int) -> None:
    if current != given:
        raise ConflictError(
            "Данные уже изменены другим пользователем. Обновите страницу.",
            details={"current_version": current},
        )


def assigned_out(a: Assignment, published_at: dt.datetime | None) -> AssignedOut:
    return AssignedOut(
        id=a.id,
        person_id=a.person_id,
        person_name=a.person_name,
        is_pinned=a.is_pinned,
        rest_override=a.rest_override,
        limit_override=a.limit_override,
        override_comment=a.override_comment,
        conflict=a.conflict,
        after_publish=published_at is not None and a.assigned_at > published_at,
    )
