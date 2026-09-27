"""Лимиты нарядов на человека за календарный месяц (open-questions №9, 27, 38).

Оператор задаёт правила для своего поддерева; видит и правила вышестоящих подразделений,
которые действуют на его людей. Применяется самое специфичное правило (`checks.resolve_limit`).
"""

import uuid

from sqlalchemy import or_, select
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
from dutyflow_common.ltree import is_ancestor_or_self
from dutyflow_common.policy import Policy, default_policy
from dutyflow_common.projections import RankProjection, UnitProjection, unit_path
from dutyflow_common.scope import in_scope, scope_clause
from scheduling.models import DutyLimit
from scheduling.refs import RefsLoader
from scheduling.schemas import DutyLimitIn, DutyLimitOut, DutyLimitUpdate


class LimitService:
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

    async def _path(self) -> str:
        if self._op_path is None:
            self._op_path = await unit_path(self.session, self.operator.unit_id)
        return self._op_path

    async def _can(self, action: str, path: str) -> bool:
        scope = self.policy.scope_for(self.operator.roles, "duty_limit", action)
        return in_scope(path, await self._path(), scope)

    async def list_limits(self) -> list[DutyLimitOut]:
        scope = self.policy.require(self.operator.roles, "duty_limit", "read")
        op_path = await self._path()
        rows = await self.session.execute(
            select(DutyLimit, UnitProjection.path, UnitProjection.name, RankProjection.name)
            .join(UnitProjection, UnitProjection.unit_id == DutyLimit.unit_id)
            .outerjoin(RankProjection, RankProjection.rank_id == DutyLimit.rank_id)
            .where(
                or_(
                    scope_clause(UnitProjection.path, op_path, scope),
                    is_ancestor_or_self(UnitProjection.path, op_path),
                )
            )
            .order_by(UnitProjection.path, DutyLimit.created_at)
        )
        return [
            DutyLimitOut(
                **limit.snapshot(),
                id=limit.id,
                unit_name=unit_name,
                rank_name=rank_name,
                version=limit.version,
                can_edit=await self._can("update", path),
            )
            for limit, path, unit_name, rank_name in rows
        ]

    async def _check(self, data: DutyLimitIn, action: str) -> None:
        unit = await self.session.get(UnitProjection, data.unit_id)
        if unit is None:
            raise ValidationFailedError("Подразделение не найдено")
        if not await self._can(action, unit.path):
            raise ForbiddenError("Подразделение вне зоны ответственности оператора")
        if (
            data.rank_id is not None
            and await self.session.get(RankProjection, data.rank_id) is None
        ):
            raise ValidationFailedError("Звание не найдено")
        if data.position_id is not None:
            refs = await self.refs_loader()
            if data.position_id not in refs.positions:
                raise ValidationFailedError("Должность не найдена")

    async def create(self, data: DutyLimitIn) -> DutyLimit:
        await self._check(data, "create")
        limit = DutyLimit(**data.model_dump())
        self.session.add(limit)
        await self.session.flush()
        audit.record(
            self.session,
            action="duty_limit.create",
            entity_type="duty_limit",
            entity_id=limit.id,
            scope_unit_id=limit.unit_id,
            after=limit.snapshot(),
        )
        await self.session.commit()
        return limit

    async def _get(self, limit_id: uuid.UUID) -> DutyLimit:
        limit = await self.session.get(DutyLimit, limit_id)
        if limit is None:
            raise NotFoundError("Лимит не найден")
        unit = await self.session.get(UnitProjection, limit.unit_id)
        if unit is None or not await self._can("update", unit.path):
            raise ForbiddenError("Лимит вышестоящего подразделения можно только просматривать")
        return limit

    async def update(self, limit_id: uuid.UUID, data: DutyLimitUpdate) -> DutyLimit:
        limit = await self._get(limit_id)
        if limit.version != data.version:
            raise ConflictError("Лимит уже изменён другим пользователем. Обновите страницу.")
        await self._check(data, "update")
        before = limit.snapshot()
        for key, value in data.model_dump(exclude={"version"}).items():
            setattr(limit, key, value)
        try:
            await self.session.flush()
        except StaleDataError as exc:
            await self.session.rollback()
            raise ConflictError("Лимит уже изменён другим пользователем") from exc
        audit.record(
            self.session,
            action="duty_limit.update",
            entity_type="duty_limit",
            entity_id=limit.id,
            scope_unit_id=limit.unit_id,
            before=before,
            after=limit.snapshot(),
        )
        await self.session.commit()
        return limit

    async def delete(self, limit_id: uuid.UUID) -> None:
        limit = await self._get(limit_id)
        audit.record(
            self.session,
            action="duty_limit.delete",
            entity_type="duty_limit",
            entity_id=limit.id,
            scope_unit_id=limit.unit_id,
            before=limit.snapshot(),
        )
        await self.session.delete(limit)
        await self.session.commit()
