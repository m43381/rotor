"""Внутренний API движка для scheduling (`docs/architecture.md` §3.4).

Синхронный: жадный метод фазы 4 укладывается в секунды. Долгие прогоны (CP-SAT) и очередь
arq появятся в фазе 5. Расчёт идёт в пуле потоков, чтобы не блокировать цикл событий.
"""

from typing import Any

from fastapi import APIRouter, Depends, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from pydantic_core import to_json

from allocation.engine.config import load_defaults, make_config
from allocation.engine.solve import solve
from dutyflow_common.auth import require_internal
from dutyflow_common.errors import ValidationFailedError

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_internal)])


class SolveIn(BaseModel):
    snapshot: dict[str, Any]
    # Переопределение настроек по умолчанию (allocation/config/default.yaml)
    config: dict[str, Any] = Field(default_factory=dict)
    seed: int = Field(default=0, ge=0, le=2**31 - 1)


@router.post("/solve", summary="Снимок + настройки + seed → решение с объяснением")
async def solve_endpoint(data: SolveIn) -> Response:
    try:
        config = make_config(data.config)
    except ValueError as exc:
        raise ValidationFailedError(f"Некорректные настройки прогона: {exc}") from exc
    try:
        solution = await run_in_threadpool(solve, data.snapshot, config, data.seed)
    except (KeyError, ValueError) as exc:
        raise ValidationFailedError(f"Некорректный снимок: {exc}") from exc
    return Response(content=to_json(solution), media_type="application/json")


@router.get("/config/defaults", summary="Настройки движка по умолчанию")
async def defaults() -> dict[str, Any]:
    return make_config(load_defaults()).model_dump(mode="json")
