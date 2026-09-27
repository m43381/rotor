"""История изменений (ADR-0010): оператор видит записи своего поддерева, записи
справочников без подразделения — только суперадминистратор."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from dutyflow_common.audit import AuditLog
from dutyflow_common.pagination import Page, PageParams, page_params
from dutyflow_common.policy import default_policy
from dutyflow_common.projections import UnitProjection
from dutyflow_common.scope import Scope, scope_clause
from scheduling.api.deps import DutyTypeServiceDep, OperatorDep, SessionDep
from scheduling.schemas import AuditEntryOut

router = APIRouter(tags=["audit"])


@router.get("/audit", response_model=Page[AuditEntryOut])
async def list_audit(
    session: SessionDep,
    operator: OperatorDep,
    svc: DutyTypeServiceDep,
    page: Annotated[PageParams, Depends(page_params)],
    entity_type: Annotated[str | None, Query()] = None,
    entity_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Page[AuditEntryOut]:
    scope = default_policy.require(operator.roles, "audit", "read")
    stmt = select(AuditLog)
    if scope is not Scope.ALL:
        stmt = stmt.join(UnitProjection, UnitProjection.unit_id == AuditLog.scope_unit_id).where(
            scope_clause(UnitProjection.path, await svc.operator_path(), scope)
        )
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = await session.scalars(
        stmt.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
        .limit(page.limit)
        .offset(page.offset)
    )
    return Page(
        items=[AuditEntryOut.model_validate(r) for r in rows],
        total=total or 0,
        limit=page.limit,
        offset=page.offset,
    )
