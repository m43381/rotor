"""Удаление записей справочников (ADR-0023): только неиспользуемых, иначе — объяснение где."""

from typing import Any

import pytest
from conftest import LISTENER, ClientFactory, Org, add_person
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from dutyflow_common.outbox import OutboxEvent

LEAVE = "00000000-0000-7000-8000-00000000e002"


@pytest.fixture
def scheduling_usage(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Подменяет опрос scheduling: `state["answer"]` — его ответ, `state["asked"]` — запросы."""
    state: dict[str, Any] = {"answer": {}, "asked": []}

    async def fake(kind: str, body: dict[str, Any]) -> dict[str, int]:
        state["asked"].append((kind, body))
        return dict(state["answer"])

    monkeypatch.setattr(app.state, "usage", fake)
    return state


async def test_delete_position_checks_people_and_scheduling(
    admin: AsyncClient,
    client_for: ClientFactory,
    org: Org,
    app: FastAPI,
    scheduling_usage: dict[str, Any],
) -> None:
    pos = (await admin.post("/positions", json={"name": "Старшина курса"})).json()
    person = await add_person(admin, org.fac_a, "Должностной", position_id=pos["id"])

    op = client_for(org.root, "unit_admin")
    assert (await op.delete(f"/positions/{pos['id']}")).status_code == 403

    r = await admin.delete(f"/positions/{pos['id']}")
    assert r.status_code == 409
    assert "людей (включая архивных): 1" in r.text

    # Человек больше не на должности, но её требует роль наряда
    await admin.patch(
        f"/people/{person['id']}", json={"position_id": None, "version": person["version"]}
    )
    scheduling_usage["answer"] = {"duty_roles": 2, "duty_limits": 0}
    r = await admin.delete(f"/positions/{pos['id']}")
    assert r.status_code == 409
    assert "ролей нарядов (требования или закрепление): 2" in r.text
    assert scheduling_usage["asked"][-1] == ("position", {"id": pos["id"], "code": None})

    scheduling_usage["answer"] = {}
    assert (await admin.delete(f"/positions/{pos['id']}")).status_code == 204
    assert pos["id"] not in {p["id"] for p in (await admin.get("/positions")).json()}
    async with app.state.db.sessionmaker() as session:
        types = (
            await session.scalars(
                select(OutboxEvent.event_type).where(OutboxEvent.aggregate_id == pos["id"])
            )
        ).all()
    assert "position.deleted" in types


async def test_delete_category_reason_and_attribute(
    admin: AsyncClient, org: Org, scheduling_usage: dict[str, Any]
) -> None:
    # Категория людей не удаляется, пока она у кого-то есть
    await add_person(admin, org.fac_a, "Слушателев", category_id=str(LISTENER))
    assert (await admin.delete(f"/person-categories/{LISTENER}")).status_code == 409

    spare = await admin.post(
        "/person-categories", json={"code": "spare", "name": "Лишняя", "sort_order": 9}
    )
    assert (await admin.delete(f"/person-categories/{spare.json()['id']}")).status_code == 204

    # Причина освобождения — только свои ссылки, scheduling не спрашивается
    reason = (
        await admin.post(
            "/exemption-reasons", json={"code": "test_trip", "name": "Тестовая поездка"}
        )
    ).json()
    person = await add_person(admin, org.fac_a, "Отпускник")
    await admin.post(
        f"/people/{person['id']}/exemptions",
        json={"reason_id": reason["id"], "date_from": "2026-10-01", "date_to": "2026-10-02"},
    )
    asked_before = len(scheduling_usage["asked"])
    r = await admin.delete(f"/exemption-reasons/{reason['id']}")
    assert r.status_code == 409
    assert "освобождений: 1" in r.text
    assert len(scheduling_usage["asked"]) == asked_before
    unused = (await admin.post("/exemption-reasons", json={"code": "test_x", "name": "X"})).json()
    assert (await admin.delete(f"/exemption-reasons/{unused['id']}")).status_code == 204

    # Характеристику ищут в требованиях ролей по коду
    attr = (
        await admin.post(
            "/attribute-definitions", json={"code": "height", "name": "Рост", "value_type": "int"}
        )
    ).json()
    scheduling_usage["answer"] = {"duty_roles": 1}
    assert (await admin.delete(f"/attribute-definitions/{attr['id']}")).status_code == 409
    assert scheduling_usage["asked"][-1] == (
        "attribute_definition",
        {"id": attr["id"], "code": "height"},
    )
    scheduling_usage["answer"] = {}
    assert (await admin.delete(f"/attribute-definitions/{attr['id']}")).status_code == 204


async def test_delete_person_only_without_assignments(
    admin: AsyncClient,
    client_for: ClientFactory,
    org: Org,
    scheduling_usage: dict[str, Any],
) -> None:
    """ADR-0023: ошибочно заведённого человека можно удалить, если его не назначали в наряды."""
    person = await add_person(admin, org.fac_a, "Ошибочный")
    await admin.post(
        f"/people/{person['id']}/exemptions",
        json={"reason_id": LEAVE, "date_from": "2026-10-01", "date_to": "2026-10-02"},
    )
    params = {"version": person["version"]}

    op = client_for(org.root, "unit_admin")
    assert (await op.delete(f"/people/{person['id']}", params=params)).status_code == 403

    scheduling_usage["answer"] = {"assignments": 4}
    r = await admin.delete(f"/people/{person['id']}", params=params)
    assert r.status_code == 409
    assert "назначений в наряды: 4" in r.text
    assert "исключить из списков" in r.text
    assert scheduling_usage["asked"][-1] == ("person", {"id": person["id"]})

    scheduling_usage["answer"] = {}
    assert (await admin.delete(f"/people/{person['id']}", params=params)).status_code == 204
    assert (await admin.get(f"/people/{person['id']}")).status_code == 404
