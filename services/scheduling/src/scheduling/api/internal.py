"""Внутренний batch-API для personnel (`docs/architecture.md` §3.3): требования ролей для
проверки при выдаче допуска и полной пересинхронизации локальной копии."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from dutyflow_common.auth import require_internal
from scheduling import facts
from scheduling.api.deps import SessionDep
from scheduling.models import DutyLimit, DutyRole, DutyType
from scheduling.schemas import DutyRoleBatchItem, DutyRolesBatchIn

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_internal)])


@router.post("/duty-roles/batch", response_model=list[DutyRoleBatchItem])
async def duty_roles_batch(data: DutyRolesBatchIn, session: SessionDep) -> list[dict[str, Any]]:
    stmt = select(DutyRole, DutyType).join(DutyType, DutyType.id == DutyRole.duty_type_id)
    if data.role_ids:
        stmt = stmt.where(DutyRole.id.in_(data.role_ids))
    if not data.include_inactive:
        stmt = stmt.where(DutyRole.is_active, DutyType.is_active)
    rows = await session.execute(stmt.order_by(DutyType.id, DutyRole.sort_order, DutyRole.id))
    return [
        {
            "id": role.id,
            "duty_type_id": role.duty_type_id,
            "code": role.code,
            "name": role.name,
            "headcount": role.headcount,
            "sort_order": role.sort_order,
            "min_rank_order": role.min_rank_order,
            "allowed_position_ids": role.allowed_position_ids,
            "attribute_requirements": role.attribute_requirements,
            "assigned_unit_id": role.assigned_unit_id,
            "allowed_category_ids": role.allowed_category_ids,
            "is_active": role.is_active,
            "version": role.version,
            "duty_type": {
                "id": t.id,
                "name": t.name,
                "short_name": t.short_name,
                "owner_unit_id": t.owner_unit_id,
                "is_active": t.is_active,
                "version": t.version,
            },
        }
        for role, t in rows
    ]


@router.get(
    "/assignments/facts",
    summary="Факты нарядов пачками по возрастанию id — для перестроения read-model analytics",
)
async def assignment_facts(
    session: SessionDep,
    after: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=5_000)] = 2_000,
) -> list[dict[str, Any]]:
    return await facts.export(session, after=after, limit=limit)


class RankUsageIn(BaseModel):
    rank_id: uuid.UUID
    order: int


@router.post(
    "/ranks/usage", summary="Роли с этим минимальным званием и лимиты по званию (ADR-0022)"
)
async def rank_usage(data: RankUsageIn, session: SessionDep) -> dict[str, int]:
    # Минимальное звание роли хранится числом старшинства, а не id звания
    roles = await session.scalar(
        select(func.count()).select_from(DutyRole).where(DutyRole.min_rank_order == data.order)
    )
    limits = await session.scalar(
        select(func.count()).select_from(DutyLimit).where(DutyLimit.rank_id == data.rank_id)
    )
    return {"duty_roles": roles or 0, "duty_limits": limits or 0}
