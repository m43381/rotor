"""Интеграционные тесты org на настоящем PostgreSQL 16 (testcontainers): ltree, триггеры и
exclusion-ограничения в SQLite не проверить. Нужен запущенный Docker."""

import os
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer

from dutyflow_common.testing import TestIssuer
from org.bootstrap import ensure_root
from org.main import create_app
from org.settings import OrgSettings

SERVICE_DIR = Path(__file__).resolve().parents[1]
INTERNAL_TOKEN = "test-internal-token"


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    external = os.environ.get("TEST_DATABASE_URL")
    if external:  # CI или заранее поднятая БД
        yield external
        return
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def settings(database_url: str) -> OrgSettings:
    return OrgSettings(database_url=database_url, internal_token=INTERNAL_TOKEN)


@pytest.fixture(scope="session")
def migrated(database_url: str) -> str:
    cfg = Config(str(SERVICE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVICE_DIR / "migrations"))
    os.environ["DATABASE_URL"] = database_url
    command.upgrade(cfg, "head")
    return database_url


@pytest.fixture(scope="session")
def issuer(settings: OrgSettings) -> TestIssuer:
    return TestIssuer(settings)


@pytest.fixture(scope="session")
async def app(settings: OrgSettings, issuer: TestIssuer, migrated: str) -> AsyncIterator[FastAPI]:
    application = create_app(settings, token_verifier=issuer.verifier)
    async with LifespanManager(application):
        yield application


@pytest.fixture(autouse=True)
async def clean_db(app: FastAPI, settings: OrgSettings) -> None:
    """Каждый тест начинается с пустого дерева и одного корня."""
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE unit, unit_type, rank, calendar_day, audit_log, outbox,"
                " processed_event RESTART IDENTITY CASCADE"
            )
        )
    await engine.dispose()
    await ensure_root(app.state.db.sessionmaker, settings)


type ClientFactory = Callable[..., AsyncClient]


@pytest.fixture
async def client_for(app: FastAPI, issuer: TestIssuer) -> AsyncIterator[ClientFactory]:
    """`client_for(unit_id, "operator")` — HTTP-клиент от имени оператора подразделения."""
    clients: list[AsyncClient] = []

    def make(unit_id: uuid.UUID, *roles: str, username: str = "tester") -> AsyncClient:
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
def admin(client_for: ClientFactory, settings: OrgSettings) -> AsyncClient:
    return client_for(settings.root_unit_id, "superadmin", username="admin")


@pytest.fixture
async def anon(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
