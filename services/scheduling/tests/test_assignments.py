"""Ручные назначения: кандидаты, проверки, подтверждение нарушений, гонка, конфликты, лимиты."""

import asyncio
import calendar
import datetime as dt
import uuid
from dataclasses import replace
from typing import Any

import pytest
from conftest import FAKE_PEOPLE, ClientFactory, Org, add_type, role
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dutyflow_common.audit import AuditLog
from dutyflow_common.ids import uuid7
from scheduling.assignments import recompute_conflicts
from scheduling.checks import PersonInfo
from scheduling.models import Assignment

_today = dt.date.today()
MONTH = (_today.replace(day=28) + dt.timedelta(days=5)).replace(day=1)
DAYS = calendar.monthrange(MONTH.year, MONTH.month)[1]


class Setup:
    def __init__(self, t: dict[str, Any], schedule: dict[str, Any], table: dict[str, Any]) -> None:
        self.type = t
        self.schedule = schedule
        self.table = table
        self.roles = {r["name"]: r["id"] for r in t["roles"]}

    def cell(self, role_name: str, day: int) -> str:
        row = next(r for r in self.table["rows"] if r["role_name"] == role_name)
        cell: dict[str, Any] = row["cells"][day - 1]
        return str(cell["id"])


async def setup(admin: AsyncClient, org: Org, unit: uuid.UUID | None = None) -> Setup:
    owner = unit or org.fac_a
    t = await add_type(
        admin,
        owner,
        "Наряд",
        roles=[role("Дежурный"), role("Дневальный", headcount=2, load_weight=0.5)],
    )
    r = await admin.post("/schedules", json={"unit_id": str(owner), "month": str(MONTH)})
    assert r.status_code == 201, r.text
    s = r.json()
    table = (await admin.get(f"/schedules/{s['id']}/table")).json()
    return Setup(t, s, table)


def person(
    org: Org, s: Setup, last: str, *, unit: uuid.UUID | None = None, path: str = "1.2.3", **kw: Any
) -> PersonInfo:
    clearances = kw.pop("clearances", tuple((uuid.UUID(r), None, None) for r in s.roles.values()))
    p = PersonInfo(
        id=uuid7(),
        unit_id=unit or org.course_a1,
        is_active=True,
        last_name=last,
        first_name="Иван",
        middle_name="Петрович",
        rank_name="Рядовой",
        clearances=clearances,
        **kw,
    )
    return FAKE_PEOPLE.add(p, path)


async def assign(client: AsyncClient, cell: str, p: PersonInfo, **extra: Any) -> Any:
    return await client.post(
        f"/day-plans/{cell}/assignments", json={"person_id": str(p.id), **extra}
    )


async def test_candidates_and_assign(admin: AsyncClient, org: Org) -> None:
    s = await setup(admin, org)
    ok = person(org, s, "Алексеев")
    no_clearance = person(org, s, "Бездопусков", clearances=())
    person(org, s, "Чужой", unit=org.fac_b, path="1.4")  # не в поддереве факультета A
    cell = s.cell("Дневальный", 10)

    r = await admin.get(f"/day-plans/{cell}/candidates")
    body = r.json()
    assert body["cell"]["headcount"] == 2
    assert body["cell"]["can_assign"] is True
    # Люди без допуска к роли в кандидаты не попадают (фаза 7d): встать в ячейку они не могут
    names = [(c["name"], c["eligible"]) for c in body["candidates"]]
    assert names == [("Алексеев Иван Петрович", True)]

    r = await assign(admin, cell, ok)
    assert r.status_code == 201, r.text
    assert [a["person_name"] for a in r.json()["assigned"]] == ["Алексеев И. П."]
    r = await assign(admin, cell, no_clearance)
    assert r.status_code == 422
    assert r.json()["code"] == "assignment_blocked"
    assert r.json()["details"]["violations"][0]["message"] == "Нет действующего допуска к роли"
    assert (await assign(admin, cell, ok)).status_code == 409  # уже в ячейке

    table = (await admin.get(f"/schedules/{s.schedule['id']}/table")).json()
    row = next(x for x in table["rows"] if x["role_name"] == "Дневальный")
    assert row["cells"][9]["filled"] == 1
    assert row["cells"][9]["assigned"][0]["person_name"] == "Алексеев И. П."


async def test_headcount(admin: AsyncClient, org: Org) -> None:
    s = await setup(admin, org)
    cell = s.cell("Дежурный", 5)
    assert (await assign(admin, cell, person(org, s, "Первый"))).status_code == 201
    r = await assign(admin, cell, person(org, s, "Второй"))
    assert r.status_code == 422
    assert "укомплектована" in r.json()["message"]


async def test_busy_rest_and_override(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    s = await setup(admin, org)
    p = person(org, s, "Отдыхов")
    assert (await assign(admin, s.cell("Дежурный", 10), p)).status_code == 201
    # Наряд 10-го (18:00 + 24 ч) занимает 10-е и 11-е: 11-го нельзя ни в какую роль
    r = await assign(admin, s.cell("Дневальный", 11), p)
    assert r.json()["code"] == "assignment_blocked"
    assert r.json()["details"]["violations"][0]["kind"] == "busy"
    # 12-го — только 24 ч отдыха из 48: можно, но с подтверждением
    r = await assign(admin, s.cell("Дневальный", 12), p)
    assert r.json()["code"] == "override_required"
    assert r.json()["details"]["violations"][0]["kind"] == "rest"
    r = await assign(admin, s.cell("Дневальный", 12), p, confirm_override=True)
    assert r.status_code == 422  # без комментария
    r = await assign(
        admin, s.cell("Дневальный", 12), p, confirm_override=True, override_comment="Некем заменить"
    )
    assert r.status_code == 201, r.text
    assigned = r.json()["assigned"][0]
    assert (assigned["rest_override"], assigned["override_comment"]) == (True, "Некем заменить")
    async with sessionmaker() as session:
        entry = await session.scalar(
            select(AuditLog).where(AuditLog.action == "assignment.override")
        )
    assert entry is not None
    assert entry.comment == "Некем заменить"

    # Освобождение в занятые сутки — жёсткий запрет
    exempt = person(org, s, "Больной", exemptions=((MONTH.replace(day=21), MONTH.replace(day=25)),))
    r = await assign(admin, s.cell("Дежурный", 20), exempt)
    assert r.json()["details"]["violations"][0]["kind"] == "exemption"


async def test_one_duty_per_day_race(admin: AsyncClient, org: Org) -> None:
    """Два оператора одновременно ставят одного человека в пересекающиеся сутки: проверки
    сервиса проходят оба запроса, но ограничение БД пропускает только один."""
    s = await setup(admin, org)
    p = person(org, s, "Гонкин")
    results = await asyncio.gather(
        assign(admin, s.cell("Дежурный", 15), p), assign(admin, s.cell("Дневальный", 15), p)
    )
    # Второй запрос отсекает либо проверка сервиса (422), либо ограничение БД (409)
    assert sorted(r.status_code for r in results)[0] == 201
    assert sorted(r.status_code for r in results)[1] in (409, 422)


async def test_one_duty_per_day_enforced_by_db(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    """Даже минуя проверки сервиса, БД не даёт поставить человека в пересекающиеся сутки."""
    s = await setup(admin, org)
    p = person(org, s, "Обходчик")
    assert (await assign(admin, s.cell("Дежурный", 15), p)).status_code == 201
    async with sessionmaker() as session:
        first = await session.scalar(select(Assignment).where(Assignment.person_id == p.id))
        assert first is not None
        session.add(
            Assignment(
                id=uuid7(),
                day_plan_id=uuid.UUID(s.cell("Дневальный", 16)),
                person_id=p.id,
                person_name="x",
                start_at=first.start_at + dt.timedelta(days=1),
                end_at=first.end_at + dt.timedelta(days=1),
                occupied_days=Range(MONTH.replace(day=16), MONTH.replace(day=17), bounds="[]"),
                assigned_by="t",
                assigned_by_name="t",
            )
        )
        with pytest.raises(IntegrityError, match="ex_assignment_one_per_day"):
            await session.commit()


async def test_limits(client_for: ClientFactory, admin: AsyncClient, org: Org) -> None:
    s = await setup(admin, org)
    fac_op = client_for(org.fac_a, "operator")
    r = await fac_op.post(
        "/duty-limits", json={"unit_id": str(org.fac_a), "max_duties": 1, "max_holiday_duties": 1}
    )
    assert r.status_code == 201, r.text
    limit = r.json()
    assert limit["unit_name"] == "Факультет A"
    assert (await fac_op.post("/duty-limits", json={"unit_id": str(org.fac_a)})).status_code == 422

    p = person(org, s, "Лимитов")
    assert (await assign(admin, s.cell("Дежурный", 3), p)).status_code == 201
    r = await assign(admin, s.cell("Дежурный", 20), p)
    assert r.json()["code"] == "override_required"
    assert "limit" in [v["kind"] for v in r.json()["details"]["violations"]]
    r = await assign(
        admin, s.cell("Дежурный", 20), p, confirm_override=True, override_comment="Приказ"
    )
    assert r.json()["assigned"][0]["limit_override"] is True

    # Оператор курса видит правило факультета, но не меняет его
    course_op = client_for(org.course_a1, "operator")
    [seen] = (await course_op.get("/duty-limits")).json()
    assert seen["can_edit"] is False
    body = {**{k: limit[k] for k in ("unit_id", "max_duties")}, "version": limit["version"]}
    assert (await course_op.put(f"/duty-limits/{limit['id']}", json=body)).status_code == 403
    r = await fac_op.put(f"/duty-limits/{limit['id']}", json={**body, "max_duties": 5})
    assert r.json()["max_duties"] == 5
    assert (await fac_op.delete(f"/duty-limits/{limit['id']}")).status_code == 204


async def test_delegated_cells_and_dropping_assignments(admin: AsyncClient, org: Org) -> None:
    s = await setup(admin, org)
    cell = s.cell("Дневальный", 7)
    p = person(org, s, "Снимаемый")
    assert (await assign(admin, cell, p)).status_code == 201

    body = {"cell_ids": [cell], "executor_unit_id": str(org.course_a1)}
    r = await admin.post(f"/schedules/{s.schedule['id']}/delegate", json=body)
    assert r.status_code == 409
    assert r.json()["code"] == "assignments_exist"
    r = await admin.post(
        f"/schedules/{s.schedule['id']}/delegate", json={**body, "drop_assignments": True}
    )
    assert r.json() == {"changed": 1}
    # В переданной ячейке назначает исполнитель, а не факультет
    r = await assign(admin, cell, p)
    assert r.status_code == 422
    assert "людей назначает оно" in r.json()["message"]

    # Курс назначает во входящую непринятую ячейку — это принимает её
    course = (
        await admin.get("/schedules", params={"month": str(MONTH), "unit_id": str(org.course_a1)})
    ).json()[0]
    ct = (await admin.get(f"/schedules/{course['id']}/table")).json()
    incoming = next(c for c in ct["rows"][0]["cells"] if c)
    assert incoming["state"] == "incoming_pending"
    assert (await assign(admin, incoming["id"], p)).status_code == 201
    ct = (await admin.get(f"/schedules/{course['id']}/table")).json()
    assert next(c for c in ct["rows"][0]["cells"] if c)["state"] == "incoming_active"
    # Факультет видит заполненность своей переданной ячейки по цепочке
    ft = (await admin.get(f"/schedules/{s.schedule['id']}/table")).json()
    helper = next(x for x in ft["rows"] if x["role_name"] == "Дневальный")
    assert (helper["cells"][6]["state"], helper["cells"][6]["filled"]) == ("delegated_accepted", 1)


async def test_delete_draft_schedule(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    s = await setup(admin, org)
    sid = s.schedule["id"]
    p = person(org, s, "Удаляемый")
    q = person(org, s, "Нижний")
    assert (await assign(admin, s.cell("Дежурный", 3), p)).status_code == 201
    r = await admin.post(
        f"/schedules/{sid}/delegate",
        json={"cell_ids": [s.cell("Дневальный", 5)], "executor_unit_id": str(org.course_a1)},
    )
    assert r.json() == {"changed": 1}
    course = (
        await admin.get("/schedules", params={"month": str(MONTH), "unit_id": str(org.course_a1)})
    ).json()[0]
    ct = (await admin.get(f"/schedules/{course['id']}/table")).json()
    incoming = next(c for c in ct["rows"][0]["cells"] if c)
    assert (await assign(admin, incoming["id"], q)).status_code == 201

    # График с входящими ячейками удаляет только вышестоящее, вернув их себе
    r = await admin.delete(f"/schedules/{course['id']}", params={"version": course["version"]})
    assert r.status_code == 422
    assert "вышестоящего" in r.json()["message"]

    # Назначения — своё и ниже по цепочке — снимаются только с согласия
    r = await admin.delete(f"/schedules/{sid}", params={"version": s.schedule["version"]})
    assert r.status_code == 409
    assert r.json()["details"] == {"assignments": 2}
    stale = await admin.delete(
        f"/schedules/{sid}", params={"version": 99, "drop_assignments": True}
    )
    assert stale.status_code == 409
    r = await admin.delete(
        f"/schedules/{sid}", params={"version": s.schedule["version"], "drop_assignments": True}
    )
    assert r.status_code == 204, r.text
    assert (await admin.get(f"/schedules/{sid}")).status_code == 404
    async with sessionmaker() as session:
        left = await session.scalars(select(Assignment.person_id))
        assert not {p.id, q.id} & set(left)
        entry = await session.scalar(select(AuditLog).where(AuditLog.action == "schedule.delete"))
        assert entry is not None
        assert entry.after is not None
        assert entry.after["dropped_assignments"] == 2
    # Входящая ячейка курса ушла каскадом — теперь пустой график курса удаляется
    r = await admin.delete(f"/schedules/{course['id']}", params={"version": course["version"]})
    assert r.status_code == 204, r.text


async def test_published_schedule_is_not_deleted(admin: AsyncClient, org: Org) -> None:
    s = await setup(admin, org)
    sid = s.schedule["id"]
    r = await admin.post(f"/schedules/{sid}/publish", json={"version": s.schedule["version"]})
    assert r.status_code == 200
    version = r.json()["schedule"]["version"]
    r = await admin.delete(f"/schedules/{sid}", params={"version": version})
    assert r.status_code == 422
    assert "неопубликованный" in r.json()["message"]


async def test_remove_pin_and_viewer(
    client_for: ClientFactory, admin: AsyncClient, org: Org
) -> None:
    s = await setup(admin, org)
    cell = s.cell("Дежурный", 8)
    r = await assign(admin, cell, person(org, s, "Закреплённый"))
    a = r.json()["assigned"][0]
    r = await admin.post(f"/assignments/{a['id']}/pin", json={"pinned": True})
    assert r.json()["assigned"][0]["is_pinned"] is True

    viewer = client_for(org.fac_a, "viewer")
    r = await viewer.get(f"/day-plans/{cell}/candidates")
    assert r.status_code == 200
    assert r.json()["cell"]["can_assign"] is False
    assert (await viewer.delete(f"/assignments/{a['id']}")).status_code == 403

    r = await admin.delete(f"/assignments/{a['id']}")
    assert r.json()["assigned"] == []


async def test_conflicts_marked_not_removed(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    s = await setup(admin, org)
    p = person(org, s, "Уволенный")
    assert (await assign(admin, s.cell("Дежурный", 9), p)).status_code == 201

    FAKE_PEOPLE.add(replace(p, is_active=False), "1.2.3")
    async with sessionmaker() as session, session.begin():
        assert await recompute_conflicts(session, FAKE_PEOPLE, [p.id]) == 1
    table = (await admin.get(f"/schedules/{s.schedule['id']}/table")).json()
    cell = next(x for x in table["rows"] if x["role_name"] == "Дежурный")["cells"][8]
    assert cell["has_conflict"] is True
    assert cell["assigned"][0]["conflict"] == "Исключён из списков личного состава"

    # Восстановили в списках — пометка снимается
    FAKE_PEOPLE.add(p, "1.2.3")
    async with sessionmaker() as session, session.begin():
        await recompute_conflicts(session, FAKE_PEOPLE, [p.id])
    async with sessionmaker() as session:
        a = await session.scalar(select(Assignment).where(Assignment.person_id == p.id))
    assert a is not None
    assert a.conflict is None
