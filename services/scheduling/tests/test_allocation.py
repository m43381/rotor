"""Автораспределение: предпросмотр → применение, устаревание, пересборка, подразделения."""

import datetime as dt
import uuid
from typing import Any

from conftest import FAKE_JOBS, FAKE_PEOPLE, ClientFactory, Org, add_type, role
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dutyflow_common.audit import AuditLog
from dutyflow_common.ids import uuid7
from dutyflow_common.outbox import OutboxEvent
from scheduling.checks import PersonInfo
from scheduling.models import Assignment

_today = dt.date.today()
MONTH = (_today.replace(day=28) + dt.timedelta(days=5)).replace(day=1)


async def setup(
    admin: AsyncClient, org: Org, people: int = 12
) -> tuple[dict[str, Any], dict[str, Any]]:
    t = await add_type(
        admin,
        org.fac_a,
        "Наряд",
        roles=[role("Дежурный"), role("Дневальный", headcount=2)],
        start_time="08:00",
        duration_minutes=360,
        rest_hours=0,
    )
    roles = [uuid.UUID(r["id"]) for r in t["roles"]]
    for i in range(people):
        FAKE_PEOPLE.add(
            PersonInfo(
                id=uuid7(),
                unit_id=org.course_a1,
                is_active=True,
                last_name=f"Курсант{i:02d}",
                first_name="Иван",
                clearances=tuple((r, None, None) for r in roles),
            ),
            "1.2.3",
        )
    s = (
        await admin.post("/schedules", json={"unit_id": str(org.fac_a), "month": str(MONTH)})
    ).json()
    return t, s


async def allocate(client: AsyncClient, schedule_id: str, **body: Any) -> Any:
    return await client.post(f"/schedules/{schedule_id}/allocate", json=body)


async def count_assignments(sessionmaker: async_sessionmaker[AsyncSession], **filters: Any) -> int:
    async with sessionmaker() as session:
        stmt = select(func.count()).select_from(Assignment)
        for key, value in filters.items():
            stmt = stmt.where(getattr(Assignment, key) == value)
        return int(await session.scalar(stmt) or 0)


async def test_preview_then_apply(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    _, s = await setup(admin, org)
    r = await allocate(admin, s["id"])
    assert r.status_code == 201, r.text
    run = r.json()
    places = run["metrics"]["places"]
    assert run["status"] == "preview_ready"
    assert places > 0
    assert run["filled"] == places == len(run["decisions"])
    d = run["decisions"][0]
    assert d["chosen_name"].startswith("Курсант")
    assert d["role_name"] in {"Дежурный", "Дневальный"}
    assert set(d["features"]) == {"load", "same_type", "holiday", "recency"}
    assert all("name" in a for a in d["alternatives"])
    # Предпросмотр график не меняет
    assert await count_assignments(sessionmaker) == 0

    r = await admin.post(f"/allocation-runs/{run['id']}/apply")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "applied"
    assert await count_assignments(sessionmaker, source="auto") == places
    async with sessionmaker() as session:
        linked = await session.scalar(
            select(func.count())
            .select_from(Assignment)
            .where(Assignment.allocation_run_id == uuid.UUID(run["id"]))
        )
        actions = list(await session.scalars(select(AuditLog.action)))
    assert linked == places
    assert "allocation.apply" in actions
    assert actions.count("assignment.auto") == places

    # Повторно применить нельзя; таблица показывает заполненные ячейки
    assert (await admin.post(f"/allocation-runs/{run['id']}/apply")).status_code == 422
    table = (await admin.get(f"/schedules/{s['id']}/table")).json()
    duty = next(x for x in table["rows"] if x["role_name"] == "Дежурный")
    assert all(c["filled"] == 1 for c in duty["cells"] if c)


async def test_stale_preview_rejected(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    _, s = await setup(admin, org)
    run = (await allocate(admin, s["id"])).json()
    # Пока смотрели предпросмотр, кто-то назначил человека вручную
    table = (await admin.get(f"/schedules/{s['id']}/table")).json()
    cell = next(c for c in table["rows"][0]["cells"] if c)
    person = next(iter(FAKE_PEOPLE.people.values()))[0]
    r = await admin.post(f"/day-plans/{cell['id']}/assignments", json={"person_id": str(person.id)})
    assert r.status_code == 201, r.text

    r = await admin.post(f"/allocation-runs/{run['id']}/apply")
    assert r.status_code == 409
    assert r.json()["code"] == "run_stale"
    assert (await admin.get(f"/allocation-runs/{run['id']}")).json()["status"] == "stale"
    assert await count_assignments(sessionmaker, source="auto") == 0


async def test_rebuild_keeps_manual(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    _, s = await setup(admin, org)
    table = (await admin.get(f"/schedules/{s['id']}/table")).json()
    cell = next(c for c in table["rows"][0]["cells"] if c)
    manual = next(iter(FAKE_PEOPLE.people.values()))[0]
    await admin.post(f"/day-plans/{cell['id']}/assignments", json={"person_id": str(manual.id)})
    first = (await allocate(admin, s["id"])).json()
    await admin.post(f"/allocation-runs/{first['id']}/apply")
    total = await count_assignments(sessionmaker)

    rebuild = (await allocate(admin, s["id"], mode="rebuild", seed=7)).json()
    assert len(rebuild["metrics"]["removed"]) == first["filled"]
    r = await admin.post(f"/allocation-runs/{rebuild['id']}/apply")
    assert r.status_code == 200, r.text
    assert await count_assignments(sessionmaker) == total
    assert await count_assignments(sessionmaker, source="manual") == 1
    # Снятые пересборкой — с событием для read-model аналитики, новые — тоже
    async with sessionmaker() as session:
        kinds = [
            e
            for e in await session.scalars(
                select(OutboxEvent.event_type).where(OutboxEvent.aggregate_type == "assignment")
            )
        ]
    assert kinds.count("assignment.removed") == first["filled"]
    assert kinds.count("assignment.created") == 1 + first["filled"] + rebuild["metrics"]["filled"]

    # Дозаполнение, когда всё заполнено: ничего не предлагается
    fill = (await allocate(admin, s["id"])).json()
    assert fill["metrics"]["places"] == 0


async def test_units_allocation(admin: AsyncClient, org: Org) -> None:
    _, s = await setup(admin, org)
    r = await allocate(admin, s["id"], kind="units")
    run = r.json()
    assert run["kind"] == "units"
    assert run["filled"] == run["metrics"]["places"] > 0
    assert {d["chosen_name"] for d in run["decisions"]} == {"Курс A1"}
    assert run["decisions"][0]["rejected"]["capacity"] == {str(org.course_a1): 12}
    r = await admin.post(f"/allocation-runs/{run['id']}/apply")
    assert r.status_code == 200, r.text
    table = (await admin.get(f"/schedules/{s['id']}/table")).json()
    states = {c["state"] for row in table["rows"] for c in row["cells"] if c}
    assert states == {"delegated_pending"}
    course = (
        await admin.get("/schedules", params={"month": str(MONTH), "unit_id": str(org.course_a1)})
    ).json()[0]
    assert course["pending_incoming"] == run["filled"]


async def test_scope_deficits_discard_history(
    client_for: ClientFactory, admin: AsyncClient, org: Org
) -> None:
    _, s = await setup(admin, org, people=1)  # один человек на три места в день
    table = (await admin.get(f"/schedules/{s['id']}/table")).json()
    first_day = [c["id"] for row in table["rows"] for c in row["cells"][:1] if c]
    run = (await allocate(admin, s["id"], cell_ids=first_day)).json()
    assert run["metrics"]["cells"] == 2
    assert run["metrics"]["places"] == 3
    assert run["filled"] == 1
    assert run["metrics"]["deficits"]
    assert "нужно 2, допустимых 1" in run["metrics"]["deficits"][0]["message"]

    viewer = client_for(org.fac_a, "viewer")
    assert (await viewer.get(f"/allocation-runs/{run['id']}")).status_code == 200
    assert (await allocate(viewer, s["id"])).status_code == 403
    assert (await viewer.post(f"/allocation-runs/{run['id']}/apply")).status_code == 403
    fac_b = client_for(org.fac_b, "operator")
    assert (await fac_b.get(f"/allocation-runs/{run['id']}")).status_code == 404

    r = await admin.post(f"/allocation-runs/{run['id']}/discard")
    assert r.json()["status"] == "discarded"
    assert (await admin.post(f"/allocation-runs/{run['id']}/apply")).status_code == 422
    history = (await admin.get(f"/schedules/{s['id']}/allocation-runs")).json()
    assert [h["status"] for h in history] == ["discarded"]


async def test_background_run_with_chosen_method(
    client_for: ClientFactory,
    admin: AsyncClient,
    org: Org,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    _, s = await setup(admin, org)
    # Выбирать метод может только суперадминистратор (open-questions №46)
    fac_op = client_for(org.fac_a, "operator")
    assert (await allocate(fac_op, s["id"], method="greedy")).status_code == 403

    # Явный CP-SAT — в фоне, с увеличенным пределом времени
    r = await allocate(admin, s["id"], method="cpsat")
    assert r.status_code == 201, r.text
    run = r.json()
    assert (run["status"], run["decisions"]) == ("queued", [])
    assert run["config"]["cpsat_time_limit_s"] == 1.0  # фоновый предел из настроек
    assert (await admin.post(f"/allocation-runs/{run['id']}/apply")).status_code == 422

    first = (await admin.get(f"/allocation-runs/{run['id']}")).json()
    assert first["status"] == "running"
    ready = (await admin.get(f"/allocation-runs/{run['id']}")).json()
    assert ready["status"] == "preview_ready"
    assert ready["method"] == "cpsat"
    assert ready["filled"] == ready["metrics"]["places"] == len(ready["decisions"])
    assert ready["filled_optimal"] is True  # все места закрыты и совпали с границей max-flow
    r = await admin.post(f"/allocation-runs/{run['id']}/apply")
    assert r.status_code == 200, r.text
    assert await count_assignments(sessionmaker, source="auto") == ready["filled"]


async def test_background_failure_and_discard(admin: AsyncClient, org: Org, app: Any) -> None:
    _, s = await setup(admin, org)
    FAKE_JOBS.fail = True
    run = (await allocate(admin, s["id"], method="cpsat")).json()
    await admin.get(f"/allocation-runs/{run['id']}")
    failed = (await admin.get(f"/allocation-runs/{run['id']}")).json()
    assert (failed["status"], failed["error"]) == ("failed", "Движок упал")

    # Большой снимок — тоже в фоне; пока считается, прогон можно отменить
    FAKE_JOBS.fail = False
    app.state.settings.allocation_async_people = 0
    try:
        queued = (await allocate(admin, s["id"])).json()
    finally:
        app.state.settings.allocation_async_people = 3_000
    assert queued["status"] == "queued"
    r = await admin.post(f"/allocation-runs/{queued['id']}/discard")
    assert r.json()["status"] == "discarded"
