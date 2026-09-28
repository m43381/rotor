from conftest import ClientFactory, Org, add_person
from httpx import AsyncClient

ILLNESS = "00000000-0000-7000-8000-00000000e001"
LEAVE = "00000000-0000-7000-8000-00000000e002"


async def test_exemption_crud_and_overlap(admin: AsyncClient, org: Org) -> None:
    person = await add_person(admin, org.fac_a, "Болеющий")
    url = f"/people/{person['id']}/exemptions"
    r = await admin.post(
        url, json={"reason_id": LEAVE, "date_from": "2026-10-01", "date_to": "2026-10-10"}
    )
    assert r.status_code == 201, r.text
    exemption = r.json()

    overlap = await admin.post(
        url, json={"reason_id": ILLNESS, "date_from": "2026-10-10", "date_to": "2026-10-12"}
    )
    assert overlap.status_code == 409
    assert "пересекается" in overlap.json()["message"]
    # Смежный период (без общего дня) — можно
    adjacent = await admin.post(
        url, json={"reason_id": ILLNESS, "date_from": "2026-10-11", "date_to": "2026-10-12"}
    )
    assert adjacent.status_code == 201

    bad = await admin.post(
        url, json={"reason_id": ILLNESS, "date_from": "2026-11-05", "date_to": "2026-11-01"}
    )
    assert bad.status_code == 422

    upd = await admin.put(
        f"/exemptions/{exemption['id']}",
        json={
            "reason_id": LEAVE,
            "date_from": "2026-10-01",
            "date_to": "2026-10-05",
            "comment": "Сократили",
            "version": exemption["version"],
        },
    )
    assert upd.status_code == 200
    assert (await admin.delete(f"/exemptions/{exemption['id']}")).status_code == 204

    card = (await admin.get(f"/people/{person['id']}")).json()
    assert [(e["date_from"], e["date_to"]) for e in card["exemptions"]] == [
        ("2026-10-11", "2026-10-12")
    ]


async def test_bulk_exemption_partial(
    admin: AsyncClient, client_for: ClientFactory, org: Org
) -> None:
    a = await add_person(admin, org.fac_a, "Первый")
    b = await add_person(admin, org.fac_a, "Второй")
    foreign = await add_person(admin, org.fac_b, "Чужой")
    await admin.post(
        f"/people/{b['id']}/exemptions",
        json={"reason_id": ILLNESS, "date_from": "2026-12-01", "date_to": "2026-12-03"},
    )

    op_a = client_for(org.fac_a, "operator")
    r = await op_a.post(
        "/exemptions/bulk",
        json={
            "person_ids": [a["id"], b["id"], foreign["id"]],
            "reason_id": LEAVE,
            "date_from": "2026-12-02",
            "date_to": "2026-12-20",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["done"] == 1
    reasons = {s["person_id"]: s["reason"] for s in body["skipped"]}
    assert "пересекается" in reasons[b["id"]]
    assert "вне зоны" in reasons[foreign["id"]]


async def test_viewer_cannot_add_exemption(
    admin: AsyncClient, client_for: ClientFactory, org: Org
) -> None:
    person = await add_person(admin, org.fac_a, "Смотримый")
    viewer = client_for(org.fac_a, "viewer")
    r = await viewer.post(
        f"/people/{person['id']}/exemptions",
        json={"reason_id": LEAVE, "date_from": "2026-10-01", "date_to": "2026-10-02"},
    )
    assert r.status_code == 403


async def test_reasons_reference(admin: AsyncClient, client_for: ClientFactory, org: Org) -> None:
    codes = {r["code"] for r in (await admin.get("/exemption-reasons")).json()}
    assert {"illness", "leave", "trip", "other"} <= codes
    r = await admin.post("/exemption-reasons", json={"code": "exercise", "name": "Учения"})
    assert r.status_code == 201
    op = client_for(org.fac_a, "operator")
    assert (await op.post("/exemption-reasons", json={"code": "x", "name": "X"})).status_code == 403


async def test_reference_updates_are_audited(admin: AsyncClient) -> None:
    position = await admin.post("/positions", json={"name": "Командир отделения"})
    assert position.status_code == 201, position.text
    pid = position.json()["id"]
    r = await admin.put(f"/positions/{pid}", json={"name": "Командир отделения", "sort_order": 3})
    assert r.status_code == 200, r.text
    reason = (
        await admin.post("/exemption-reasons", json={"code": "study", "name": "Учёба"})
    ).json()
    r = await admin.put(
        f"/exemption-reasons/{reason['id']}", json={"code": "study", "name": "Учебный сбор"}
    )
    assert r.status_code == 200, r.text
    attr = await admin.post(
        "/attribute-definitions",
        json={"code": "sport", "name": "Спортсмен", "value_type": "bool"},
    )
    assert attr.status_code == 201, attr.text
    r = await admin.put(
        f"/attribute-definitions/{attr.json()['id']}",
        json={"code": "sport", "name": "Спортсмен-разрядник", "value_type": "bool"},
    )
    assert r.status_code == 200, r.text
    # Тип характеристики менять нельзя
    bad = await admin.put(
        f"/attribute-definitions/{attr.json()['id']}",
        json={"code": "sport", "name": "Спорт", "value_type": "string"},
    )
    assert bad.status_code == 422
    history = (await admin.get("/audit", params={"entity_id": pid})).json()["items"]
    assert [a["action"] for a in history] == ["position.update", "position.create"]
