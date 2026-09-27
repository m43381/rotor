"""Интеграционные тесты personnel на PostgreSQL 16 и Redis (testcontainers).

Дерево подразделений попадает в проекцию так же, как в работе, — через обработчик событий
`unit.*` (ADR-0011), а не прямой вставкой в таблицу.
"""

import os
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from dutyflow_common.events import Event
from dutyflow_common.ids import uuid7
from dutyflow_common.projections import handle_rank_event, handle_unit_event
from dutyflow_common.testing import TestIssuer
from personnel.main import create_app
from personnel.settings import PersonnelSettings

SERVICE_DIR = Path(__file__).resolve().parents[1]
INTERNAL_TOKEN = "test-internal-token"


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    external = os.environ.get("TEST_DATABASE_URL")
    if external:
        yield external
        return
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    with RedisContainer("redis:7-alpine") as r:
        yield f"redis://{r.get_container_host_ip()}:{r.get_exposed_port(6379)}/0"


@pytest.fixture(scope="session")
def settings(database_url: str) -> PersonnelSettings:
    return PersonnelSettings(database_url=database_url, internal_token=INTERNAL_TOKEN)


@pytest.fixture(scope="session")
def migrated(database_url: str) -> str:
    cfg = Config(str(SERVICE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVICE_DIR / "migrations"))
    os.environ["DATABASE_URL"] = database_url
    command.upgrade(cfg, "head")
    return database_url


@pytest.fixture(scope="session")
def issuer(settings: PersonnelSettings) -> TestIssuer:
    return TestIssuer(settings)


@pytest.fixture(scope="session")
async def app(
    settings: PersonnelSettings, issuer: TestIssuer, migrated: str
) -> AsyncIterator[FastAPI]:
    application = create_app(settings, token_verifier=issuer.verifier)
    async with LifespanManager(application):
        yield application


@pytest.fixture
def sessionmaker(app: FastAPI) -> async_sessionmaker[AsyncSession]:
    maker: async_sessionmaker[AsyncSession] = app.state.db.sessionmaker
    return maker


# --- дерево подразделений -----------------------------------------------------------------------


@dataclass
class Org:
    """Академия(1) → Факультет A(1.2) → Курс A1(1.2.3); Факультет B(1.4)."""

    root: uuid.UUID
    fac_a: uuid.UUID
    course_a1: uuid.UUID
    fac_b: uuid.UUID
    rank_private: uuid.UUID
    rank_major: uuid.UUID


async def emit(
    sessionmaker: async_sessionmaker[AsyncSession],
    event_type: str,
    aggregate: uuid.UUID,
    payload: dict[str, object],
) -> None:
    """Применяет событие org к проекциям — как это делает консьюмер."""
    handler = handle_unit_event if event_type.startswith("unit.") else handle_rank_event
    async with sessionmaker() as session, session.begin():
        await handler(session, Event(uuid7(), event_type, aggregate, dict(payload)))


def unit_payload(
    unit_id: uuid.UUID, parent: uuid.UUID | None, path: str, name: str, version: int = 1
) -> dict[str, object]:
    return {
        "unit_id": str(unit_id),
        "parent_id": str(parent) if parent else None,
        "path": path,
        "name": name,
        "short_name": None,
        "is_active": True,
        "version": version,
    }


@pytest.fixture(autouse=True)
async def org(app: FastAPI, settings: PersonnelSettings) -> Org:
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE person, person_attribute, exemption, clearance, position,"
                " unit_projection, rank_projection, duty_type_projection, duty_role_projection,"
                " audit_log, outbox, processed_event CASCADE"
            )
        )
        # Справочники из миграции (причины, характеристика «категория») не трогаем,
        # пользовательские — удаляем.
        await conn.execute(text("DELETE FROM attribute_definition WHERE code <> 'category'"))
        await conn.execute(
            text(
                "DELETE FROM exemption_reason WHERE code NOT IN ('illness','leave','trip','other')"
            )
        )
    await engine.dispose()

    maker: async_sessionmaker[AsyncSession] = app.state.db.sessionmaker
    o = Org(uuid7(), uuid7(), uuid7(), uuid7(), uuid7(), uuid7())
    for uid, parent, path, name in [
        (o.root, None, "1", "Академия"),
        (o.fac_a, o.root, "1.2", "Факультет A"),
        (o.course_a1, o.fac_a, "1.2.3", "Курс A1"),
        (o.fac_b, o.root, "1.4", "Факультет B"),
    ]:
        await emit(maker, "unit.created", uid, unit_payload(uid, parent, path, name))
    for rid, name, order in [(o.rank_private, "Рядовой", 10), (o.rank_major, "Майор", 100)]:
        await emit(maker, "rank.changed", rid, {"name": name, "order": order, "is_active": True})
    return o


# --- клиенты ------------------------------------------------------------------------------------

type ClientFactory = Callable[..., AsyncClient]


@pytest.fixture
async def client_for(app: FastAPI, issuer: TestIssuer) -> AsyncIterator[ClientFactory]:
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
def admin(client_for: ClientFactory, org: Org) -> AsyncClient:
    return client_for(org.root, "superadmin", username="admin")


@pytest.fixture
async def internal(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Internal-Token": INTERNAL_TOKEN},
    ) as c:
        yield c


async def add_person(
    client: AsyncClient, unit_id: uuid.UUID, last: str, first: str = "Иван", **extra: object
) -> dict[str, object]:
    r = await client.post(
        "/people", json={"unit_id": str(unit_id), "last_name": last, "first_name": first, **extra}
    )
    assert r.status_code == 201, r.text
    data: dict[str, object] = r.json()
    return data
