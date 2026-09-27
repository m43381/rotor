"""Тесты documents: своя БД — PostgreSQL 16 (testcontainers), personnel — подставной
(`httpx.MockTransport`): проверяются разбор файлов, задачи импорта и передача токена
оператора. Связка с настоящим personnel — в e2e на стенде."""

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
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer

from documents.main import create_app
from documents.settings import DocumentsSettings
from dutyflow_common.testing import TestIssuer

SERVICE_DIR = Path(__file__).resolve().parents[1]
UNIT = uuid.UUID("00000000-0000-7000-8000-000000000001")

TEMPLATE = {
    "kind": "people",
    "title": "Личный состав",
    "columns": [
        {"key": "personal_no", "title": "Личный номер", "required": False, "type": "text"},
        {"key": "last_name", "title": "Фамилия", "required": True, "type": "text"},
        {"key": "first_name", "title": "Имя", "required": True, "type": "text"},
        {
            "key": "unit",
            "title": "Подразделение",
            "required": True,
            "type": "list",
            "options": ["Факультет", "Факультет / 1 курс"],
        },
        {"key": "attr:birth", "title": "Дата рождения", "required": False, "type": "date"},
    ],
    "instructions": ["Одна строка — один человек."],
}


@dataclass
class FakePersonnel:
    """Отвечает как personnel: ошибка — строка без фамилии; хэш — от числа строк."""

    calls: list[tuple[str, str, dict[str, Any] | None, str]] = field(default_factory=list)
    stale: bool = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append(
            (request.method, request.url.path, body, request.headers.get("authorization", ""))
        )
        if request.url.path.endswith("/template"):
            return httpx.Response(200, json=TEMPLATE)
        assert body is not None
        rows = []
        for r in body["rows"]:
            ok = bool(r["values"].get("last_name"))
            rows.append(
                {
                    "row": r["row"],
                    "action": "create" if ok else "error",
                    "label": r["values"].get("last_name"),
                    "errors": []
                    if ok
                    else [{"column": "last_name", "message": "Фамилия обязательна"}],
                    "warnings": [],
                    "changes": {},
                }
            )
        summary = {"create": 0, "update": 0, "unchanged": 0, "error": 0}
        for r in rows:
            summary[r["action"]] += 1
        state_hash = f"h{len(rows)}"
        if not body["dry_run"]:
            if self.stale or body.get("expected_hash") != state_hash:
                return httpx.Response(409, json={"code": "import_stale", "message": "Изменились"})
            if summary["error"] and not body.get("skip_invalid"):
                return httpx.Response(422, json={"code": "validation_failed", "message": "Ошибки"})
        return httpx.Response(
            200,
            json={
                "kind": "people",
                "applied": not body["dry_run"],
                "summary": summary,
                "rows": rows,
                "state_hash": state_hash,
            },
        )


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    external = os.environ.get("TEST_DATABASE_URL")
    if external:
        yield external
        return
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def settings(database_url: str) -> DocumentsSettings:
    return DocumentsSettings(database_url=database_url, personnel_url="http://personnel")


@pytest.fixture(scope="session")
def migrated(database_url: str) -> str:
    cfg = Config(str(SERVICE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVICE_DIR / "migrations"))
    os.environ["DATABASE_URL"] = database_url
    command.upgrade(cfg, "head")
    return database_url


@pytest.fixture(scope="session")
def issuer(settings: DocumentsSettings) -> TestIssuer:
    return TestIssuer(settings)


@pytest.fixture(scope="session")
def personnel() -> FakePersonnel:
    return FakePersonnel()


@pytest.fixture(scope="session")
async def app(
    settings: DocumentsSettings, issuer: TestIssuer, migrated: str, personnel: FakePersonnel
) -> AsyncIterator[FastAPI]:
    application = create_app(
        settings,
        token_verifier=issuer.verifier,
        personnel_transport=httpx.MockTransport(personnel.handler),
    )
    async with LifespanManager(application):
        yield application


@pytest.fixture(autouse=True)
async def clean(app: FastAPI, settings: DocumentsSettings, personnel: FakePersonnel) -> None:
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE import_job"))
    await engine.dispose()
    personnel.calls.clear()
    personnel.stale = False


type ClientFactory = Callable[..., AsyncClient]


@pytest.fixture
async def client_for(app: FastAPI, issuer: TestIssuer) -> AsyncIterator[ClientFactory]:
    clients: list[AsyncClient] = []

    def make(*roles: str, username: str = "tester", unit_id: uuid.UUID = UNIT) -> AsyncClient:
        token = issuer.token(unit_id=unit_id, roles=list(roles), username=username)
        c = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        )
        clients.append(c)
        return c

    yield make
    for c in clients:
        await c.aclose()
