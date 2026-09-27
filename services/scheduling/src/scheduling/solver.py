"""Вызов движка распределения (сервис allocation, `POST /internal/solve`).

scheduling собирает снимок и применяет решение, allocation только считает
(`docs/architecture.md` §3.4). В тестах вызов подменяется движком в процессе.
"""

from typing import Any, Protocol

from dutyflow_common.internal import InternalClient
from scheduling.settings import SchedulingSettings


class Solver(Protocol):
    async def __call__(
        self, snapshot: dict[str, Any], config: dict[str, Any], seed: int
    ) -> dict[str, Any]: ...


def http_solver(settings: SchedulingSettings) -> Solver:
    async def solve(snapshot: dict[str, Any], config: dict[str, Any], seed: int) -> dict[str, Any]:
        # Жадный метод фазы 4 укладывается в секунды; таймаут — с запасом на большие снимки
        client = InternalClient(
            settings.allocation_url, settings.internal_token, timeout=180.0, retries=1
        )
        try:
            result: dict[str, Any] = await client.post(
                "/internal/solve", {"snapshot": snapshot, "config": config, "seed": seed}
            )
        finally:
            await client.aclose()
        return result

    return solve
