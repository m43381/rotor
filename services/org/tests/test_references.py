import uuid

import pytest
from conftest import ClientFactory
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text

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


async def test_delete_rank_only_when_unused(
    admin: AsyncClient,
    client_for: ClientFactory,
    settings: OrgSettings,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0022: org спрашивает personnel и scheduling; используемое звание не удаляется."""
    rank = (await admin.post("/ranks", json={"name": "Сержант", "order": 40})).json()
    usage: dict[str, int] = {"people": 2, "duty_roles": 1, "duty_limits": 0}
    asked: list[tuple[uuid.UUID, int]] = []

    async def fake_usage(rank_id: uuid.UUID, order: int) -> dict[str, int]:
        asked.append((rank_id, order))
        return usage

    monkeypatch.setattr(app.state, "rank_usage", fake_usage)

    op = client_for(settings.root_unit_id, "operator")
    assert (await op.delete(f"/ranks/{rank['id']}")).status_code == 403

    r = await admin.delete(f"/ranks/{rank['id']}")
    assert r.status_code == 409
    assert "людей (включая архивных): 2" in r.text
    assert "ролей нарядов" in r.text
    assert "лимитов" not in r.text
    assert asked == [(uuid.UUID(rank["id"]), 40)]

    usage = {"people": 0, "duty_roles": 0, "duty_limits": 0}
    assert (await admin.delete(f"/ranks/{rank['id']}")).status_code == 204
    assert (await admin.get("/ranks")).json() == []
    assert (await admin.delete(f"/ranks/{rank['id']}")).status_code == 404

    async with app.state.db.sessionmaker() as session:
        events = (
            (
                await session.execute(
                    text(
                        "SELECT event_type FROM outbox WHERE aggregate_id = :id"
                        " AND event_type LIKE 'rank.%' ORDER BY id"
                    ),
                    {"id": rank["id"]},
                )
            )
            .scalars()
            .all()
        )
        actions = (
            (
                await session.execute(
                    text("SELECT action FROM audit_log WHERE entity_id = :id ORDER BY id"),
                    {"id": rank["id"]},
                )
            )
            .scalars()
            .all()
        )
    assert events == ["rank.changed", "rank.deleted"]
    assert actions == ["rank.create", "rank.delete"]


async def test_delete_rank_refused_when_owner_unavailable(
    admin: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dutyflow_common.internal import ServiceUnavailableError

    rank = (await admin.post("/ranks", json={"name": "Майор", "order": 100})).json()

    async def down(rank_id: uuid.UUID, order: int) -> dict[str, int]:
        raise ServiceUnavailableError("Сервис недоступен: personnel")

    monkeypatch.setattr(app.state, "rank_usage", down)
    assert (await admin.delete(f"/ranks/{rank['id']}")).status_code == 503
    assert [r["name"] for r in (await admin.get("/ranks")).json()] == ["Майор"]
