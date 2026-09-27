"""Типы нарядов и роли: видимость по дереву, создание, изменение, проверка требований ролей.

Видимость: оператор видит наряды подразделений своего scope и наряды вышестоящих
подразделений на пути от корня до своего — их роли делегируются вниз, и допуски к ним
выдают нижестоящие операторы (ADR-0009). Менять можно только наряды своего scope.
Все изменения — с аудитом (ADR-0010) и событиями `duty_type.changed` / `duty_role.changed`,
по которым personnel держит локальную копию требований.
"""

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import StaleDataError

from dutyflow_common import audit
from dutyflow_common.context import Operator
from dutyflow_common.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
)
from dutyflow_common.ltree import is_ancestor_or_self, is_descendant_or_self
from dutyflow_common.outbox import add_event
from dutyflow_common.policy import Policy, default_policy
from dutyflow_common.projections import RankProjection, UnitProjection, unit_path
from dutyflow_common.requirements import validate_requirement
from dutyflow_common.scope import in_scope, scope_clause
from scheduling.models import DutyRole, DutyType
from scheduling.refs import PersonnelRefs, RefsLoader
from scheduling.schemas import (
    DutyRoleIn,
    DutyRoleOut,
    DutyRoleUpdate,
    DutyTypeCreate,
    DutyTypeOut,
    DutyTypeUpdate,
)

NAME_CONSTRAINT = "uq_duty_type_owner_name_active"
ROLE_CODE_CONSTRAINT = "uq_duty_role_duty_type_id"


class DutyTypeService:
    def __init__(
        self,
        session: AsyncSession,
        operator: Operator,
        refs_loader: RefsLoader,
        policy: Policy = default_policy,
    ) -> None:
        self.session = session
        self.operator = operator
        self.refs_loader = refs_loader
        self.policy = policy
        self._op_path: str | None = None
        self._refs: PersonnelRefs | None = None

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
        scope = self.policy.scope_for(self.operator.roles, "duty_type", action)
        return in_scope(path, await self.operator_path(), scope)

    # --- чтение ------------------------------------------------------------------------------

    async def _visible(self) -> Any:  # Select с четырьмя колонками; точный тип громоздок
        scope = self.policy.require(self.operator.roles, "duty_type", "read")
        op_path = await self.operator_path()
        owner = aliased(UnitProjection)
        assigned = aliased(UnitProjection)
        return (
            select(DutyType, owner.path, owner.name, assigned.name)
            .join(owner, owner.unit_id == DutyType.owner_unit_id)
            .outerjoin(assigned, assigned.unit_id == DutyType.assigned_unit_id)
            .where(
                or_(
                    scope_clause(owner.path, op_path, scope),
                    is_ancestor_or_self(owner.path, op_path),
                )
            )
        ), owner

    async def list_types(
        self, *, include_inactive: bool = False, unit_id: uuid.UUID | None = None
    ) -> list[DutyTypeOut]:
        """Видимые наряды. `unit_id` — только наряды, которые касаются этого подразделения:
        его собственные и вышестоящих (их роли могут прийти к нему по делегированию)."""
        stmt, owner = await self._visible()
        if unit_id is not None:
            unit = await self._unit(unit_id)
            stmt = stmt.where(is_ancestor_or_self(owner.path, unit.path))
        if not include_inactive:
            stmt = stmt.where(DutyType.is_active)
        rows = (await self.session.execute(stmt.order_by(owner.path, DutyType.name))).all()
        return await self._out(rows)

    async def get(self, type_id: uuid.UUID) -> DutyTypeOut:
        stmt, _ = await self._visible()
        row = (await self.session.execute(stmt.where(DutyType.id == type_id))).first()
        if row is None:
            raise NotFoundError("Тип наряда не найден")
        return (await self._out([row]))[0]

    async def _out(self, rows: Any) -> list[DutyTypeOut]:
        ids = [r[0].id for r in rows]
        roles: dict[uuid.UUID, list[DutyRoleOut]] = defaultdict(list)
        if ids:
            for role in await self.session.scalars(
                select(DutyRole)
                .where(DutyRole.duty_type_id.in_(ids))
                .order_by(DutyRole.sort_order, DutyRole.name)
            ):
                roles[role.duty_type_id].append(DutyRoleOut.model_validate(role))
        result = []
        for t, owner_path, owner_name, assigned_name in rows:
            result.append(
                DutyTypeOut(
                    id=t.id,
                    name=t.name,
                    short_name=t.short_name,
                    owner_unit_id=t.owner_unit_id,
                    owner_unit_name=owner_name,
                    assigned_unit_id=t.assigned_unit_id,
                    assigned_unit_name=assigned_name,
                    start_time=t.start_time,
                    duration_minutes=t.duration_minutes,
                    rest_hours=t.rest_hours,
                    load_weight=t.load_weight,
                    is_active=t.is_active,
                    version=t.version,
                    roles=roles.get(t.id, []),
                    can_edit=await self._can("update", owner_path),
                )
            )
        return result

    # --- типы ----------------------------------------------------------------------------------

    async def _check_assigned(self, owner: UnitProjection, assigned_id: uuid.UUID | None) -> None:
        """Закреплённое подразделение — внутри поддерева владельца (сам владелец или ниже)."""
        if assigned_id is None:
            return
        unit = await self.session.scalar(
            select(UnitProjection).where(
                UnitProjection.unit_id == assigned_id,
                is_descendant_or_self(UnitProjection.path, owner.path),
            )
        )
        if unit is None:
            raise ValidationFailedError(
                "Закреплённое подразделение должно входить в подразделение-владельца наряда"
            )
        if not unit.is_active:
            raise ValidationFailedError("Закреплённое подразделение расформировано")

    async def _type_for_update(self, type_id: uuid.UUID) -> tuple[DutyType, UnitProjection]:
        duty_type = await self.session.get(DutyType, type_id)
        if duty_type is None:
            raise NotFoundError("Тип наряда не найден")
        owner = await self._unit(duty_type.owner_unit_id)
        if not await self._can("update", owner.path):
            op_path = await self.operator_path()
            visible = await self._can("read", owner.path) or _is_prefix(owner.path, op_path)
            if not visible:
                raise NotFoundError("Тип наряда не найден")
            raise ForbiddenError("Наряд другого подразделения можно только просматривать")
        return duty_type, owner

    async def create(self, data: DutyTypeCreate) -> DutyType:
        self.policy.require(self.operator.roles, "duty_type", "create")
        owner = await self._unit(data.owner_unit_id)
        if not await self._can("create", owner.path):
            raise ForbiddenError("Подразделение вне зоны ответственности оператора")
        if not owner.is_active:
            raise ValidationFailedError("Подразделение расформировано")
        await self._check_assigned(owner, data.assigned_unit_id)

        duty_type = DutyType(**data.model_dump(exclude={"roles"}), is_active=True)
        self.session.add(duty_type)
        await self.session.flush()
        self._record_type("duty_type.create", duty_type, before=None)
        codes: set[str] = set()
        for order, role_in in enumerate(data.roles):
            if role_in.sort_order == 0:
                role_in.sort_order = order
            await self._new_role(duty_type, owner, role_in, codes)
        await self._commit()
        return duty_type

    async def update(self, type_id: uuid.UUID, data: DutyTypeUpdate) -> DutyType:
        duty_type, owner = await self._type_for_update(type_id)
        _check_version(duty_type.version, data.version)
        await self._check_assigned(owner, data.assigned_unit_id)
        before = duty_type.snapshot()
        for key, value in data.model_dump(exclude={"version"}).items():
            setattr(duty_type, key, value)
        await self._flush()
        self._record_type("duty_type.update", duty_type, before=before)
        await self._commit()
        return duty_type

    def _record_type(self, action: str, t: DutyType, *, before: dict[str, Any] | None) -> None:
        changed = audit.record(
            self.session,
            action=action,
            entity_type="duty_type",
            entity_id=t.id,
            scope_unit_id=t.owner_unit_id,
            before=before,
            after=t.snapshot(),
        )
        if changed is not None:
            add_event(
                self.session,
                "duty_type.changed",
                "duty_type",
                t.id,
                {"id": t.id, **t.snapshot(), "version": t.version},
            )

    # --- роли ----------------------------------------------------------------------------------

    async def _refs_cached(self) -> PersonnelRefs:
        if self._refs is None:
            self._refs = await self.refs_loader()
        return self._refs

    async def _validate_role(self, data: DutyRoleIn, previous: DutyRole | None) -> None:
        if data.min_rank_order is not None:
            exists = await self.session.scalar(
                select(RankProjection.rank_id).where(RankProjection.order == data.min_rank_order)
            )
            if exists is None:
                raise ValidationFailedError("Звание для минимального требования не найдено")
        if not data.allowed_position_ids and not data.attribute_requirements:
            return
        refs = await self._refs_cached()
        old_positions = set(previous.allowed_position_ids or []) if previous else set()
        for pid in data.allowed_position_ids or []:
            active = refs.positions.get(pid)
            if active is None or (not active and pid not in old_positions):
                raise ValidationFailedError("Должность из требований роли не найдена")
        old_codes = {r["code"] for r in previous.attribute_requirements} if previous else set()
        for req in data.attribute_requirements:
            definition = refs.attributes.get(req.code)
            if definition is None or (not definition.is_active and req.code not in old_codes):
                raise ValidationFailedError(f"Характеристика «{req.code}» не найдена")
            error = validate_requirement(
                req, definition.name, definition.value_type, definition.enum_options
            )
            if error:
                raise ValidationFailedError(error)

    @staticmethod
    def _role_values(data: DutyRoleIn) -> dict[str, Any]:
        return {
            "name": data.name.strip(),
            "headcount": data.headcount,
            "sort_order": data.sort_order,
            "min_rank_order": data.min_rank_order,
            "allowed_position_ids": data.allowed_position_ids,
            "attribute_requirements": [r.model_dump() for r in data.attribute_requirements],
            "is_active": data.is_active,
        }

    async def _new_role(
        self, duty_type: DutyType, owner: UnitProjection, data: DutyRoleIn, codes: set[str]
    ) -> DutyRole:
        await self._validate_role(data, None)
        if not codes:
            codes |= set(
                await self.session.scalars(
                    select(DutyRole.code).where(DutyRole.duty_type_id == duty_type.id)
                )
            )
        code = data.code or _next_code(codes)
        if code in codes:
            raise ConflictError(f"Роль с кодом «{code}» в этом наряде уже есть")
        codes.add(code)
        role = DutyRole(duty_type_id=duty_type.id, code=code, **self._role_values(data))
        self.session.add(role)
        await self.session.flush()
        self._record_role("duty_role.create", role, owner, before=None)
        return role

    async def add_role(self, type_id: uuid.UUID, data: DutyRoleIn) -> DutyRole:
        duty_type, owner = await self._type_for_update(type_id)
        role = await self._new_role(duty_type, owner, data, set())
        await self._commit()
        return role

    async def update_role(self, role_id: uuid.UUID, data: DutyRoleUpdate) -> DutyRole:
        role = await self.session.get(DutyRole, role_id)
        if role is None:
            raise NotFoundError("Роль не найдена")
        _, owner = await self._type_for_update(role.duty_type_id)
        _check_version(role.version, data.version)
        await self._validate_role(data, role)
        before = role.snapshot()
        if data.code and data.code != role.code:
            role.code = data.code
        for key, value in self._role_values(data).items():
            setattr(role, key, value)
        await self._flush()
        self._record_role("duty_role.update", role, owner, before=before)
        await self._commit()
        return role

    def _record_role(
        self, action: str, role: DutyRole, owner: UnitProjection, *, before: dict[str, Any] | None
    ) -> None:
        changed = audit.record(
            self.session,
            action=action,
            entity_type="duty_role",
            entity_id=role.id,
            scope_unit_id=owner.unit_id,
            before=before,
            after=role.snapshot(),
        )
        if changed is not None:
            add_event(
                self.session,
                "duty_role.changed",
                "duty_role",
                role.id,
                {"id": role.id, **role.snapshot(), "version": role.version},
            )

    # --- вспомогательное -----------------------------------------------------------------------

    async def _flush(self) -> None:
        try:
            await self.session.flush()
        except StaleDataError as exc:
            await self.session.rollback()
            raise ConflictError("Данные уже изменены другим пользователем") from exc
        except IntegrityError as exc:
            await self.session.rollback()
            raise _integrity(exc) from exc

    async def _commit(self) -> None:
        try:
            await self.session.commit()
        except StaleDataError as exc:
            await self.session.rollback()
            raise ConflictError("Данные уже изменены другим пользователем") from exc
        except IntegrityError as exc:
            await self.session.rollback()
            raise _integrity(exc) from exc


def _integrity(exc: IntegrityError) -> ConflictError:
    text = str(exc.orig)
    if NAME_CONSTRAINT in text:
        return ConflictError("У подразделения уже есть действующий наряд с таким названием")
    if ROLE_CODE_CONSTRAINT in text:
        return ConflictError("Роль с таким кодом в этом наряде уже есть")
    return ConflictError("Операция нарушает ограничение целостности данных")


def _is_prefix(ancestor: str, path: str) -> bool:
    a, p = ancestor.split("."), path.split(".")
    return p[: len(a)] == a


def _next_code(taken: set[str]) -> str:
    n = len(taken) + 1
    while f"role{n}" in taken:
        n += 1
    return f"role{n}"


def _check_version(current: int, given: int) -> None:
    if current != given:
        raise ConflictError(
            "Данные уже изменены другим пользователем. Обновите страницу.",
            details={"current_version": current},
        )
