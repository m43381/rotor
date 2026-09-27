"""Снимок задачи распределения (ADR-0013): состав, индексы, лимиты, воспроизводимый hash."""

import datetime as dt
import json
import uuid
from typing import Any

from conftest import FAKE_PEOPLE, ClientFactory, Org, add_type, role
from httpx import AsyncClient

from dutyflow_common.ids import uuid7
from scheduling.checks import PersonInfo

_today = dt.date.today()
MONTH = (_today.replace(day=28) + dt.timedelta(days=5)).replace(day=1)


async def snapshot(client: AsyncClient, schedule_id: str) -> dict[str, Any]:
    r = await client.get(f"/schedules/{schedule_id}/snapshot")
    assert r.status_code == 200, r.text
    assert "attachment" in r.headers["content-disposition"]
    data: dict[str, Any] = json.loads(r.content)
    return data


async def test_snapshot(client_for: ClientFactory, admin: AsyncClient, org: Org) -> None:
    t = await add_type(
        admin, org.fac_a, "Наряд", roles=[role("Дежурный"), role("Дневальный", headcount=2)]
    )
    duty = uuid.UUID(t["roles"][0]["id"])
    other_role = uuid7()  # допуск к роли вне снимка в него не попадает
    s = (
        await admin.post("/schedules", json={"unit_id": str(org.fac_a), "month": str(MONTH)})
    ).json()
    table = (await admin.get(f"/schedules/{s['id']}/table")).json()
    orderly_cells = [c["id"] for c in table["rows"][1]["cells"] if c]
    await admin.post(
        f"/schedules/{s['id']}/delegate",
        json={"cell_ids": orderly_cells[:3], "executor_unit_id": str(org.course_a1)},
    )
    await admin.post(
        "/duty-limits", json={"unit_id": str(org.fac_a), "max_duties": 4, "max_holiday_duties": 1}
    )
    p = FAKE_PEOPLE.add(
        PersonInfo(
            id=uuid7(),
            unit_id=org.course_a1,
            is_active=True,
            last_name="Снимков",
            first_name="Иван",
            clearances=((duty, MONTH.replace(day=5), None), (other_role, None, None)),
            exemptions=((MONTH - dt.timedelta(days=200), MONTH.replace(day=2)),),
        ),
        "1.2.3",
    )
    duty_cell = table["rows"][0]["cells"][9]["id"]
    r = await admin.post(f"/day-plans/{duty_cell}/assignments", json={"person_id": str(p.id)})
    assert r.status_code == 201, r.text

    snap = await snapshot(admin, s["id"])
    assert snap["snapshot_version"] == 1
    assert snap["timezone"] == "Europe/Moscow"
    assert [u["name"] for u in snap["units"]] == ["Факультет A", "Курс A1"]
    assert snap["units"][1]["parent"] == 0
    start = snap["horizon"]["month_start"]
    assert start == 90
    assert snap["days"][start][0] == str(MONTH)
    assert {r["name"] for r in snap["roles"]} == {"Дежурный", "Дневальный"}
    role_idx = {r["name"]: i for i, r in enumerate(snap["roles"])}

    [person] = snap["people"]
    assert person["u"] == 1
    # Только допуск к роли снимка; начало — номер дня горизонта; освобождение обрезано
    assert person["c"] == [[role_idx["Дежурный"], start + 4, None]]
    assert person["x"] == [[0, start + 1]]
    assert person["limit"] == [4, 1]

    # Ячейки: свои ячейки факультета и входящие ячейки курса со ссылкой на родителя
    incoming = [c for c in snap["cells"] if c["origin"] == "incoming"]
    assert len(incoming) == 3
    assert all(c["s"] == 1 and c["status"] == "pending" for c in incoming)
    parent = snap["cells"][incoming[0]["parent"]]
    assert (parent["s"], parent["e"]) == (0, 1)

    [a] = snap["assignments"]
    assert (a["p"], a["d"], a["r"]) == (0, start + 9, role_idx["Дежурный"])
    assert snap["cells"][a["cell"]]["d"] == start + 9
    assert a["days"] == [start + 9, start + 10]  # 18:00 + 24 ч — двое суток
    assert a["load"] == 2.0
    assert a["auto"] is False
    assert a["rest"] == 48
    # 18:00 местного времени дня start+9 от полуночи первого дня горизонта
    assert a["t"] == [(start + 9) * 1440 + 18 * 60, (start + 10) * 1440 + 18 * 60]

    # Тот же вход — тот же hash; изменилось назначение — другой
    again = await snapshot(admin, s["id"])
    assert again["hash"] == snap["hash"]
    assignment_id = r.json()["assigned"][0]["id"]
    await admin.post(f"/assignments/{assignment_id}/pin", json={"pinned": True})
    assert (await snapshot(admin, s["id"]))["hash"] != snap["hash"]

    fac_b = client_for(org.fac_b, "operator")
    assert (await fac_b.get(f"/schedules/{s['id']}/snapshot")).status_code == 404
