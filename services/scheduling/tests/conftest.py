"""Интеграционные тесты scheduling на PostgreSQL 16 (testcontainers).

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

from dutyflow_common.events import Event
from dutyflow_common.ids import uuid7
from dutyflow_common.projections import handle_rank_event, handle_unit_event
from dutyflow_common.testing import TestIssuer
from scheduling.main import create_app
from scheduling.refs import AttributeDef, PersonnelRefs
from scheduling.settings import SchedulingSettings

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
def settings(database_url: str) -> SchedulingSettings:
    return SchedulingSettings(database_url=database_url, internal_token=INTERNAL_TOKEN)


@pytest.fixture(scope="session")
def migrated(database_url: str) -> str:
    cfg = Config(str(SERVICE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVICE_DIR / "migrations"))
    os.environ["DATABASE_URL"] = database_url
    command.upgrade(cfg, "head")
    return database_url


# Справочники personnel, на которые ссылаются требования ролей (в тестах — без HTTP).
POSITION_OFFICER = uuid.UUID("00000000-0000-7000-8000-0000000000a1")
POSITION_OLD = uuid.UUID("00000000-0000-7000-8000-0000000000a2")
REFS = PersonnelRefs(
    positions={POSITION_OFFICER: True, POSITION_OLD: False},
    attributes={
        "category": AttributeDef(
            "category", "Категория", "enum", ["Курсант", "Слушатель", "Постоянный состав"], True
        ),
        "course_no": AttributeDef("course_no", "Курс", "int", None, True),
    },
)


async def load_refs() -> PersonnelRefs:
    return REFS


@pytest.fixture(scope="session")
def issuer(settings: SchedulingSettings) -> TestIssuer:
    return TestIssuer(settings)


@pytest.fixture(scope="session")
async def app(
    settings: SchedulingSettings, issuer: TestIssuer, migrated: str
) -> AsyncIterator[FastAPI]:
    application = create_app(settings, token_verifier=issuer.verifier, refs_loader=load_refs)
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
async def org(app: FastAPI, settings: SchedulingSettings) -> Org:
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE day_plan, schedule, duty_role, duty_type, unit_projection,"
                " rank_projection, calendar_projection, audit_log, outbox, processed_event CASCADE"
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


def role(name: str = "Дежурный", **extra: object) -> dict[str, object]:
    return {"name": name, **extra}


async def add_type(
    client: AsyncClient,
    owner: uuid.UUID,
    name: str = "Наряд по курсу",
    roles: list[dict[str, object]] | None = None,
    **extra: object,
) -> dict[str, object]:
    r = await client.post(
        "/duty-types",
        json={
            "name": name,
            "owner_unit_id": str(owner),
            "start_time": "18:00",
            "duration_minutes": 24 * 60,
            "roles": roles or [role()],
            **extra,
        },
    )
    assert r.status_code == 201, r.text
    data: dict[str, object] = r.json()
    return data
