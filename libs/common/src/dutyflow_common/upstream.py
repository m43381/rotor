"""HTTP-клиент к публичному API другого сервиса от имени оператора (ADR-0014).

Сервис-посредник (`documents`) передаёт дальше токен оператора: права и аудит проверяет
сервис-владелец данных, как при работе из интерфейса, и в журнале остаётся реальный
оператор. Ошибки владельца (4xx) доходят до оператора как есть — с тем же кодом и текстом;
недоступность (сеть, 5xx) — 503. Повторяются только чтения: запись могла уже пройти.
"""

import asyncio
import logging
from typing import Any

import httpx

from dutyflow_common.context import current_request_id
from dutyflow_common.errors import AppError
from dutyflow_common.internal import ServiceUnavailableError

log = logging.getLogger(__name__)


class UpstreamError(AppError):
    """Ошибка сервиса-владельца, переданная оператору без изменений."""

    def __init__(self, status: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(message, details=details)
        self.status_code = status
        self.code = code


class UpstreamClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 60.0,
        retries: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)
        self._retries = retries

    async def get(self, path: str, token: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, token, params=params)

    async def post(self, path: str, token: str, body: dict[str, Any]) -> Any:
        return await self._request("POST", path, token, body=body)

    async def _request(
        self,
        method: str,
        path: str,
        token: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        attempts = self._retries if method == "GET" else 1
        delay = 0.5
        for attempt in range(1, attempts + 1):
            try:
                resp = await self._client.request(
                    method,
                    path,
                    json=body,
                    params=params,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-Request-Id": current_request_id.get(),
                    },
                )
            except httpx.TransportError as exc:
                log.warning("%s %s недоступен (%s), попытка %d", method, path, exc, attempt)
            else:
                if resp.status_code < 400:
                    return resp.json()
                if resp.status_code < 500:
                    raise _error(resp)
                log.warning("%s %s → %s, попытка %d", method, path, resp.status_code, attempt)
            if attempt < attempts:
                await asyncio.sleep(delay)
                delay *= 2
        raise ServiceUnavailableError("Сервис временно недоступен, попробуйте позже")

    async def aclose(self) -> None:
        await self._client.aclose()


def _error(resp: httpx.Response) -> UpstreamError:
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    return UpstreamError(
        resp.status_code,
        str(body.get("code", "upstream_error")),
        str(body.get("message", "Ошибка при обращении к сервису")),
        body.get("details"),
    )
