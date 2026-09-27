"""Фоновые расчёты: постановка в очередь arq и статус задачи (фаза 5b).

scheduling ставит задачу и опрашивает её, пока результат не готов; результат хранится
в Redis сутки (`WorkerSettings.keep_result`).
"""

from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.jobs import Job, JobStatus
from fastapi import APIRouter, Depends, Request

from allocation.api.internal import SolveIn
from allocation.engine.config import make_config
from allocation.worker import JOB
from dutyflow_common.auth import require_internal
from dutyflow_common.errors import NotFoundError, ValidationFailedError

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_internal)])

STATUS = {
    JobStatus.deferred: "queued",
    JobStatus.queued: "queued",
    JobStatus.in_progress: "running",
    JobStatus.complete: "done",
}


async def _pool(request: Request) -> ArqRedis:
    return await create_pool(RedisSettings.from_dsn(request.app.state.settings.redis_url))


@router.post("/jobs", status_code=202, summary="Поставить расчёт в очередь")
async def submit(data: SolveIn, request: Request) -> dict[str, str]:
    try:
        make_config(data.config)  # ошибки настроек — сразу, а не в воркере
    except ValueError as exc:
        raise ValidationFailedError(f"Некорректные настройки прогона: {exc}") from exc
    pool = await _pool(request)
    try:
        job = await pool.enqueue_job(JOB, data.snapshot, data.config, data.seed)
    finally:
        await pool.aclose()
    if job is None:
        raise ValidationFailedError("Задача с таким id уже есть")
    return {"job_id": job.job_id}


@router.get("/jobs/{job_id}", summary="Статус задачи и результат")
async def status(job_id: str, request: Request) -> dict[str, Any]:
    pool = await _pool(request)
    try:
        job = Job(job_id, pool)
        state = await job.status()
        if state == JobStatus.not_found:
            raise NotFoundError("Задача не найдена или результат уже удалён")
        if state != JobStatus.complete:
            return {"job_id": job_id, "status": STATUS[state]}
        info = await job.result_info()
    finally:
        await pool.aclose()
    if info is None or not info.success:
        return {"job_id": job_id, "status": "failed", "error": str(info.result if info else "")}
    return {"job_id": job_id, "status": "done", "result": info.result}
