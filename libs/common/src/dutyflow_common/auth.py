"""Проверка JWT оператора по JWKS (ADR-0002).

Сервис зависит только от стандартного OIDC: подпись проверяется по ключам из JWKS,
issuer/audience/имя claim-а с подразделением берутся из настроек — поэтому Keycloak
можно заменить другим IdP без правки бизнес-сервисов.
"""

import asyncio
import hmac
import time
import uuid
from typing import Any

import httpx
import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from dutyflow_common.context import Operator, current_operator
from dutyflow_common.errors import UnauthorizedError
from dutyflow_common.policy import Role
from dutyflow_common.settings import ServiceSettings

_ALGORITHMS = ["RS256", "ES256"]
_REFRESH_COOLDOWN_S = 30.0
_ROLE_VALUES = frozenset(r.value for r in Role)


class JwksCache:
    """Ключи IdP в памяти. Обновляются при встрече неизвестного `kid` (ротация ключей),
    но не чаще раза в `_REFRESH_COOLDOWN_S`, чтобы мусорные токены не устроили DoS на IdP."""

    def __init__(self, jwks_url: str) -> None:
        self._url = jwks_url
        self._keys: dict[str, Any] = {}
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    def set_keys(self, jwks: dict[str, Any]) -> None:
        self._keys = {
            k["kid"]: jwt.PyJWK(k).key for k in jwks.get("keys", []) if k.get("use", "sig") == "sig"
        }
        self._fetched_at = time.monotonic()

    async def get(self, kid: str) -> Any:
        if kid in self._keys:
            return self._keys[kid]
        async with self._lock:
            if kid not in self._keys and time.monotonic() - self._fetched_at > _REFRESH_COOLDOWN_S:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(self._url)
                    resp.raise_for_status()
                    self.set_keys(resp.json())
        if kid not in self._keys:
            raise UnauthorizedError("Неизвестный ключ подписи токена")
        return self._keys[kid]


class TokenVerifier:
    def __init__(self, settings: ServiceSettings, jwks: JwksCache | None = None) -> None:
        self._settings = settings
        self.jwks = jwks or JwksCache(settings.oidc_jwks_url)

    async def verify(self, token: str) -> Operator:
        try:
            header = jwt.get_unverified_header(token)
            key = await self.jwks.get(str(header.get("kid", "")))
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=_ALGORITHMS,
                audience=self._settings.oidc_audience,
                issuer=self._settings.oidc_issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise UnauthorizedError("Недействительный токен") from exc
        return self._operator_from_claims(claims)

    def _operator_from_claims(self, claims: dict[str, Any]) -> Operator:
        raw_unit = claims.get(self._settings.oidc_unit_claim)
        try:
            unit_id = uuid.UUID(str(raw_unit))
        except ValueError as exc:
            raise UnauthorizedError("В токене нет подразделения оператора") from exc
        realm_roles = claims.get("realm_access", {}).get("roles", [])
        roles = frozenset(Role(r) for r in realm_roles if r in _ROLE_VALUES)
        if not roles:
            raise UnauthorizedError("У учётной записи нет роли в системе")
        return Operator(
            subject=str(claims["sub"]),
            username=str(claims.get("preferred_username", claims["sub"])),
            unit_id=unit_id,
            roles=roles,
            full_name=str(claims.get("name", "")),
        )


_bearer = HTTPBearer(auto_error=False)


async def get_operator(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Operator:
    """FastAPI-зависимость: оператор из заголовка Authorization.

    Кладёт его в contextvar, откуда его берёт аудит.
    """
    if credentials is None:
        raise UnauthorizedError("Требуется вход в систему")
    verifier: TokenVerifier = request.app.state.token_verifier
    operator = await verifier.verify(credentials.credentials)
    current_operator.set(operator)
    return operator


async def require_internal(request: Request) -> None:
    """Защита /internal/* — вызовы между сервисами внутри сети compose."""
    settings: ServiceSettings = request.app.state.settings
    expected = settings.internal_token
    given = request.headers.get("X-Internal-Token", "")
    if not expected or not hmac.compare_digest(given, expected):
        raise UnauthorizedError("Внутренний эндпоинт")
