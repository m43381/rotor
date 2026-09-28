from conftest import ClientFactory
from httpx import AsyncClient

from org.settings import OrgSettings


async def test_ranks_ordered_and_readonly_for_operator(
    admin: AsyncClient, client_for: ClientFactory, settings: OrgSettings
) -> None:
    for name, order in [("Майор", 30), ("Рядовой", 1), ("Лейтенант", 20)]:
        r = await admin.post("/ranks", json={"name": name, "order": order})
        assert r.status_code == 201, r.text

    op = client_for(settings.root_unit_id, "operator")
    names = [r["name"] for r in (await op.get("/ranks")).json()]
    assert names == ["Рядовой", "Лейтенант", "Майор"]
    assert (await op.post("/ranks", json={"name": "X", "order": 5})).status_code == 403


async def test_rank_order_unique(admin: AsyncClient) -> None:
    assert (await admin.post("/ranks", json={"name": "A", "order": 1})).status_code == 201
    assert (await admin.post("/ranks", json={"name": "B", "order": 1})).status_code == 409


async def test_calendar_upsert_and_range(admin: AsyncClient) -> None:
    r = await admin.put(
        "/calendar/2026-11-04",
        json={"date": "2026-11-04", "kind": "holiday", "name": "День народного единства"},
    )
    assert r.status_code == 200
    r = await admin.get("/calendar", params={"date_from": "2026-11-01", "date_to": "2026-11-30"})
    assert [d["date"] for d in r.json()] == ["2026-11-04"]
    assert (await admin.delete("/calendar/2026-11-04")).status_code == 204


async def test_unit_type_code_validated(admin: AsyncClient) -> None:
    r = await admin.post("/unit-types", json={"code": "Bad Code", "name": "x", "level": 1})
    assert r.status_code == 422


async def test_reference_updates_are_audited(admin: AsyncClient) -> None:
    rank = (await admin.post("/ranks", json={"name": "Сержант", "order": 5})).json()
    r = await admin.put(
        f"/ranks/{rank['id']}",
        json={"name": "Младший сержант", "short_name": "мл. с-т", "order": 5},
    )
    assert r.status_code == 200, r.text
    assert r.json()["short_name"] == "мл. с-т"
    kind = (
        await admin.post("/unit-types", json={"code": "platoon", "name": "Взвод", "level": 5})
    ).json()
    r = await admin.put(
        f"/unit-types/{kind['id']}", json={"code": "platoon", "name": "Учебный взвод", "level": 5}
    )
    assert r.status_code == 200, r.text
    audit = (await admin.get("/audit", params={"entity_id": rank["id"]})).json()["items"]
    assert [a["action"] for a in audit] == ["rank.update", "rank.create"]
