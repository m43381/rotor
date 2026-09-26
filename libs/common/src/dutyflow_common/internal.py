"""HTTP-клиент для внутренних batch-эндпоинтов других сервисов (`/internal/*`)."""

import asyncio
import logging
from typing import Any

import httpx

from dutyflow_common.context import current_request_id
from dutyflow_common.errors import AppError

log = logging.getLogger(__name__)


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"


class InternalClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 10.0,
        retries: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={"X-Internal-Token": token},
            transport=transport,
        )
        self._retries = retries

    async def post(self, path: str, body: dict[str, Any]) -> Any:
        """POST с повторами при сетевых ошибках и 5xx. Ошибки 4xx не повторяются."""
        delay = 0.5
        for attempt in range(1, self._retries + 1):
            try:
                resp = await self._client.post(
                    path, json=body, headers={"X-Request-Id": current_request_id.get()}
                )
                if resp.status_code < 500:
                    resp.raise_for_status()
                    return resp.json()
                log.warning("%s → %s, попытка %d", path, resp.status_code, attempt)
            except httpx.TransportError as exc:
                log.warning("%s недоступен (%s), попытка %d", path, exc, attempt)
            if attempt < self._retries:
                await asyncio.sleep(delay)
                delay *= 2
        raise ServiceUnavailableError(f"Сервис недоступен: {self._client.base_url}{path}")

    async def aclose(self) -> None:
        await self._client.aclose()
