"""Лимиты нарядов на человека за месяц (open-questions №9, 27)."""

import uuid

from fastapi import APIRouter

from dutyflow_common.errors import NotFoundError
from scheduling.api.deps import LimitServiceDep
from scheduling.schemas import DutyLimitIn, DutyLimitOut, DutyLimitUpdate

router = APIRouter(tags=["duty-limits"])


async def _one(svc: LimitServiceDep, limit_id: uuid.UUID) -> DutyLimitOut:
    found = next((x for x in await svc.list_limits() if x.id == limit_id), None)
    if found is None:
        raise NotFoundError("Лимит не найден")
    return found


@router.get("/duty-limits", response_model=list[DutyLimitOut])
async def list_limits(svc: LimitServiceDep) -> list[DutyLimitOut]:
    return await svc.list_limits()


@router.post("/duty-limits", response_model=DutyLimitOut, status_code=201)
async def create_limit(data: DutyLimitIn, svc: LimitServiceDep) -> DutyLimitOut:
    return await _one(svc, (await svc.create(data)).id)


@router.put("/duty-limits/{limit_id}", response_model=DutyLimitOut)
async def update_limit(
    limit_id: uuid.UUID, data: DutyLimitUpdate, svc: LimitServiceDep
) -> DutyLimitOut:
    await svc.update(limit_id, data)
    return await _one(svc, limit_id)


@router.delete("/duty-limits/{limit_id}", status_code=204)
async def delete_limit(limit_id: uuid.UUID, svc: LimitServiceDep) -> None:
    await svc.delete(limit_id)
