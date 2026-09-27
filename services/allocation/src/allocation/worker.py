"""Воркер фоновых расчётов (arq на Redis): `arq allocation.worker.WorkerSettings`.

Долгие прогоны — CP-SAT с большим пределом, большие снимки — идут в очередь, чтобы не держать
HTTP-запрос (open-questions №47). Воркер вызывает ту же чистую функцию `solve`, что и
синхронный `POST /internal/solve`; снимок и настройки передаются аргументами задачи.
"""

import asyncio
from typing import Any, ClassVar

from arq.connections import RedisSettings

from allocation.engine.config import make_config
from allocation.engine.solve import solve
from allocation.settings import AllocationSettings

JOB = "solve_job"


async def solve_job(
    ctx: dict[str, Any], snapshot: dict[str, Any], config: dict[str, Any], seed: int
) -> dict[str, Any]:
    # Расчёт — CPU; в отдельном потоке, чтобы воркер отвечал на служебные запросы arq
    return await asyncio.to_thread(solve, snapshot, make_config(config), seed)


class WorkerSettings:
    functions: ClassVar[list[Any]] = [solve_job]
    redis_settings = RedisSettings.from_dsn(AllocationSettings().redis_url)
    job_timeout = 600  # страховка сверх пределов методов
    keep_result = 86_400  # результат ждёт, пока scheduling его заберёт
    max_jobs = 2  # расчёт нагружает процессор — параллельно немного
