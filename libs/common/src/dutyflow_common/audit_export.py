"""Внутренняя выгрузка журнала аудита сервиса пачками — для начального заполнения и
перестроения сводного журнала в analytics (ADR-0010, фаза 7b). Записи — в том же виде,
что событие `audit.recorded`, по возрастанию id (uuid7 упорядочен по времени)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dutyflow_common.audit import AuditLog
from dutyflow_common.auth import require_internal
from dutyflow_common.context import service_name
from dutyflow_common.db import get_session


def entry(row: AuditLog) -> dict[str, Any]:
    return {
        "audit_id": row.id,
        "service": service_name(),
        "occurred_at": row.occurred_at,
        "actor_id": row.actor_id,
        "actor_name": row.actor_name,
        "actor_unit_id": row.actor_unit_id,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "scope_unit_id": row.scope_unit_id,
        "before": row.before,
        "after": row.after,
        "comment": row.comment,
        "request_id": row.request_id,
    }


def audit_export_router() -> APIRouter:
    router = APIRouter(
        prefix="/internal", tags=["internal"], dependencies=[Depends(require_internal)]
    )

    @router.get("/audit", summary="Журнал аудита сервиса пачками по возрастанию id")
    async def export_audit(
        session: Annotated[AsyncSession, Depends(get_session)],
        after: Annotated[uuid.UUID | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=5_000)] = 2_000,
    ) -> list[dict[str, Any]]:
        stmt = select(AuditLog).order_by(AuditLog.id).limit(limit)
        if after is not None:
            stmt = stmt.where(AuditLog.id > after)
        return [entry(r) for r in await session.scalars(stmt)]

    return router
