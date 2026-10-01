import uuid

from conftest import Org, add_person, emit
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from dutyflow_common.projections import RankProjection

LEAVE = "00000000-0000-7000-8000-00000000e002"


async def test_internal_requires_token(app: object, org: Org) -> None:
    from httpx import ASGITransport

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:  # type: ignore[arg-type]
        r = await c.post(
            "/internal/people/batch",
            json={"unit_ids": [str(org.root)], "date_from": "2026-10-01", "date_to": "2026-10-31"},
        )
    assert r.status_code == 401


async def test_people_batch_snapshot(admin: AsyncClient, internal: AsyncClient, org: Org) -> None:
    a = await add_person(
        admin,
        org.course_a1,
        "Снимков",
        rank_id=str(org.rank_major),
        attributes={"skill": "1 класс"},
    )
    b = await add_person(admin, org.fac_b, "Другой")
    archived = await add_person(admin, org.fac_a, "Архивный")
    await admin.post(f"/people/{archived['id']}/archive", json={"version": archived["version"]})
    await admin.post(
        f"/people/{a['id']}/exemptions",
        json={"reason_id": LEAVE, "date_from": "2026-09-25", "date_to": "2026-10-03"},
    )
    await admin.post(
        f"/people/{a['id']}/exemptions",
        json={"reason_id": LEAVE, "date_from": "2026-12-01", "date_to": "2026-12-05"},
    )  # вне периода

    r = await internal.post(
        "/internal/people/batch",
        json={"unit_ids": [str(org.fac_a)], "date_from": "2026-10-01", "date_to": "2026-10-31"},
    )
    assert r.status_code == 200
    people = r.json()
    assert [p["id"] for p in people] == [a["id"]]  # поддерево A, без архивных и без B
    assert people[0]["rank_order"] == 100
    assert people[0]["attributes"] == {"skill": "1 класс"}
    assert people[0]["exemptions"] == [["2026-09-25", "2026-10-03"]]

    only_unit = await internal.post(
        "/internal/people/batch",
        json={
            "unit_ids": [str(org.fac_b)],
            "include_descendants": False,
            "date_from": "2026-10-01",
            "date_to": "2026-10-31",
        },
    )
    assert [p["id"] for p in only_unit.json()] == [b["id"]]


async def test_availability_masks(admin: AsyncClient, internal: AsyncClient, org: Org) -> None:
    a = await add_person(admin, org.fac_a, "Маскин")
    await admin.post(
        f"/people/{a['id']}/exemptions",
        json={"reason_id": LEAVE, "date_from": "2026-09-30", "date_to": "2026-10-02"},
    )
    await admin.post(
        f"/people/{a['id']}/exemptions",
        json={"reason_id": LEAVE, "date_from": "2026-10-05", "date_to": "2026-10-05"},
    )
    r = await internal.post(
        "/internal/people/availability-batch",
        json={"person_ids": [a["id"]], "date_from": "2026-10-01", "date_to": "2026-10-07"},
    )
    assert r.json() == {"date_from": "2026-10-01", "days": 7, "masks": {a["id"]: "0011011"}}


async def test_people_batch_by_ids_with_names(
    admin: AsyncClient, internal: AsyncClient, org: Org
) -> None:
    a = await add_person(admin, org.course_a1, "Именной", rank_id=str(org.rank_major))
    gone = await add_person(admin, org.fac_b, "Ушедший")
    await admin.post(f"/people/{gone['id']}/archive", json={"version": gone["version"]})
    period = {"date_from": "2026-10-01", "date_to": "2026-10-31"}
    r = await internal.post(
        "/internal/people/batch",
        json={"person_ids": [a["id"], gone["id"]], "include_names": True, **period},
    )
    people = {p["last_name"]: p for p in r.json()}
    assert people["Именной"]["rank_name"] == "Майор"
    assert people["Именной"]["is_active"] is True
    assert people["Ушедший"]["is_active"] is False  # исключённые тоже — по id
    bad = await internal.post("/internal/people/batch", json=period)
    assert bad.status_code == 422


async def test_availability_for_50k_ids(
    admin: AsyncClient, internal: AsyncClient, org: Org
) -> None:
    """Список id длиннее лимита параметров asyncpg (32 767) — передаётся одним массивом."""
    a = await add_person(admin, org.course_a1, "Массовый")
    ids = [a["id"], *(str(uuid.uuid4()) for _ in range(49_999))]
    r = await internal.post(
        "/internal/people/availability-batch",
        json={"person_ids": ids, "date_from": "2026-10-01", "date_to": "2026-10-03"},
    )
    assert r.status_code == 200, r.text[:300]
    assert r.json()["masks"] == {a["id"]: "111"}


async def test_rank_usage_counts_archived_people_and_deleted_rank_leaves_projection(
    admin: AsyncClient, internal: AsyncClient, org: Org, app: FastAPI
) -> None:
    """ADR-0022: org удаляет звание, только если его не носит никто, включая архивных."""
    body = {"id": str(org.rank_major), "order": 100}
    assert (await internal.post("/internal/usage/rank", json=body)).json() == {"people": 0}

    p = await add_person(admin, org.fac_a, "Архивный", rank_id=str(org.rank_major))
    await admin.post(f"/people/{p['id']}/archive", json={"version": p["version"]})
    assert (await internal.post("/internal/usage/rank", json=body)).json() == {"people": 1}
    unit = {"id": str(org.fac_a)}
    assert (await internal.post("/internal/usage/unit", json=unit)).json() == {"people": 1}
    assert (await internal.post("/internal/usage/other", json=unit)).json() == {}

    maker = app.state.db.sessionmaker
    await emit(maker, "rank.deleted", org.rank_private, {"order": 10})
    async with maker() as session:
        ids = set((await session.scalars(select(RankProjection.rank_id))).all())
    assert ids == {org.rank_major}
