"""Внутренний batch-API для personnel (`docs/architecture.md` §3.3): требования ролей для
проверки при выдаче допуска и полной пересинхронизации локальной копии."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import any_, func, select

from dutyflow_common.auth import require_internal
from dutyflow_common.usage import UsageIn
from scheduling import facts
from scheduling.api.deps import SessionDep
from scheduling.models import Assignment, DayPlan, DutyLimit, DutyRole, DutyType, Schedule
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


@router.post(
    "/usage/{kind}", summary="Ссылки на чужую запись перед её удалением (ADR-0022, ADR-0023)"
)
async def usage(kind: str, data: UsageIn, session: SessionDep) -> dict[str, int]:
    """Где в scheduling упоминается запись org или personnel. Неизвестный вид — пустой ответ."""

    async def count(model: Any, *where: Any) -> int:
        return await session.scalar(select(func.count()).select_from(model).where(*where)) or 0

    rid = data.id
    if kind == "rank":
        # Минимальное звание роли хранится числом старшинства, а не id звания
        return {
            "duty_roles": await count(DutyRole, DutyRole.min_rank_order == data.order),
            "duty_limits": await count(DutyLimit, DutyLimit.rank_id == rid),
        }
    if kind == "position":
        return {
            "duty_roles": await count(DutyRole, rid == any_(DutyRole.allowed_position_ids)),
            "duty_limits": await count(DutyLimit, DutyLimit.position_id == rid),
        }
    if kind == "person_category":
        return {"duty_roles": await count(DutyRole, rid == any_(DutyRole.allowed_category_ids))}
    if kind == "attribute_definition":
        # Требования ролей ссылаются на характеристику по коду
        req = DutyRole.attribute_requirements.contains([{"code": data.code}])
        return {"duty_roles": await count(DutyRole, req)}
    if kind == "unit":
        return {
            "duty_types": await count(DutyType, DutyType.owner_unit_id == rid),
            "duty_roles": await count(DutyRole, DutyRole.assigned_unit_id == rid),
            "schedules": await count(Schedule, Schedule.unit_id == rid),
            "day_plans": await count(DayPlan, DayPlan.executor_unit_id == rid),
            "duty_limits": await count(DutyLimit, DutyLimit.unit_id == rid),
        }
    if kind == "person":
        return {"assignments": await count(Assignment, Assignment.person_id == rid)}
    return {}
