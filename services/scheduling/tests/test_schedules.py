"""Графики и делегирование ролей вниз по дереву (фаза 3a, ADR-0009)."""

import calendar
import datetime as dt
import uuid
from typing import Any

import httpx
from conftest import ClientFactory, Org, add_type, emit, role, unit_payload
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dutyflow_common.audit import AuditLog
from dutyflow_common.calendar import CalendarProjection, handle_calendar_event, resync_calendar
from dutyflow_common.events import Event
from dutyflow_common.ids import uuid7
from dutyflow_common.internal import InternalClient
from scheduling.models import DayPlan, Schedule

# Следующий месяц: синхронизация ячеек с ролями действует с текущего месяца
_today = dt.date.today()
MONTH = (_today.replace(day=28) + dt.timedelta(days=5)).replace(day=1)
DAYS = calendar.monthrange(MONTH.year, MONTH.month)[1]


async def create_schedule(client: AsyncClient, unit: uuid.UUID) -> dict[str, Any]:
    r = await client.post("/schedules", json={"unit_id": str(unit), "month": str(MONTH)})
    assert r.status_code == 201, r.text
    data: dict[str, Any] = r.json()
    return data


async def table(client: AsyncClient, schedule_id: str) -> dict[str, Any]:
    r = await client.get(f"/schedules/{schedule_id}/table")
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()
    return data


def row(t: dict[str, Any], role_name: str) -> dict[str, Any]:
    return next(r for r in t["rows"] if r["role_name"] == role_name)


def states(t: dict[str, Any], role_name: str) -> set[str]:
    return {c["state"] for c in row(t, role_name)["cells"] if c}


def cell_ids(t: dict[str, Any], role_name: str) -> list[str]:
    return [c["id"] for c in row(t, role_name)["cells"] if c]


async def schedule_of(client: AsyncClient, unit: uuid.UUID) -> dict[str, Any] | None:
    r = await client.get("/schedules", params={"month": str(MONTH), "unit_id": str(unit)})
    items: list[dict[str, Any]] = r.json()
    return items[0] if items else None


async def fac_duty(admin: AsyncClient, org: Org) -> None:
    await add_type(
        admin,
        org.fac_a,
        "Наряд по факультету",
        roles=[role("Дежурный"), role("Помощник", headcount=2)],
    )


async def test_create_materializes_own_cells(admin: AsyncClient, org: Org) -> None:
    await fac_duty(admin, org)
    await add_type(admin, org.root, "Наряд академии")  # чужой (вышестоящий) — не попадает
    s = await create_schedule(admin, org.fac_a)
    assert s["month"] == str(MONTH)
    assert (s["status"], s["can_edit"], s["pending_incoming"]) == ("draft", True, 0)
    r = await admin.post("/schedules", json={"unit_id": str(org.fac_a), "month": str(MONTH)})
    assert r.status_code == 409

    t = await table(admin, s["id"])
    assert len(t["days"]) == DAYS
    assert [r["role_name"] for r in t["rows"]] == ["Дежурный", "Помощник"]
    assert all(c is not None for c in row(t, "Помощник")["cells"])
    assert states(t, "Дежурный") == {"own"}
    assert [c["name"] for c in t["children"]] == ["Курс A1"]
    # Сводка заполненности: обе роли закрывает сам факультет, людей ещё нет
    assert (t["schedule"]["to_fill"], t["schedule"]["unfilled"]) == (2 * DAYS, 2 * DAYS)


async def test_delegate_accept_and_take_back(
    admin: AsyncClient,
    org: Org,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # Ниже курса — учебная группа, чтобы проверить цепочку из трёх звеньев
    group = uuid7()
    await emit(
        sessionmaker,
        "unit.created",
        group,
        unit_payload(group, org.course_a1, "1.2.3.5", "Группа 1"),
    )
    await fac_duty(admin, org)
    fac = await create_schedule(admin, org.fac_a)
    t = await table(admin, fac["id"])
    helpers = cell_ids(t, "Помощник")

    r = await admin.post(
        f"/schedules/{fac['id']}/delegate",
        json={"cell_ids": helpers, "executor_unit_id": str(org.course_a1)},
    )
    assert r.json() == {"changed": DAYS}
    t = await table(admin, fac["id"])
    assert states(t, "Помощник") == {"delegated_pending"}
    assert states(t, "Дежурный") == {"own"}
    assert t["units"][str(org.course_a1)]["name"] == "Курс A1"

    # График курса создан автоматически, в нём — только входящая роль
    course = await schedule_of(admin, org.course_a1)
    assert course is not None
    assert course["pending_incoming"] == DAYS
    ct = await table(admin, course["id"])
    assert [r["role_name"] for r in ct["rows"]] == ["Помощник"]
    assert states(ct, "Помощник") == {"incoming_pending"}

    # Курс принимает первую неделю и передаёт остаток группе (это тоже принятие)
    course_cells = cell_ids(ct, "Помощник")
    r = await admin.post(f"/schedules/{course['id']}/accept", json={"cell_ids": course_cells[:7]})
    assert r.json() == {"changed": 7}
    r = await admin.post(
        f"/schedules/{course['id']}/delegate",
        json={"cell_ids": course_cells[7:], "executor_unit_id": str(group)},
    )
    assert r.json() == {"changed": DAYS - 7}
    ct = await table(admin, course["id"])
    assert states(ct, "Помощник") == {"incoming_active", "incoming_delegated_pending"}
    t = await table(admin, fac["id"])
    assert states(t, "Помощник") == {"delegated_accepted"}
    group_schedule = await schedule_of(admin, group)
    assert group_schedule is not None
    assert group_schedule["pending_incoming"] == DAYS - 7

    # Делегировать можно только прямому дочернему
    r = await admin.post(
        f"/schedules/{fac['id']}/delegate",
        json={"cell_ids": helpers[:1], "executor_unit_id": str(group)},
    )
    assert r.status_code == 422
    r = await admin.post(
        f"/schedules/{fac['id']}/delegate",
        json={"cell_ids": helpers[:1], "executor_unit_id": str(org.fac_b)},
    )
    assert r.status_code == 422

    # Факультет забирает роль себе — вся цепочка вниз удаляется
    r = await admin.post(
        f"/schedules/{fac['id']}/delegate",
        json={"cell_ids": helpers, "executor_unit_id": str(org.fac_a)},
    )
    assert r.json() == {"changed": DAYS}
    t = await table(admin, fac["id"])
    assert states(t, "Помощник") == {"own"}
    async with sessionmaker() as session:
        incoming = await session.scalar(
            select(func.count()).select_from(DayPlan).where(DayPlan.origin == "incoming")
        )
        actions = list(
            await session.scalars(select(AuditLog.action).where(AuditLog.entity_type == "schedule"))
        )
    assert incoming == 0
    assert actions.count("day_plan.delegate") == 3
    assert "day_plan.accept" in actions


async def test_scope(client_for: ClientFactory, admin: AsyncClient, org: Org) -> None:
    await fac_duty(admin, org)
    fac = await create_schedule(admin, org.fac_a)
    fac_b = client_for(org.fac_b, "operator")
    assert (await fac_b.get(f"/schedules/{fac['id']}/table")).status_code == 404
    r = await fac_b.post("/schedules", json={"unit_id": str(org.fac_a), "month": str(MONTH)})
    assert r.status_code == 403
    assert await schedule_of(fac_b, org.fac_a) is None

    # Оператор курса видит свой график, но не график факультета
    t = await table(admin, fac["id"])
    await admin.post(
        f"/schedules/{fac['id']}/delegate",
        json={"cell_ids": cell_ids(t, "Помощник")[:3], "executor_unit_id": str(org.course_a1)},
    )
    course_op = client_for(org.course_a1, "operator")
    course = await schedule_of(course_op, org.course_a1)
    assert course is not None
    assert course["can_edit"] is True
    assert (await course_op.get(f"/schedules/{fac['id']}/table")).status_code == 404
    r = await course_op.post(f"/schedules/{course['id']}/accept", json={})
    assert r.json() == {"changed": 3}

    viewer = client_for(org.fac_a, "viewer")
    assert (await viewer.get(f"/schedules/{course['id']}/table")).status_code == 200
    r = await viewer.post(f"/schedules/{course['id']}/accept", json={})
    assert r.status_code == 403


async def test_publish_with_warnings_and_archive(admin: AsyncClient, org: Org) -> None:
    await fac_duty(admin, org)
    fac = await create_schedule(admin, org.fac_a)
    t = await table(admin, fac["id"])
    await admin.post(
        f"/schedules/{fac['id']}/delegate",
        json={"cell_ids": cell_ids(t, "Помощник")[:5], "executor_unit_id": str(org.course_a1)},
    )
    r = await admin.post(f"/schedules/{fac['id']}/publish", json={"version": fac["version"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["schedule"]["status"] == "published"
    assert body["schedule"]["published_by"] == "admin"
    assert body["warnings"] == [{"unit_id": str(org.course_a1), "unit_name": "Курс A1", "count": 5}]

    # Опубликованный график можно менять (замены, open-questions №36)
    r = await admin.post(
        f"/schedules/{fac['id']}/pin",
        json={"cell_ids": cell_ids(t, "Дежурный")[:2], "pinned": True},
    )
    assert r.json() == {"changed": 2}
    again = await admin.post(f"/schedules/{fac['id']}/publish", json={"version": 2})
    assert again.status_code == 422
    stale = await admin.post(f"/schedules/{fac['id']}/archive", json={"version": 1})
    assert stale.status_code == 409
    r = await admin.post(f"/schedules/{fac['id']}/archive", json={"version": 2})
    assert r.json()["status"] == "archived"
    assert r.json()["can_edit"] is False
    r = await admin.post(
        f"/schedules/{fac['id']}/pin",
        json={"cell_ids": cell_ids(t, "Дежурный")[:1], "pinned": False},
    )
    assert r.status_code == 422
    t = await table(admin, fac["id"])
    assert [c["is_pinned"] for c in row(t, "Дежурный")["cells"][:3]] == [True, True, False]


async def test_cells_follow_roles(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await fac_duty(admin, org)
    fac = await create_schedule(admin, org.fac_a)
    [duty_type] = (await admin.get("/duty-types", params={"unit_id": str(org.fac_a)})).json()

    # Новая роль появляется в уже созданном графике
    r = await admin.post(f"/duty-types/{duty_type['id']}/roles", json=role("Дневальный"))
    assert r.status_code == 201
    new_role = next(x for x in r.json()["roles"] if x["name"] == "Дневальный")
    t = await table(admin, fac["id"])
    assert len(cell_ids(t, "Дневальный")) == DAYS

    # Выключенная роль: неделегированные ячейки убираются, делегированные остаются
    await admin.post(
        f"/schedules/{fac['id']}/delegate",
        json={"cell_ids": cell_ids(t, "Дневальный")[:2], "executor_unit_id": str(org.course_a1)},
    )
    r = await admin.put(
        f"/duty-roles/{new_role['id']}",
        json={**role("Дневальный"), "version": new_role["version"], "is_active": False},
    )
    assert r.status_code == 200, r.text
    t = await table(admin, fac["id"])
    assert states(t, "Дневальный") == {"inactive"}
    assert len(cell_ids(t, "Дневальный")) == 2

    # Прошлые графики не трогаются
    async with sessionmaker() as session:
        count = await session.scalar(select(func.count()).select_from(Schedule))
    assert count == 2  # факультет и автоматически созданный график курса


async def test_calendar_in_table(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await fac_duty(admin, org)
    fac = await create_schedule(admin, org.fac_a)
    holiday = MONTH.replace(day=4) if MONTH.replace(day=4).weekday() < 5 else MONTH.replace(day=5)
    async with sessionmaker() as session, session.begin():
        await handle_calendar_event(
            session,
            Event(
                uuid7(),
                "calendar.changed",
                uuid.UUID(int=0),
                {"date": str(holiday), "kind": "holiday", "name": "Праздник"},
            ),
        )
    t = await table(admin, fac["id"])
    kinds = {d["date"]: (d["kind"], d["name"]) for d in t["days"]}
    assert kinds[str(holiday)] == ("holiday", "Праздник")
    saturday = next(
        MONTH + dt.timedelta(days=i)
        for i in range(7)
        if (MONTH + dt.timedelta(days=i)).weekday() == 5
    )
    assert kinds[str(saturday)][0] == "weekend"


async def test_calendar_resync(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/internal/calendar"
        return httpx.Response(200, json=[{"date": "2026-11-04", "kind": "holiday", "name": None}])

    client = InternalClient("http://org", "t", transport=httpx.MockTransport(handler))
    await resync_calendar(sessionmaker, client)
    await client.aclose()
    async with sessionmaker() as session:
        day = await session.get(CalendarProjection, dt.date(2026, 11, 4))
    assert day is not None
    assert day.kind == "holiday"
