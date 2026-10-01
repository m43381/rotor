"""Подразделения: дерево в scope оператора и операции над ним."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from org.api.deps import UnitServiceDep
from org.schemas import MeOut, UnitCreate, UnitMove, UnitOut, UnitUpdate

router = APIRouter(tags=["units"])


@router.get("/me", response_model=MeOut, summary="Текущий оператор и его подразделение")
async def me(svc: UnitServiceDep) -> MeOut:
    unit = await svc.get(svc.operator.unit_id)
    op = svc.operator
    return MeOut(
        subject=op.subject,
        username=op.username,
        full_name=op.full_name,
        roles=sorted(r.value for r in op.roles),
        unit=await svc.to_out(unit),
    )


@router.get("/units", response_model=list[UnitOut], summary="Все подразделения в scope оператора")
async def list_units(
    svc: UnitServiceDep,
    include_inactive: Annotated[bool, Query()] = False,
) -> list[UnitOut]:
    return [await svc.to_out(u) for u in await svc.list_visible(include_inactive=include_inactive)]


@router.post("/units", response_model=UnitOut, status_code=201)
async def create_unit(data: UnitCreate, svc: UnitServiceDep) -> UnitOut:
    return await svc.to_out(await svc.create(data))


@router.get("/units/{unit_id}", response_model=UnitOut)
async def get_unit(unit_id: uuid.UUID, svc: UnitServiceDep) -> UnitOut:
    return await svc.to_out(await svc.get(unit_id))


@router.patch("/units/{unit_id}", response_model=UnitOut)
async def update_unit(unit_id: uuid.UUID, data: UnitUpdate, svc: UnitServiceDep) -> UnitOut:
    return await svc.to_out(await svc.update(unit_id, data))


@router.post("/units/{unit_id}/move", response_model=UnitOut, summary="Перенос поддерева")
async def move_unit(unit_id: uuid.UUID, data: UnitMove, svc: UnitServiceDep) -> UnitOut:
    return await svc.to_out(await svc.move(unit_id, data))


@router.delete("/units/{unit_id}", response_model=UnitOut, summary="Расформировать")
async def deactivate_unit(
    unit_id: uuid.UUID, version: Annotated[int, Query()], svc: UnitServiceDep
) -> UnitOut:
    return await svc.to_out(await svc.deactivate(unit_id, version))


@router.post(
    "/units/{unit_id}/restore",
    response_model=UnitOut,
    summary="Восстановить расформированное подразделение (ADR-0023)",
)
async def restore_unit(
    unit_id: uuid.UUID, version: Annotated[int, Query()], svc: UnitServiceDep
) -> UnitOut:
    return await svc.to_out(await svc.restore(unit_id, version))


@router.post(
    "/units/{unit_id}/purge",
    status_code=204,
    summary="Удалить навсегда, если на подразделение ничего не ссылается (ADR-0023)",
)
async def purge_unit(
    unit_id: uuid.UUID, version: Annotated[int, Query()], request: Request, svc: UnitServiceDep
) -> Response:
    await svc.purge(unit_id, version, request.app.state.usage)
    return Response(status_code=204)


@router.get("/units/{unit_id}/subtree", response_model=list[UnitOut])
async def subtree(unit_id: uuid.UUID, svc: UnitServiceDep) -> list[UnitOut]:
    return [await svc.to_out(u) for u in await svc.subtree(unit_id)]


@router.get("/units/{unit_id}/ancestors", response_model=list[UnitOut])
async def ancestors(unit_id: uuid.UUID, svc: UnitServiceDep) -> list[UnitOut]:
    return [await svc.to_out(u) for u in await svc.ancestors(unit_id)]
