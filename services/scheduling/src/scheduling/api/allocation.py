"""Автораспределение: предпросмотр с объяснениями, применение, отмена, история (фаза 4b)."""

import uuid

from fastapi import APIRouter

from scheduling.api.deps import RunServiceDep
from scheduling.schemas import AllocateIn, RunBrief, RunOut

router = APIRouter(tags=["allocation"])


@router.post(
    "/schedules/{schedule_id}/allocate",
    response_model=RunOut,
    status_code=201,
    summary="Рассчитать распределение (предпросмотр, график не меняется)",
)
async def allocate(schedule_id: uuid.UUID, data: AllocateIn, svc: RunServiceDep) -> RunOut:
    run = await svc.allocate(schedule_id, data)
    return await svc.get(run.id, poll=False)


@router.get("/schedules/{schedule_id}/allocation-runs", response_model=list[RunBrief])
async def list_runs(schedule_id: uuid.UUID, svc: RunServiceDep) -> list[RunBrief]:
    return await svc.list_runs(schedule_id)


@router.get("/allocation-runs/{run_id}", response_model=RunOut)
async def get_run(run_id: uuid.UUID, svc: RunServiceDep) -> RunOut:
    return await svc.get(run_id)


@router.post(
    "/allocation-runs/{run_id}/apply",
    response_model=RunOut,
    summary="Применить предпросмотр",
    description="409 `run_stale` — после расчёта данные изменились, нужен пересчёт (№45).",
)
async def apply(run_id: uuid.UUID, svc: RunServiceDep) -> RunOut:
    await svc.apply(run_id)
    return await svc.get(run_id)


@router.post("/allocation-runs/{run_id}/discard", response_model=RunOut)
async def discard(run_id: uuid.UUID, svc: RunServiceDep) -> RunOut:
    await svc.discard(run_id)
    return await svc.get(run_id)
