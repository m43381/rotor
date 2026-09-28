"""Настройка Keycloak для DutyFlow: `python -m auth_admin.bootstrap` (контейнер keycloak-init).

Идемпотентно, при каждом `just up`:
- служебный клиент `dutyflow-auth-admin` (конфиденциальный, только client credentials) с
  секретом из `AUTH_ADMIN_CLIENT_SECRET` и ролями `manage-users`, `view-users`,
  `query-users` и `view-realm` (чтение настроек, без их изменения) в `realm-management`;
- политика паролей и блокировки realm (open-questions №61).

Импорт realm-файла Keycloak выполняет только при первом создании realm, поэтому то, что
должно меняться на уже развёрнутом стенде, настраивается здесь — через Admin API
администратором master-realm.
"""

import asyncio
import logging
import sys
from typing import Any

import httpx

from auth_admin.settings import AuthAdminSettings
from dutyflow_common.app import setup_logging

log = logging.getLogger(__name__)

# Правила пароля (№61), а не сам пароль
PASSWORD_POLICY = "length(10) and digits(1) and lowerCase(1) and notUsername(undefined)"  # noqa: S105
REALM_SECURITY = {
    "passwordPolicy": PASSWORD_POLICY,
    "bruteForceProtected": True,
    "failureFactor": 10,
    "permanentLockout": False,
    "waitIncrementSeconds": 900,
    "maxFailureWaitSeconds": 900,
    "maxDeltaTimeSeconds": 43200,
    "ssoSessionIdleTimeout": 3600,
    "ssoSessionMaxLifespan": 43200,
}
# view-realm — только чтение настроек realm: без него Keycloak не отдаёт состав ролей
# (`/roles/{role}/users`), и список операторов пришлось бы собирать запросом на каждого
SERVICE_ROLES = ("manage-users", "view-users", "query-users", "view-realm")


async def bootstrap(
    settings: AuthAdminSettings, transport: httpx.AsyncBaseTransport | None = None
) -> None:
    if not settings.auth_admin_client_secret:
        raise SystemExit("AUTH_ADMIN_CLIENT_SECRET не задан (см. deploy/.env)")
    async with httpx.AsyncClient(
        base_url=settings.keycloak_url, timeout=30.0, transport=transport
    ) as http:
        token = await _admin_token(http, settings)
        h = {"Authorization": f"Bearer {token}"}
        realm = f"/admin/realms/{settings.keycloak_realm}"

        async def call(method: str, path: str, **kw: Any) -> httpx.Response:
            resp = await http.request(method, realm + path, headers=h, **kw)
            resp.raise_for_status()
            return resp

        current = (await call("GET", "")).json()
        await call("PUT", "", json={**current, **REALM_SECURITY})

        client_id = settings.auth_admin_client_id
        found = (await call("GET", "/clients", params={"clientId": client_id})).json()
        body = {
            "clientId": client_id,
            "name": "DutyFlow auth-admin",
            "enabled": True,
            "publicClient": False,
            "secret": settings.auth_admin_client_secret,
            "serviceAccountsEnabled": True,
            "standardFlowEnabled": False,
            "directAccessGrantsEnabled": False,
            "implicitFlowEnabled": False,
        }
        if found:
            uid = found[0]["id"]
            await call("PUT", f"/clients/{uid}", json={**found[0], **body})
        else:
            await call("POST", "/clients", json=body)
            uid = (await call("GET", "/clients", params={"clientId": client_id})).json()[0]["id"]
        account = (await call("GET", f"/clients/{uid}/service-account-user")).json()
        management = (
            await call("GET", "/clients", params={"clientId": "realm-management"})
        ).json()[0]
        roles = [
            (await call("GET", f"/clients/{management['id']}/roles/{name}")).json()
            for name in SERVICE_ROLES
        ]
        await call(
            "POST", f"/users/{account['id']}/role-mappings/clients/{management['id']}", json=roles
        )
    log.info("Keycloak настроен: клиент %s, политика паролей и блокировки", client_id)


async def _admin_token(http: httpx.AsyncClient, settings: AuthAdminSettings) -> str:
    for attempt in range(30):
        try:
            resp = await http.post(
                "/realms/master/protocol/openid-connect/token",
                data={
                    "grant_type": "password",
                    "client_id": "admin-cli",
                    "username": settings.keycloak_admin,
                    "password": settings.keycloak_admin_password,
                },
            )
            if resp.status_code == 200:
                token: str = resp.json()["access_token"]
                return token
            log.warning(
                "Keycloak: вход администратора — %s, попытка %d", resp.status_code, attempt + 1
            )
        except httpx.TransportError as exc:
            log.warning("Keycloak недоступен (%s), попытка %d", exc, attempt + 1)
        await asyncio.sleep(2)
    raise SystemExit("Не удалось войти в Keycloak администратором master-realm")


if __name__ == "__main__":
    s = AuthAdminSettings()
    setup_logging(s.log_level)
    asyncio.run(bootstrap(s))
    sys.exit(0)
