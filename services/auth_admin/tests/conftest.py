"""Тесты auth-admin: своя БД (журнал аудита) — PostgreSQL 16, Keycloak Admin API и org —
подставные (`httpx.MockTransport`). Keycloak в памяти повторяет нужные эндпоинты: пользователи,
роли realm, клиенты, токены."""

import base64
import json
import os
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from auth_admin.main import create_app
from auth_admin.settings import AuthAdminSettings
from dutyflow_common.testing import TestIssuer
from dutyflow_common.testing.audit_coverage import AuditCoverage, event_hooks

SERVICE_DIR = Path(__file__).resolve().parents[1]
# Учёт покрытия аудита: исключения — маршруты, не меняющие данные, с причиной
AUDIT = AuditCoverage(exempt={})
ROOT = uuid.UUID("00000000-0000-7000-8000-000000000001")
FACULTY = uuid.UUID("00000000-0000-7000-8000-000000000002")
COURSE = uuid.UUID("00000000-0000-7000-8000-000000000003")
OTHER = uuid.UUID("00000000-0000-7000-8000-000000000004")
UNITS = {
    ROOT: {"id": str(ROOT), "name": "Академия", "path": "1"},
    FACULTY: {"id": str(FACULTY), "name": "Факультет 1", "path": "1.2"},
    COURSE: {"id": str(COURSE), "name": "1 курс", "path": "1.2.3"},
    OTHER: {"id": str(OTHER), "name": "Факультет 2", "path": "1.4"},
}
ROLES = ("superadmin", "unit_admin", "operator", "viewer")


@dataclass
class FakeKeycloak:
    users: dict[str, dict[str, Any]] = field(default_factory=dict)
    roles: dict[str, set[str]] = field(default_factory=dict)  # user → роли realm
    passwords: dict[str, tuple[str, bool]] = field(default_factory=dict)
    logouts: list[str] = field(default_factory=list)
    realm: dict[str, Any] = field(default_factory=lambda: {"realm": "dutyflow"})
    clients: dict[str, dict[str, Any]] = field(default_factory=dict)
    client_roles: dict[str, list[str]] = field(default_factory=dict)

    def add(self, username: str, role: str, unit: uuid.UUID, user_id: str | None = None) -> str:
        uid = user_id or str(uuid.uuid4())
        self.users[uid] = {
            "id": uid,
            "username": username,
            "enabled": True,
            "firstName": "Имя",
            "lastName": username.title(),
            "attributes": {"unit_id": [str(unit)]},
            "createdTimestamp": 1_700_000_000_000,
        }
        self.roles[uid] = {role}
        return uid

    def handler(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path.removeprefix("/auth"), request.method
        is_json = request.headers.get("content-type", "").startswith("application/json")
        body = json.loads(request.content) if request.content and is_json else None
        if path.endswith("/protocol/openid-connect/token"):
            return httpx.Response(200, json={"access_token": "kc", "expires_in": 300})
        prefix = "/admin/realms/dutyflow"
        assert path.startswith(prefix), path
        rest = path[len(prefix) :]
        parts = [p for p in rest.split("/") if p]
        if not parts:
            if method == "GET":
                return httpx.Response(200, json=self.realm)
            self.realm = body or {}
            return httpx.Response(204)
        if parts[0] == "users" and len(parts) == 1:
            if method == "GET":
                first = int(request.url.params.get("first", 0))
                size = int(request.url.params.get("max", 100))
                return httpx.Response(200, json=list(self.users.values())[first : first + size])
            assert body is not None
            if any(u["username"] == body["username"] for u in self.users.values()):
                return httpx.Response(409, json={"errorMessage": "User exists"})
            uid = str(uuid.uuid4())
            creds = body.pop("credentials", [])
            self.users[uid] = {**body, "id": uid, "createdTimestamp": 1_700_000_000_000}
            self.roles[uid] = set()
            if creds:
                self.passwords[uid] = (creds[0]["value"], creds[0]["temporary"])
            return httpx.Response(201, headers={"Location": f"http://kc{prefix}/users/{uid}"})
        if parts[0] == "users":
            uid = parts[1]
            if parts[2:4] == ["role-mappings", "clients"]:  # служебная учётная запись клиента
                names = {r["name"] for r in body or []}
                self.client_roles[uid] = sorted({*self.client_roles.get(uid, []), *names})
                return httpx.Response(204)
            if uid not in self.users:
                return httpx.Response(404)
            tail = parts[2:]
            if not tail:
                if method == "GET":
                    return httpx.Response(200, json=self.users[uid])
                assert body is not None
                self.users[uid] = {**self.users[uid], **body, "id": uid}
                return httpx.Response(204)
            if tail == ["role-mappings", "realm"]:
                if method == "GET":
                    return httpx.Response(200, json=[{"name": r} for r in sorted(self.roles[uid])])
                names = {r["name"] for r in body or []}
                if method == "POST":
                    self.roles[uid] |= names
                else:
                    self.roles[uid] -= names
                return httpx.Response(204)
            if tail == ["reset-password"]:
                assert body is not None
                self.passwords[uid] = (body["value"], body["temporary"])
                return httpx.Response(204)
            if tail == ["logout"]:
                self.logouts.append(uid)
                return httpx.Response(204)
            if tail[:2] == ["role-mappings", "clients"]:
                self.client_roles[uid] = sorted(
                    {*self.client_roles.get(uid, []), *(r["name"] for r in body or [])}
                )
                return httpx.Response(204)
        if parts[0] == "roles":
            role = parts[1]
            if len(parts) == 2:
                return httpx.Response(200, json={"name": role, "id": role})
            members = [self.users[u] for u, r in self.roles.items() if role in r]
            first = int(request.url.params.get("first", 0))
            size = int(request.url.params.get("max", 100))
            return httpx.Response(200, json=members[first : first + size])
        if parts[0] == "clients":
            if len(parts) == 1:
                if method == "GET":
                    cid = request.url.params.get("clientId")
                    if cid == "realm-management":
                        return httpx.Response(
                            200, json=[{"id": "rm", "clientId": "realm-management"}]
                        )
                    return httpx.Response(
                        200, json=[c for c in self.clients.values() if c["clientId"] == cid]
                    )
                assert body is not None
                self.clients[body["clientId"]] = {**body, "id": body["clientId"] + "-uuid"}
                return httpx.Response(201)
            if parts[1] == "rm" and parts[2] == "roles":
                return httpx.Response(200, json={"name": parts[3], "id": parts[3]})
            if parts[2:] == ["service-account-user"]:
                return httpx.Response(200, json={"id": "sa"})
            if method == "PUT":
                cid = parts[1].removesuffix("-uuid")
                self.clients[cid] = {**self.clients[cid], **(body or {})}
                return httpx.Response(204)
        return httpx.Response(404)


def _unit_of(request: httpx.Request) -> uuid.UUID:
    token = request.headers["authorization"].split()[1].split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
    return uuid.UUID(claims["unit_id"])


def org_handler(request: httpx.Request) -> httpx.Response:
    """`GET /units` — поддерево подразделения оператора (для суперадминистратора — всё)."""
    assert request.url.path == "/units"
    token = request.headers["authorization"].split()[1].split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
    root = UNITS[_unit_of(request)]["path"]
    if "superadmin" in claims["realm_access"]["roles"]:
        root = "1"
    units = [u for u in UNITS.values() if u["path"] == root or u["path"].startswith(root + ".")]
    return httpx.Response(200, json=units)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    external = os.environ.get("TEST_DATABASE_URL")
    if external:
        yield external
        return
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def settings(database_url: str) -> AuthAdminSettings:
    return AuthAdminSettings(
        database_url=database_url,
        auth_admin_client_secret="secret",
        keycloak_admin="kcadmin",
        keycloak_admin_password="kc-password",
    )


@pytest.fixture(scope="session")
def migrated(database_url: str) -> str:
    cfg = Config(str(SERVICE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVICE_DIR / "migrations"))
    os.environ["DATABASE_URL"] = database_url
    command.upgrade(cfg, "head")
    return database_url


@pytest.fixture(scope="session")
def issuer(settings: AuthAdminSettings) -> TestIssuer:
    return TestIssuer(settings)


@pytest.fixture(scope="session")
def keycloak() -> FakeKeycloak:
    return FakeKeycloak()


@pytest.fixture(scope="session")
async def app(
    settings: AuthAdminSettings, issuer: TestIssuer, migrated: str, keycloak: FakeKeycloak
) -> AsyncIterator[FastAPI]:
    application = create_app(
        settings,
        token_verifier=issuer.verifier,
        keycloak_transport=httpx.MockTransport(keycloak.handler),
        org_transport=httpx.MockTransport(org_handler),
    )
    AUDIT.bind(application)
    async with LifespanManager(application):
        yield application


@pytest.fixture
def sessionmaker(app: FastAPI) -> async_sessionmaker[AsyncSession]:
    maker: async_sessionmaker[AsyncSession] = app.state.db.sessionmaker
    return maker


@dataclass
class People:
    root_admin: str
    fac_admin: str
    fac_operator: str
    course_admin: str
    other_admin: str


@pytest.fixture(autouse=True)
async def people(app: FastAPI, settings: AuthAdminSettings, keycloak: FakeKeycloak) -> People:
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE audit_log, outbox"))
    await engine.dispose()
    for store in (keycloak.users, keycloak.roles, keycloak.passwords):
        store.clear()
    keycloak.logouts.clear()
    return People(
        root_admin=keycloak.add("admin", "superadmin", ROOT),
        fac_admin=keycloak.add("fac_admin", "unit_admin", FACULTY),
        fac_operator=keycloak.add("fac_operator", "operator", FACULTY),
        course_admin=keycloak.add("course_admin", "unit_admin", COURSE),
        other_admin=keycloak.add("other_admin", "unit_admin", OTHER),
    )


type ClientFactory = Callable[..., AsyncClient]


@pytest.fixture
async def client_for(app: FastAPI, issuer: TestIssuer) -> AsyncIterator[ClientFactory]:
    clients: list[AsyncClient] = []

    def make(unit_id: uuid.UUID, role: str, sub: str | None = None) -> AsyncClient:
        token = issuer.token(unit_id=unit_id, roles=[role], sub=sub)
        c = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
            event_hooks=event_hooks(AUDIT),
        )
        clients.append(c)
        return c

    yield make
    for c in clients:
        await c.aclose()


@pytest.fixture(scope="session")
def audit_coverage() -> AuditCoverage:
    """Учёт покрытия аудита — через фикстуру: импорт conftest из теста дал бы второй экземпляр."""
    return AUDIT
