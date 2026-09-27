"""Данные для печатных форм (фаза 6b): месяц графика и суточный наряд поддерева."""

import uuid

from conftest import ClientFactory, Org
from httpx import AsyncClient
from test_assignments import MONTH, assign, person, setup


async def test_schedule_print_people_and_delegated(admin: AsyncClient, org: Org) -> None:
    s = await setup(admin, org)
    p = person(org, s, "Алексеев")
    assert (await assign(admin, s.cell("Дежурный", 1), p)).status_code == 201
    # Дневальных на 2-е число передаём курсу: в графике факультета — имя курса
    r = await admin.post(
        f"/schedules/{s.schedule['id']}/delegate",
        json={"cell_ids": [s.cell("Дневальный", 2)], "executor_unit_id": str(org.course_a1)},
    )
    assert r.status_code == 200, r.text

    data = (await admin.get(f"/schedules/{s.schedule['id']}/print")).json()
    assert data["schedule"]["unit_name"] == "Факультет A"
    rows = {r["role_name"]: r for r in data["rows"]}
    first = rows["Дежурный"]["cells"][0]
    assert first["missing"] == 0
    assert first["people"][0]["rank_name"] == "Рядовой"
    assert first["people"][0]["short_name"] == "Алексеев И. П."
    assert first["people"][0]["unit_name"] == "Курс A1"
    assert rows["Дневальный"]["cells"][1] == {
        "executor_unit_name": "Курс A1",
        "people": [],
        "missing": 0,
    }
    assert rows["Дневальный"]["cells"][0]["missing"] == 2


async def test_daily_roster_subtree_and_scope(
    admin: AsyncClient, client_for: ClientFactory, org: Org
) -> None:
    s = await setup(admin, org)
    p = person(org, s, "Борисов")
    await assign(admin, s.cell("Дежурный", 3), p)
    day = MONTH.replace(day=3)

    roster = (
        await admin.get("/rosters/daily", params={"unit_id": str(org.root), "date": str(day)})
    ).json()
    assert roster["unit_name"] == "Академия"
    assert roster["statuses"] == ["draft"]
    [duty] = roster["duties"]
    assert duty["duty_type_name"] == "Наряд"
    assert duty["executor_unit_name"] == "Факультет A"
    roles = {r["role_name"]: r for r in duty["roles"]}
    assert [x["last_name"] for x in roles["Дежурный"]["people"]] == ["Борисов"]
    assert roles["Дневальный"]["missing"] == 2

    # Факультет B наряда факультета A не видит; чужое подразделение — 404
    b = await admin.get("/rosters/daily", params={"unit_id": str(org.fac_b), "date": str(day)})
    assert b.json()["duties"] == []
    op = client_for(org.fac_b, "operator")
    r = await op.get("/rosters/daily", params={"unit_id": str(org.fac_a), "date": str(day)})
    assert r.status_code == 404
    unknown = await admin.get(
        "/rosters/daily", params={"unit_id": str(uuid.uuid4()), "date": str(day)}
    )
    assert unknown.status_code == 422
