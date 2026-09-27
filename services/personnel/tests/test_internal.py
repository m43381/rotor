from conftest import Org, add_person
from httpx import AsyncClient

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
        attributes={"category": "Курсант"},
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
    assert people[0]["attributes"] == {"category": "Курсант"}
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
