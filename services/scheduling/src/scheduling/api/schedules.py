"""Графики подразделений на месяц: таблица, делегирование ролей, принятие, публикация."""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from scheduling.api.deps import ScheduleServiceDep
from scheduling.schemas import (
    AcceptIn,
    ChangedOut,
    DelegateIn,
    PinIn,
    PublishOut,
    ScheduleCreate,
    ScheduleOut,
    TableOut,
    VersionIn,
)

router = APIRouter(tags=["schedules"])


@router.get("/schedules", response_model=list[ScheduleOut], summary="Графики месяца в scope")
async def list_schedules(
    svc: ScheduleServiceDep,
    month: Annotated[dt.date, Query(description="Любой день месяца")],
    unit_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[ScheduleOut]:
    return await svc.list_schedules(month, unit_id)


@router.post("/schedules", response_model=ScheduleOut, status_code=201)
async def create_schedule(data: ScheduleCreate, svc: ScheduleServiceDep) -> ScheduleOut:
    schedule = await svc.create(data.unit_id, data.month)
    return await svc.get(schedule.id)


@router.get("/schedules/{schedule_id}", response_model=ScheduleOut)
async def get_schedule(schedule_id: uuid.UUID, svc: ScheduleServiceDep) -> ScheduleOut:
    return await svc.get(schedule_id)


@router.get(
    "/schedules/{schedule_id}/table",
    response_model=TableOut,
    summary="Таблица месяца: строки — роли нарядов, столбцы — дни",
)
async def schedule_table(schedule_id: uuid.UUID, svc: ScheduleServiceDep) -> TableOut:
    return await svc.table(schedule_id)


@router.post(
    "/schedules/{schedule_id}/delegate",
    response_model=ChangedOut,
    summary="Делегировать ячейки прямому дочернему подразделению или вернуть себе",
)
async def delegate(schedule_id: uuid.UUID, data: DelegateIn, svc: ScheduleServiceDep) -> ChangedOut:
    return ChangedOut(changed=await svc.delegate(schedule_id, data.cell_ids, data.executor_unit_id))


@router.post("/schedules/{schedule_id}/accept", response_model=ChangedOut)
async def accept(schedule_id: uuid.UUID, data: AcceptIn, svc: ScheduleServiceDep) -> ChangedOut:
    return ChangedOut(changed=await svc.accept(schedule_id, data.cell_ids))


@router.post("/schedules/{schedule_id}/pin", response_model=ChangedOut)
async def pin(schedule_id: uuid.UUID, data: PinIn, svc: ScheduleServiceDep) -> ChangedOut:
    return ChangedOut(changed=await svc.pin(schedule_id, data.cell_ids, data.pinned))


@router.post(
    "/schedules/{schedule_id}/publish",
    response_model=PublishOut,
    summary="Опубликовать (непринятые ячейки поддерева — предупреждение, не запрет)",
)
async def publish(schedule_id: uuid.UUID, data: VersionIn, svc: ScheduleServiceDep) -> PublishOut:
    _, warnings = await svc.publish(schedule_id, data.version)
    return PublishOut(schedule=await svc.get(schedule_id), warnings=warnings)


@router.post("/schedules/{schedule_id}/archive", response_model=ScheduleOut)
async def archive(schedule_id: uuid.UUID, data: VersionIn, svc: ScheduleServiceDep) -> ScheduleOut:
    await svc.archive(schedule_id, data.version)
    return await svc.get(schedule_id)
