"""Тесты analytics на PostgreSQL 16 (testcontainers). Дерево подразделений попадает в
проекцию через обработчик событий `unit.*`, факты — через обработчики событий scheduling,
как в работе."""

import datetime as dt
import os
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from analytics.facts import handle_assignment_event, handle_schedule_event
from analytics.main import create_app
from analytics.settings import AnalyticsSettings
from dutyflow_common.events import Event
from dutyflow_common.ids import uuid7
from dutyflow_common.projections import handle_unit_event
from dutyflow_common.testing import TestIssuer

SERVICE_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    external = os.environ.get("TEST_DATABASE_URL")
    if external:
        yield external
        return
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def settings(database_url: str) -> AnalyticsSettings:
    return AnalyticsSettings(database_url=database_url)


@pytest.fixture(scope="session")
def migrated(database_url: str) -> str:
    cfg = Config(str(SERVICE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVICE_DIR / "migrations"))
    os.environ["DATABASE_URL"] = database_url
    command.upgrade(cfg, "head")
    return database_url


@pytest.fixture(scope="session")
def issuer(settings: AnalyticsSettings) -> TestIssuer:
    return TestIssuer(settings)


@pytest.fixture(scope="session")
async def app(
    settings: AnalyticsSettings, issuer: TestIssuer, migrated: str
) -> AsyncIterator[FastAPI]:
    application = create_app(settings, token_verifier=issuer.verifier)
    async with LifespanManager(application):
        yield application


@pytest.fixture
def sessionmaker(app: FastAPI) -> async_sessionmaker[AsyncSession]:
    maker: async_sessionmaker[AsyncSession] = app.state.db.sessionmaker
    return maker


@dataclass
class Org:
    """Академия(1) → Факультет A(1.2) → Курс A1(1.2.3), Курс A2(1.2.4); Факультет B(1.5)."""

    root: uuid.UUID
    fac_a: uuid.UUID
    course_a1: uuid.UUID
    course_a2: uuid.UUID
    fac_b: uuid.UUID


async def emit(
    sessionmaker: async_sessionmaker[AsyncSession], event_type: str, payload: dict[str, Any]
) -> None:
    handler = (
        handle_unit_event
        if event_type.startswith("unit.")
        else handle_assignment_event
        if event_type.startswith("assignment.")
        else handle_schedule_event
    )
    async with sessionmaker() as session, session.begin():
        aggregate = uuid.UUID(str(payload.get("unit_id") or payload.get("assignment_id")))
        await handler(session, Event(uuid7(), event_type, aggregate, payload))


@pytest.fixture(autouse=True)
async def org(app: FastAPI, settings: AnalyticsSettings) -> Org:
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE duty_fact, audit_view, unit_projection, processed_event, person_dim,"
                " category_dim"
            )
        )
    await engine.dispose()
    maker: async_sessionmaker[AsyncSession] = app.state.db.sessionmaker
    o = Org(uuid7(), uuid7(), uuid7(), uuid7(), uuid7())
    for uid, parent, path, name in [
        (o.root, None, "1", "Академия"),
        (o.fac_a, o.root, "1.2", "Факультет A"),
        (o.course_a1, o.fac_a, "1.2.3", "Курс A1"),
        (o.course_a2, o.fac_a, "1.2.4", "Курс A2"),
        (o.fac_b, o.root, "1.5", "Факультет B"),
    ]:
        await emit(
            maker,
            "unit.created",
            {
                "unit_id": str(uid),
                "parent_id": str(parent) if parent else None,
                "path": path,
                "name": name,
                "short_name": None,
                "is_active": True,
                "version": 1,
            },
        )
    return o


def fact(
    *,
    person: uuid.UUID,
    unit: uuid.UUID,
    date: dt.date,
    schedule: uuid.UUID,
    status: str = "published",
    days: int = 1,
    weight: float = 1.0,
    holiday: bool = False,
    name: str = "Иванов И. И.",
    duty: str = "Наряд",
    role: str = "Дежурный",
    source: str = "auto",
) -> dict[str, Any]:
    start = dt.datetime.combine(date, dt.time(15), tzinfo=dt.UTC)
    return {
        "assignment_id": str(uuid7()),
        "day_plan_id": str(uuid7()),
        "schedule_id": str(schedule),
        "schedule_status": status,
        "person_id": str(person),
        "person_name": name,
        "unit_id": str(unit),
        "duty_type_id": str(uuid.UUID(int=1)),
        "duty_role_id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{duty}:{role}")),
        "duty_type_name": duty,
        "role_name": role,
        "date": date.isoformat(),
        "start_at": start.isoformat(),
        "end_at": (start + dt.timedelta(days=days)).isoformat(),
        "occupied_days": days,
        "load": days * weight,
        "holiday": holiday,
        "source": source,
    }


type ClientFactory = Callable[..., AsyncClient]


@pytest.fixture
async def client_for(app: FastAPI, issuer: TestIssuer) -> AsyncIterator[ClientFactory]:
    clients: list[AsyncClient] = []

    def make(unit_id: uuid.UUID, *roles: str) -> AsyncClient:
        token = issuer.token(unit_id=unit_id, roles=list(roles))
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
