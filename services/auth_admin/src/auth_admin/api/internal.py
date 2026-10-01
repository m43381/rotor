"""Внутренний API auth-admin для других сервисов (`X-Internal-Token`)."""

from fastapi import APIRouter, Depends, Request

from dutyflow_common.auth import require_internal
from dutyflow_common.usage import UsageIn

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_internal)])


@router.post(
    "/usage/{kind}",
    summary="Операторы, привязанные к подразделению, перед его удалением (ADR-0023)",
)
async def usage(kind: str, data: UsageIn, request: Request) -> dict[str, int]:
    if kind != "unit":
        return {}
    operators = await request.app.state.keycloak.count_with_attribute("unit_id", str(data.id))
    return {"operators": operators}
