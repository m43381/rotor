"""Клиент Keycloak Admin REST API для управления операторами (ADR-0002).

Работает от служебного клиента `dutyflow-auth-admin` (client credentials, роли
`manage-users`, `view-users`, `query-users`, `view-realm` в `realm-management`); токен кэшируется до
истечения. Список операторов строится без N+1: все пользователи — постранично, роли — по
составу каждой из четырёх ролей системы.
"""

import time
from typing import Any

import httpx

from dutyflow_common.errors import AppError, ConflictError, NotFoundError
from dutyflow_common.internal import ServiceUnavailableError

ROLES = ("superadmin", "unit_admin", "operator", "viewer")
PAGE = 500
SERVICE_PREFIX = "service-account-"


class KeycloakError(AppError):
    status_code = 502
    code = "keycloak_error"


class KeycloakAdmin:
    def __init__(
        self,
        base_url: str,
        realm: str,
        client_id: str,
        client_secret: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._http = httpx.AsyncClient(base_url=base_url, timeout=20.0, transport=transport)
        self.realm = realm
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: str | None = None
        self._expires = 0.0

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _auth(self) -> dict[str, str]:
        if self._token is None or time.monotonic() > self._expires:
            try:
                resp = await self._http.post(
                    f"/realms/{self.realm}/protocol/openid-connect/token",
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                )
            except httpx.TransportError as exc:
                raise ServiceUnavailableError("Сервис входа (Keycloak) недоступен") from exc
            if resp.status_code != 200:
                raise KeycloakError("Нет доступа к управлению пользователями Keycloak")
            data = resp.json()
            self._token = data["access_token"]
            self._expires = time.monotonic() + max(10, int(data.get("expires_in", 60)) - 10)
        return {"Authorization": f"Bearer {self._token}"}

    async def _call(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        try:
            resp = await self._http.request(
                method,
                f"/admin/realms/{self.realm}{path}",
                json=json,
                params=params,
                headers=await self._auth(),
            )
        except httpx.TransportError as exc:
            raise ServiceUnavailableError("Сервис входа (Keycloak) недоступен") from exc
        if resp.status_code == 404:
            raise NotFoundError("Оператор не найден")
        if resp.status_code == 409:
            raise ConflictError("Такой логин уже занят")
        if resp.status_code >= 400:
            detail = resp.text[:300]
            raise KeycloakError(f"Keycloak отклонил операцию: {detail}")
        return resp

    # --- чтение ----------------------------------------------------------------------------

    async def users(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        while True:
            page = (
                await self._call(
                    "GET",
                    "/users",
                    params={"first": len(result), "max": PAGE, "briefRepresentation": "false"},
                )
            ).json()
            result += page
            if len(page) < PAGE:
                break
        return [u for u in result if not u["username"].startswith(SERVICE_PREFIX)]

    async def role_members(self) -> dict[str, str]:
        """Пользователь → роль системы (у оператора одна роль; при нескольких — старшая)."""
        members: dict[str, str] = {}
        for role in reversed(ROLES):  # старшие роли перезаписывают младшие
            first = 0
            while True:
                page = (
                    await self._call(
                        "GET", f"/roles/{role}/users", params={"first": first, "max": PAGE}
                    )
                ).json()
                for u in page:
                    members[u["id"]] = role
                if len(page) < PAGE:
                    break
                first += PAGE
        return members

    async def user(self, user_id: str) -> dict[str, Any]:
        data: dict[str, Any] = (await self._call("GET", f"/users/{user_id}")).json()
        return data

    async def user_role(self, user_id: str) -> str | None:
        mapped = (await self._call("GET", f"/users/{user_id}/role-mappings/realm")).json()
        names: set[str] = {str(r["name"]) for r in mapped}
        role: str | None = next((r for r in ROLES if r in names), None)
        return role

    # --- изменение ---------------------------------------------------------------------------

    async def create_user(self, body: dict[str, Any]) -> str:
        resp = await self._call("POST", "/users", json=body)
        location = str(resp.headers.get("Location", ""))
        return location.rstrip("/").rsplit("/", 1)[-1]

    async def update_user(self, user_id: str, body: dict[str, Any]) -> None:
        await self._call("PUT", f"/users/{user_id}", json=body)

    async def set_role(self, user_id: str, role: str) -> None:
        """Одна роль системы у оператора: лишние снимаются, нужная назначается."""
        mapped = (await self._call("GET", f"/users/{user_id}/role-mappings/realm")).json()
        extra = [r for r in mapped if r["name"] in ROLES and r["name"] != role]
        if extra:
            await self._call("DELETE", f"/users/{user_id}/role-mappings/realm", json=extra)
        if not any(r["name"] == role for r in mapped):
            target = (await self._call("GET", f"/roles/{role}")).json()
            await self._call("POST", f"/users/{user_id}/role-mappings/realm", json=[target])

    async def reset_password(self, user_id: str, password: str) -> None:
        await self._call(
            "PUT",
            f"/users/{user_id}/reset-password",
            json={"type": "password", "value": password, "temporary": True},
        )

    async def logout(self, user_id: str) -> None:
        await self._call("POST", f"/users/{user_id}/logout")
