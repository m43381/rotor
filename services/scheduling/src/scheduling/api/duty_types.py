"""Типы нарядов и роли (ADR-0008, ADR-0009)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from scheduling.api.deps import DutyTypeServiceDep
from scheduling.schemas import (
    DutyRoleIn,
    DutyRoleUpdate,
    DutyTypeCreate,
    DutyTypeOut,
    DutyTypeUpdate,
)

router = APIRouter(tags=["duty-types"])


@router.get("/duty-types", response_model=list[DutyTypeOut], summary="Видимые типы нарядов")
async def list_duty_types(
    svc: DutyTypeServiceDep,
    include_inactive: Annotated[bool, Query()] = False,
    unit_id: Annotated[
        uuid.UUID | None, Query(description="Наряды, касающиеся подразделения")
    ] = None,
) -> list[DutyTypeOut]:
    return await svc.list_types(include_inactive=include_inactive, unit_id=unit_id)


@router.post("/duty-types", response_model=DutyTypeOut, status_code=201)
async def create_duty_type(data: DutyTypeCreate, svc: DutyTypeServiceDep) -> DutyTypeOut:
    duty_type = await svc.create(data)
    return await svc.get(duty_type.id)


@router.get("/duty-types/{type_id}", response_model=DutyTypeOut)
async def get_duty_type(type_id: uuid.UUID, svc: DutyTypeServiceDep) -> DutyTypeOut:
    return await svc.get(type_id)


@router.put("/duty-types/{type_id}", response_model=DutyTypeOut)
async def update_duty_type(
    type_id: uuid.UUID, data: DutyTypeUpdate, svc: DutyTypeServiceDep
) -> DutyTypeOut:
    await svc.update(type_id, data)
    return await svc.get(type_id)


@router.post("/duty-types/{type_id}/roles", response_model=DutyTypeOut, status_code=201)
async def add_duty_role(
    type_id: uuid.UUID, data: DutyRoleIn, svc: DutyTypeServiceDep
) -> DutyTypeOut:
    await svc.add_role(type_id, data)
    return await svc.get(type_id)


@router.put("/duty-roles/{role_id}", response_model=DutyTypeOut)
async def update_duty_role(
    role_id: uuid.UUID, data: DutyRoleUpdate, svc: DutyTypeServiceDep
) -> DutyTypeOut:
    role = await svc.update_role(role_id, data)
    return await svc.get(role.duty_type_id)
