"""Основа сервисов personnel: scope оператора по проекции дерева и общие проверки."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from dutyflow_common.context import Operator
from dutyflow_common.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
)
from dutyflow_common.policy import Policy, default_policy
from dutyflow_common.projections import UnitProjection, unit_path
from dutyflow_common.scope import Scope, in_scope
from personnel.models import Person


class ScopedService:
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

    def _scope(self, resource: str, action: str) -> Scope:
        return self.policy.scope_for(self.operator.roles, resource, action)

    async def _unit(self, unit_id: uuid.UUID) -> UnitProjection:
        unit = await self.session.get(UnitProjection, unit_id)
        if unit is None:
            raise ValidationFailedError("Подразделение не найдено")
        return unit

    async def _require_unit(self, resource: str, action: str, unit_id: uuid.UUID) -> UnitProjection:
        unit = await self._unit(unit_id)
        if not in_scope(unit.path, await self.operator_path(), self._scope(resource, action)):
            raise ForbiddenError("Подразделение вне зоны ответственности оператора")
        return unit

    async def _person(self, person_id: uuid.UUID, resource: str, action: str) -> Person:
        person = await self.session.get(Person, person_id)
        if person is None:
            raise NotFoundError("Человек не найден")
        try:
            await self._require_unit(resource, action, person.unit_id)
        except ValidationFailedError as exc:  # подразделение неизвестно — для оператора «нет»
            raise NotFoundError("Человек не найден") from exc
        return person

    async def _commit(self) -> None:
        try:
            await self.session.commit()
        except StaleDataError as exc:
            await self.session.rollback()
            raise ConflictError("Данные уже изменены другим пользователем") from exc


def check_version(current: int, given: int) -> None:
    if current != given:
        raise ConflictError(
            "Данные уже изменены другим пользователем. Обновите страницу.",
            details={"current_version": current},
        )
