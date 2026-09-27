"""Тесты documents: своя БД — PostgreSQL 16 (testcontainers), personnel — подставной
(`httpx.MockTransport`): проверяются разбор файлов, задачи импорта и передача токена
оператора. Связка с настоящим personnel — в e2e на стенде."""

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

from documents.main import create_app
from documents.settings import DocumentsSettings
from dutyflow_common.testing import TestIssuer

SERVICE_DIR = Path(__file__).resolve().parents[1]
UNIT = uuid.UUID("00000000-0000-7000-8000-000000000001")
FACULTY = uuid.UUID("00000000-0000-7000-8000-000000000002")
COURSE = uuid.UUID("00000000-0000-7000-8000-000000000003")
UNITS = {
    UNIT: {"id": str(UNIT), "name": "Академия", "path": "1", "parent_id": None},
    FACULTY: {"id": str(FACULTY), "name": "Факультет 1", "path": "1.2", "parent_id": str(UNIT)},
    COURSE: {"id": str(COURSE), "name": "1 курс", "path": "1.2.3", "parent_id": str(FACULTY)},
}
SCHEDULE_ID = uuid.UUID("00000000-0000-7000-8000-00000000aaaa")

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


def _claims(request: httpx.Request) -> dict[str, Any]:
    token = request.headers["authorization"].split()[1]
    payload = token.split(".")[1]
    data: dict[str, Any] = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    return data


def _person(last: str) -> dict[str, Any]:
    return {
        "person_id": str(uuid.uuid4()),
        "rank_name": "Рядовой",
        "last_name": last,
        "first_name": "Иван",
        "middle_name": "Петрович",
        "short_name": f"{last} И. П.",
        "unit_name": "Группа 111",
        "conflict": None,
    }


@dataclass
class FakeUpstreams:
    """org и scheduling: подразделения, текущий оператор, данные для печати."""

    status: str = "published"
    calls: list[str] = field(default_factory=list)

    def org(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(f"org {path}")
        if path == "/me":
            unit = UNITS[uuid.UUID(_claims(request)["unit_id"])]
            return httpx.Response(200, json={"unit": unit})
        parts = path.strip("/").split("/")
        unit = UNITS.get(uuid.UUID(parts[1]))
        if unit is None:
            return httpx.Response(404, json={"code": "not_found", "message": "Нет такого"})
        if len(parts) == 3:  # ancestors: от корня к родителю
            chain = []
            parent = unit["parent_id"]
            while parent:
                chain.insert(0, UNITS[uuid.UUID(parent)])
                parent = UNITS[uuid.UUID(parent)]["parent_id"]
            return httpx.Response(200, json=chain)
        return httpx.Response(200, json=unit)

    def scheduling(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(f"scheduling {path}")
        if path == f"/schedules/{SCHEDULE_ID}/print":
            days = [{"date": f"2026-11-{d:02d}", "kind": "workday", "name": None} for d in (1, 2)]
            return httpx.Response(
                200,
                json={
                    "schedule": {
                        "id": str(SCHEDULE_ID),
                        "unit_id": str(COURSE),
                        "unit_name": "1 курс",
                        "month": "2026-11-01",
                        "status": self.status,
                    },
                    "days": days,
                    "rows": [
                        {
                            "duty_type_name": "Наряд по курсу",
                            "duty_type_short_name": None,
                            "owner_unit_name": "1 курс",
                            "role_name": "Дежурный",
                            "start_time": "18:00:00",
                            "duration_minutes": 1440,
                            "headcount": 1,
                            "cells": [
                                {
                                    "executor_unit_name": None,
                                    "people": [_person("Алексеев")],
                                    "missing": 0,
                                },
                                {"executor_unit_name": "Группа 111", "people": [], "missing": 0},
                            ],
                        },
                        {
                            "duty_type_name": "Наряд по курсу",
                            "duty_type_short_name": None,
                            "owner_unit_name": "1 курс",
                            "role_name": "Дневальный",
                            "start_time": "18:00:00",
                            "duration_minutes": 1440,
                            "headcount": 2,
                            "cells": [
                                {
                                    "executor_unit_name": None,
                                    "people": [_person("Борисов")],
                                    "missing": 1,
                                },
                                None,
                            ],
                        },
                    ],
                },
            )
        if path == "/rosters/daily":
            return httpx.Response(
                200,
                json={
                    "unit_id": request.url.params["unit_id"],
                    "unit_name": "1 курс",
                    "date": request.url.params["date"],
                    "day_kind": "workday",
                    "day_name": None,
                    "statuses": [self.status],
                    "duties": [
                        {
                            "duty_type_name": "Наряд по курсу",
                            "owner_unit_name": "1 курс",
                            "executor_unit_name": "1 курс",
                            "start_at": "2026-11-05T15:00:00Z",
                            "end_at": "2026-11-06T15:00:00Z",
                            "roles": [
                                {
                                    "role_name": "Дежурный",
                                    "headcount": 1,
                                    "people": [_person("Алексеев")],
                                    "missing": 0,
                                },
                                {
                                    "role_name": "Дневальный",
                                    "headcount": 2,
                                    "people": [],
                                    "missing": 2,
                                },
                            ],
                        }
                    ],
                },
            )
        return httpx.Response(404, json={"code": "not_found", "message": "Нет такого"})


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
def upstreams() -> FakeUpstreams:
    return FakeUpstreams()


@pytest.fixture(scope="session")
async def app(
    settings: DocumentsSettings,
    issuer: TestIssuer,
    migrated: str,
    personnel: FakePersonnel,
    upstreams: FakeUpstreams,
) -> AsyncIterator[FastAPI]:
    application = create_app(
        settings,
        token_verifier=issuer.verifier,
        personnel_transport=httpx.MockTransport(personnel.handler),
        scheduling_transport=httpx.MockTransport(upstreams.scheduling),
        org_transport=httpx.MockTransport(upstreams.org),
    )
    async with LifespanManager(application):
        yield application


@pytest.fixture(autouse=True)
async def clean(
    app: FastAPI, settings: DocumentsSettings, personnel: FakePersonnel, upstreams: FakeUpstreams
) -> None:
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE import_job, document_settings, print_template, audit_log, outbox")
        )
    await engine.dispose()
    personnel.calls.clear()
    personnel.stale = False
    upstreams.calls.clear()
    upstreams.status = "published"


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


@pytest.fixture
def sessionmaker(app: FastAPI) -> async_sessionmaker[AsyncSession]:
    maker: async_sessionmaker[AsyncSession] = app.state.db.sessionmaker
    return maker
