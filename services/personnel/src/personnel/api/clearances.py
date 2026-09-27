"""Допуски к ролям нарядов и отчёт о несоответствиях (ADR-0009)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from dutyflow_common.pagination import Page, PageParams, page_params
from personnel.api.deps import ClearanceServiceDep
from personnel.schemas import (
    BulkClearanceIn,
    BulkClearanceResult,
    ClearanceIn,
    ClearanceOption,
    ClearanceOut,
    ClearanceRoleOut,
    ClearanceUpdate,
    MismatchItem,
    RevokeIn,
)

router = APIRouter(tags=["clearances"])


@router.get("/people/{person_id}/clearances", response_model=list[ClearanceOut])
async def list_clearances(
    person_id: uuid.UUID,
    svc: ClearanceServiceDep,
    include_revoked: Annotated[bool, Query()] = False,
) -> list[ClearanceOut]:
    return await svc.list_for_person(person_id, include_revoked=include_revoked)


@router.get(
    "/people/{person_id}/clearance-options",
    response_model=list[ClearanceOption],
    summary="Роли, к которым можно выдать допуск, и соответствие требованиям",
)
async def clearance_options(
    person_id: uuid.UUID, svc: ClearanceServiceDep
) -> list[ClearanceOption]:
    return await svc.options(person_id)


@router.post(
    "/people/{person_id}/clearances",
    response_model=list[ClearanceOut],
    status_code=201,
    summary="Выдать допуск",
    description="Если человек не проходит требования роли — 422 `requirements_not_met` с "
    "перечнем нарушений в `details.violations`. Повтор с `confirm_override` и комментарием "
    "выдаёт допуск вопреки требованиям.",
)
async def grant_clearance(
    person_id: uuid.UUID, data: ClearanceIn, svc: ClearanceServiceDep
) -> list[ClearanceOut]:
    await svc.grant(person_id, data)
    return await svc.list_for_person(person_id)


@router.patch("/clearances/{clearance_id}", response_model=list[ClearanceOut])
async def update_clearance(
    clearance_id: uuid.UUID, data: ClearanceUpdate, svc: ClearanceServiceDep
) -> list[ClearanceOut]:
    clearance = await svc.update(clearance_id, data)
    return await svc.list_for_person(clearance.person_id)


@router.post("/clearances/{clearance_id}/revoke", response_model=list[ClearanceOut])
async def revoke_clearance(
    clearance_id: uuid.UUID, data: RevokeIn, svc: ClearanceServiceDep
) -> list[ClearanceOut]:
    clearance = await svc.revoke(clearance_id, data)
    return await svc.list_for_person(clearance.person_id)


@router.post("/clearances/bulk", response_model=BulkClearanceResult, summary="Допуск группе людей")
async def bulk_clearance(data: BulkClearanceIn, svc: ClearanceServiceDep) -> BulkClearanceResult:
    return await svc.bulk(data)


@router.get(
    "/clearance-roles",
    response_model=list[ClearanceRoleOut],
    summary="Роли, допуски к которым оператор выдаёт своим людям",
)
async def clearance_roles(svc: ClearanceServiceDep) -> list[ClearanceRoleOut]:
    return await svc.roles_for_operator()


@router.get(
    "/reports/clearance-mismatches",
    response_model=Page[MismatchItem],
    summary="Действующие допуски, не проходящие текущие требования ролей",
)
async def clearance_mismatches(
    svc: ClearanceServiceDep,
    page: Annotated[PageParams, Depends(page_params)],
    unit_id: Annotated[uuid.UUID | None, Query()] = None,
    subtree: Annotated[bool, Query()] = True,
) -> Page[MismatchItem]:
    return await svc.mismatches(unit_id, subtree, page)
