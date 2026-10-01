"""Логика дерева подразделений: scope-фильтрация, создание, изменение, перенос, расформирование,
восстановление и удаление навсегда пустого подразделения (ADR-0023).

Все проверки прав — через `default_policy` из libs/common; поддерево — предикаты `ltree` (ADR-0003).
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import case, cast, func, literal, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from dutyflow_common import audit
from dutyflow_common.context import Operator
from dutyflow_common.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
)
from dutyflow_common.ltree import Ltree, is_descendant_or_self
from dutyflow_common.outbox import add_event
from dutyflow_common.policy import Policy, default_policy
from dutyflow_common.scope import Scope, in_scope, scope_clause
from dutyflow_common.usage import UsageCheck, ensure_unused
from org.models import Unit, UnitType, unit_node_no_seq
from org.schemas import UnitCreate, UnitMove, UnitOut, UnitPermissions, UnitUpdate

RESOURCE = "unit"


def depth(path: str) -> int:
    return path.count(".") + 1


class UnitService:
    def __init__(
        self, session: AsyncSession, operator: Operator, policy: Policy = default_policy
    ) -> None:
        self.session = session
        self.operator = operator
        self.policy = policy
        self._operator_path: str | None = None

    # --- scope ---------------------------------------------------------------------------

    async def operator_path(self) -> str:
        if self._operator_path is None:
            path = await self.session.scalar(
                select(Unit.path).where(Unit.id == self.operator.unit_id, Unit.is_active)
            )
            if path is None:
                raise ForbiddenError("Подразделение оператора не найдено или расформировано")
            self._operator_path = path
        return self._operator_path

    def _scope(self, action: str) -> Scope:
        return self.policy.scope_for(self.operator.roles, RESOURCE, action)

    async def _require(self, action: str, unit: Unit) -> None:
        if not in_scope(unit.path, await self.operator_path(), self._scope(action)):
            raise ForbiddenError("Подразделение вне зоны ответственности оператора")

    async def permissions(self, unit: Unit) -> UnitPermissions:
        op_path = await self.operator_path()
        active = unit.is_active
        not_root = unit.parent_id is not None
        return UnitPermissions(
            update=active and in_scope(unit.path, op_path, self._scope("update")),
            move=active and not_root and in_scope(unit.path, op_path, self._scope("move")),
            delete=active and not_root and in_scope(unit.path, op_path, self._scope("delete")),
            create_child=active and in_scope(unit.path, op_path, self._scope("create")),
            restore=not active and in_scope(unit.path, op_path, self._scope("restore")),
            purge=not_root and in_scope(unit.path, op_path, self._scope("purge")),
        )

    async def to_out(self, unit: Unit) -> UnitOut:
        return UnitOut(
            id=unit.id,
            parent_id=unit.parent_id,
            unit_type_id=unit.unit_type_id,
            name=unit.name,
            short_name=unit.short_name,
            path=unit.path,
            depth=depth(unit.path),
            sort_order=unit.sort_order,
            is_active=unit.is_active,
            version=unit.version,
            permissions=await self.permissions(unit),
        )

    # --- чтение --------------------------------------------------------------------------

    async def list_visible(self, *, include_inactive: bool = False) -> Sequence[Unit]:
        """Все подразделения в scope оператора — плоский список для дерева в UI."""
        scope = self.policy.require(self.operator.roles, RESOURCE, "read")
        stmt = select(Unit).where(scope_clause(Unit.path, await self.operator_path(), scope))
        if not include_inactive:
            stmt = stmt.where(Unit.is_active)
        stmt = stmt.order_by(func.nlevel(Unit.path), Unit.sort_order, Unit.name)
        return (await self.session.scalars(stmt)).all()

    async def get(self, unit_id: uuid.UUID, *, action: str = "read") -> Unit:
        unit = await self.session.get(Unit, unit_id)
        if unit is None:
            raise NotFoundError("Подразделение не найдено")
        await self._require(action, unit)
        return unit

    async def subtree(self, unit_id: uuid.UUID) -> Sequence[Unit]:
        root = await self.get(unit_id)
        stmt = (
            select(Unit)
            .where(is_descendant_or_self(Unit.path, root.path), Unit.is_active)
            .order_by(func.nlevel(Unit.path), Unit.sort_order, Unit.name)
        )
        return (await self.session.scalars(stmt)).all()

    async def ancestors(self, unit_id: uuid.UUID) -> Sequence[Unit]:
        """Цепочка от корня до узла (без него самого). Предки вне scope не скрываются:
        оператору нужен путь «академия → факультет → курс», имена вышестоящих не секретны."""
        unit = await self.get(unit_id)
        stmt = (
            select(Unit)
            .where(Unit.path.op("@>")(cast(literal(unit.path), Ltree())), Unit.id != unit.id)
            .order_by(func.nlevel(Unit.path))
        )
        return (await self.session.scalars(stmt)).all()

    # --- изменение -----------------------------------------------------------------------

    async def _unit_type(self, type_id: uuid.UUID) -> UnitType:
        unit_type = await self.session.get(UnitType, type_id)
        if unit_type is None:
            raise ValidationFailedError("Тип подразделения не найден")
        return unit_type

    async def _check_hierarchy(self, parent: Unit, child_type: UnitType) -> None:
        parent_type = await self._unit_type(parent.unit_type_id)
        if not parent_type.can_have_children:
            raise ValidationFailedError(
                f"Подразделение типа «{parent_type.name}» не может иметь дочерних"
            )
        if child_type.level <= parent_type.level:
            raise ValidationFailedError(
                f"Тип «{child_type.name}» должен быть ниже по иерархии, чем «{parent_type.name}»"
            )

    async def create(self, data: UnitCreate) -> Unit:
        parent = await self.get(data.parent_id, action="create")
        if not parent.is_active:
            raise ValidationFailedError("Нельзя создать подразделение в расформированном")
        unit_type = await self._unit_type(data.unit_type_id)
        await self._check_hierarchy(parent, unit_type)
        await self._ensure_name_free(parent.id, data.name)

        node_no = await self.session.scalar(select(unit_node_no_seq.next_value()))
        unit = Unit(
            node_no=node_no,
            parent_id=parent.id,
            unit_type_id=unit_type.id,
            name=data.name.strip(),
            short_name=data.short_name,
            sort_order=data.sort_order,
            path=f"{parent.path}.{node_no}",
            is_active=True,
        )
        self.session.add(unit)
        await self.session.flush()
        audit.record(
            self.session,
            action="unit.create",
            entity_type=RESOURCE,
            entity_id=unit.id,
            scope_unit_id=unit.id,
            after=unit.snapshot(),
        )
        add_event(self.session, "unit.created", RESOURCE, unit.id, _event(unit))
        await self._commit()
        return unit

    async def update(self, unit_id: uuid.UUID, data: UnitUpdate) -> Unit:
        unit = await self.get(unit_id, action="update")
        self._check_version(unit, data.version)
        before = unit.snapshot()
        if data.name is not None and data.name.strip() != unit.name:
            if unit.parent_id is not None:
                await self._ensure_name_free(unit.parent_id, data.name, exclude=unit.id)
            unit.name = data.name.strip()
        if "short_name" in data.model_fields_set:
            unit.short_name = data.short_name
        if data.sort_order is not None:
            unit.sort_order = data.sort_order
        if data.unit_type_id is not None and data.unit_type_id != unit.unit_type_id:
            new_type = await self._unit_type(data.unit_type_id)
            if unit.parent_id is not None:
                parent = await self.session.get(Unit, unit.parent_id)
                assert parent is not None
                await self._check_hierarchy(parent, new_type)
            unit.unit_type_id = new_type.id
        await self._flush()  # version растёт при flush — событие должно нести новую версию
        entry = audit.record(
            self.session,
            action="unit.update",
            entity_type=RESOURCE,
            entity_id=unit.id,
            scope_unit_id=unit.id,
            before=before,
            after=unit.snapshot(),
        )
        if entry is not None:
            add_event(self.session, "unit.updated", RESOURCE, unit.id, _event(unit))
        await self._commit()
        return unit

    async def move(self, unit_id: uuid.UUID, data: UnitMove) -> Unit:
        unit = await self.get(unit_id, action="move")
        self._check_version(unit, data.version)
        if unit.parent_id is None:
            raise ValidationFailedError("Корневое подразделение нельзя перенести")
        new_parent = await self.get(data.new_parent_id, action="create")
        if not new_parent.is_active:
            raise ValidationFailedError("Нельзя перенести в расформированное подразделение")
        if in_scope(new_parent.path, unit.path, Scope.OWN_AND_ALL_DESCENDANTS):
            raise ValidationFailedError("Нельзя перенести подразделение внутрь самого себя")
        if new_parent.id == unit.parent_id:
            return unit
        await self._check_hierarchy(new_parent, await self._unit_type(unit.unit_type_id))
        await self._ensure_name_free(new_parent.id, unit.name, exclude=unit.id)

        before = unit.snapshot()
        old_path = unit.path
        new_path = f"{new_parent.path}.{unit.node_no}"
        # Поддерево переписывается одним UPDATE, без рекурсии (ADR-0003):
        # потомки получают new_path || subpath(path, nlevel(old_path)), сам узел — new_path
        # (subpath с offset = nlevel в PostgreSQL даёт ошибку «invalid positions»).
        old_ltree = cast(literal(old_path), Ltree())
        new_ltree = cast(literal(new_path), Ltree())
        tail = func.subpath(Unit.path, func.nlevel(old_ltree))
        new_value = case(
            (Unit.path == old_ltree, new_ltree),
            else_=new_ltree.op("||", return_type=Ltree())(tail),
        )
        result = await self.session.execute(
            update(Unit)
            .where(is_descendant_or_self(Unit.path, old_path))
            .values(path=new_value)
            .execution_options(synchronize_session=False)
        )
        moved = int(getattr(result, "rowcount", 0))
        # parent_id и version меняем через ORM, чтобы сработала оптимистичная блокировка.
        unit.parent_id = new_parent.id
        await self.session.flush()
        await self.session.refresh(unit)
        audit.record(
            self.session,
            action="unit.move",
            entity_type=RESOURCE,
            entity_id=unit.id,
            scope_unit_id=unit.id,
            before=before,
            after=unit.snapshot(),
        )
        add_event(
            self.session,
            "unit.moved",
            RESOURCE,
            unit.id,
            {**_event(unit), "old_path": old_path, "new_path": new_path, "moved_count": moved},
        )
        await self._commit()
        return unit

    async def deactivate(self, unit_id: uuid.UUID, version: int) -> Unit:
        """Расформирование: узел не удаляется физически (на него ссылаются люди и графики)."""
        unit = await self.get(unit_id, action="delete")
        self._check_version(unit, version)
        if unit.parent_id is None:
            raise ValidationFailedError("Корневое подразделение нельзя расформировать")
        has_children = await self.session.scalar(
            select(func.count()).where(Unit.parent_id == unit.id, Unit.is_active)
        )
        if has_children:
            raise ConflictError("Сначала расформируйте или перенесите дочерние подразделения")
        before = unit.snapshot()
        unit.is_active = False
        await self._flush()
        audit.record(
            self.session,
            action="unit.deactivate",
            entity_type=RESOURCE,
            entity_id=unit.id,
            scope_unit_id=unit.id,
            before=before,
            after=unit.snapshot(),
        )
        add_event(self.session, "unit.deleted", RESOURCE, unit.id, _event(unit))
        await self._commit()
        return unit

    async def restore(self, unit_id: uuid.UUID, version: int) -> Unit:
        """Вернуть расформированное подразделение на прежнее место в дереве."""
        unit = await self.get(unit_id, action="restore")
        self._check_version(unit, version)
        if unit.is_active:
            raise ValidationFailedError("Подразделение не расформировано")
        parent = await self.session.get(Unit, unit.parent_id) if unit.parent_id else None
        if parent is not None and not parent.is_active:
            raise ConflictError(f"Сначала восстановите вышестоящее подразделение «{parent.name}»")
        if unit.parent_id is not None:
            await self._ensure_name_free(unit.parent_id, unit.name, exclude=unit.id)
        before = unit.snapshot()
        unit.is_active = True
        await self._flush()
        audit.record(
            self.session,
            action="unit.restore",
            entity_type=RESOURCE,
            entity_id=unit.id,
            scope_unit_id=unit.id,
            before=before,
            after=unit.snapshot(),
        )
        add_event(self.session, "unit.restored", RESOURCE, unit.id, _event(unit))
        await self._commit()
        return unit

    async def purge(self, unit_id: uuid.UUID, version: int, usage: UsageCheck) -> None:
        """Удалить навсегда подразделение, на которое ничего не ссылается (ADR-0023).

        Ссылки ищутся у personnel (люди, включая архивных), scheduling (наряды, роли, графики,
        ячейки, лимиты) и auth-admin (операторы). Дочерние, даже расформированные, тоже мешают:
        их путь в ltree начинается с пути удаляемого узла.
        """
        unit = await self.get(unit_id, action="purge")
        self._check_version(unit, version)
        if unit.parent_id is None:
            raise ValidationFailedError("Корневое подразделение удалить нельзя")
        children = await self.session.scalar(
            select(func.count()).select_from(Unit).where(Unit.parent_id == unit.id)
        )
        found: dict[str, Any] = {"child_units": children or 0}
        found |= await usage("unit", {"id": str(unit.id)})
        ensure_unused(
            f"Подразделение «{unit.name}»",
            found,
            "Его можно только расформировать." if unit.is_active else "",
        )
        audit.record(
            self.session,
            action="unit.purge",
            entity_type=RESOURCE,
            entity_id=unit.id,
            scope_unit_id=unit.parent_id,
            before=unit.snapshot(),
        )
        add_event(
            self.session, "unit.purged", RESOURCE, unit.id, {"unit_id": unit.id, "path": unit.path}
        )
        await self.session.delete(unit)
        await self._commit()

    # --- вспомогательное -----------------------------------------------------------------

    @staticmethod
    def _check_version(unit: Unit, version: int) -> None:
        if unit.version != version:
            raise ConflictError(
                "Подразделение уже изменено другим пользователем. Обновите страницу.",
                details={"current_version": unit.version},
            )

    async def _ensure_name_free(
        self, parent_id: uuid.UUID, name: str, *, exclude: uuid.UUID | None = None
    ) -> None:
        stmt = select(Unit.id).where(
            Unit.parent_id == parent_id, Unit.name == name.strip(), Unit.is_active
        )
        if exclude is not None:
            stmt = stmt.where(Unit.id != exclude)
        if await self.session.scalar(stmt) is not None:
            raise ConflictError("Подразделение с таким названием уже есть у этого родителя")

    async def _flush(self) -> None:
        try:
            await self.session.flush()
        except StaleDataError as exc:
            await self.session.rollback()
            raise ConflictError("Подразделение уже изменено другим пользователем") from exc

    async def _commit(self) -> None:
        try:
            await self.session.commit()
        except StaleDataError as exc:
            await self.session.rollback()
            raise ConflictError("Подразделение уже изменено другим пользователем") from exc


def _event(unit: Unit) -> dict[str, object]:
    return {
        "unit_id": unit.id,
        "parent_id": unit.parent_id,
        "unit_type_id": unit.unit_type_id,
        "name": unit.name,
        "short_name": unit.short_name,
        "path": unit.path,
        "is_active": unit.is_active,
        "version": unit.version,
    }
