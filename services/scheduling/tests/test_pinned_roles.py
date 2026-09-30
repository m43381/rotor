"""Роль, закреплённая за подразделением: ячейки сами проходят цепочку до него (ADR-0018)."""

import uuid
from typing import Any

from conftest import FAKE_PEOPLE, Org, add_type, emit, role, unit_payload
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from test_schedules import DAYS, MONTH, cell_ids, create_schedule, row, schedule_of, states, table

from dutyflow_common.audit import AuditLog
from dutyflow_common.ids import uuid7
from scheduling.checks import PersonInfo


async def add_group(sessionmaker: async_sessionmaker[AsyncSession], org: Org) -> uuid.UUID:
    group = uuid7()
    await emit(
        sessionmaker,
        "unit.created",
        group,
        unit_payload(group, org.course_a1, "1.2.3.5", "Группа 1"),
    )
    return group


async def pinned_duty(admin: AsyncClient, org: Org, target: uuid.UUID) -> dict[str, Any]:
    return await add_type(
        admin,
        org.fac_a,
        "Наряд по факультету",
        roles=[role("Дежурный"), role("Дневальный", headcount=2, assigned_unit_id=str(target))],
    )


async def test_cells_follow_chain_to_pinned_unit(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    group = await add_group(sessionmaker, org)
    await pinned_duty(admin, org, group)
    fac = await create_schedule(admin, org.fac_a)

    # Факультет: роль уже передана курсу и закреплена, дежурный — свой
    t = await table(admin, fac["id"])
    orderly = row(t, "Дневальный")
    assert (orderly["assigned_unit_name"], orderly["locked"]) == ("Группа 1", True)
    assert row(t, "Дежурный")["locked"] is False
    assert states(t, "Дежурный") == {"own"}
    assert states(t, "Дневальный") == {"delegated_accepted"}
    assert all(c["is_pinned"] and c["executor_unit_id"] == str(org.course_a1)
               for c in orderly["cells"])  # fmt: skip

    # Курс — промежуточное звено: принял и передал группе, менять решение не может
    course = await schedule_of(admin, org.course_a1)
    assert course is not None
    assert course["pending_incoming"] == 0
    ct = await table(admin, course["id"])
    assert states(ct, "Дневальный") == {"incoming_delegated_pending"}
    assert row(ct, "Дневальный")["locked"] is True

    # Группа — закреплённое подразделение: входящие ждут принятия, решение за ней
    grp = await schedule_of(admin, group)
    assert grp is not None
    assert grp["pending_incoming"] == DAYS
    gt = await table(admin, grp["id"])
    assert states(gt, "Дневальный") == {"incoming_pending"}
    assert row(gt, "Дневальный")["locked"] is False
    r = await admin.post(f"/schedules/{grp['id']}/accept", json={})
    assert r.json() == {"changed": DAYS}

    # Звенья выше закреплённого не могут вернуть себе, передать другому или открепить
    fac_cells = cell_ids(t, "Дневальный")
    for sid, cells, body in (
        (fac["id"], fac_cells, {"executor_unit_id": str(org.fac_a)}),
        (course["id"], cell_ids(ct, "Дневальный"), {"executor_unit_id": str(org.course_a1)}),
    ):
        r = await admin.post(f"/schedules/{sid}/delegate", json={"cell_ids": cells[:1], **body})
        assert r.status_code == 422
        assert "закреплена за подразделением «Группа 1»" in r.json()["message"]
    r = await admin.post(
        f"/schedules/{fac['id']}/pin", json={"cell_ids": fac_cells[:1], "pinned": False}
    )
    assert r.status_code == 422

    async with sessionmaker() as session:
        routed = await session.scalar(select(AuditLog).where(AuditLog.action == "day_plan.route"))
    assert routed is not None
    assert routed.after is not None
    assert routed.after["cells"] == DAYS


async def test_pin_change_reroutes_and_keeps_assigned(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    t_type = await pinned_duty(admin, org, org.course_a1)
    fac = await create_schedule(admin, org.fac_a)
    course = await schedule_of(admin, org.course_a1)
    assert course is not None
    ct = await table(admin, course["id"])
    assert states(ct, "Дневальный") == {"incoming_pending"}
    course_cells = cell_ids(ct, "Дневальный")
    await admin.post(f"/schedules/{course['id']}/accept", json={})

    # В одной ячейке курса уже назначен человек — её цепочку перестраивать нельзя
    orderly_id = next(r["id"] for r in t_type["roles"] if r["name"] == "Дневальный")
    p = FAKE_PEOPLE.add(
        PersonInfo(
            id=uuid7(),
            unit_id=org.course_a1,
            is_active=True,
            last_name="Назначенный",
            first_name="Иван",
            clearances=((uuid.UUID(orderly_id), None, None),),
        ),
        "1.2.3",
    )
    r = await admin.post(f"/day-plans/{course_cells[0]}/assignments", json={"person_id": str(p.id)})
    assert r.status_code == 201, r.text

    group = await add_group(sessionmaker, org)
    body = {"name": "Дневальный", "headcount": 2, "version": 1, "assigned_unit_id": str(group)}
    r = await admin.put(f"/duty-roles/{orderly_id}", json=body)
    assert r.status_code == 200, r.text
    ct = await table(admin, course["id"])
    cells = row(ct, "Дневальный")["cells"]
    assert (cells[0]["state"], cells[0]["filled"]) == ("incoming_active", 1)
    assert {c["state"] for c in cells[1:]} == {"incoming_delegated_pending"}
    grp = await schedule_of(admin, group)
    assert grp is not None
    assert grp["pending_incoming"] == DAYS - 1

    # Закрепление сняли — цепочки остались, но факультет снова решает сам
    body = {"name": "Дневальный", "headcount": 2, "version": 2}
    r = await admin.put(f"/duty-roles/{orderly_id}", json=body)
    assert r.status_code == 200, r.text
    t = await table(admin, fac["id"])
    assert row(t, "Дневальный")["locked"] is False
    assert not any(c["is_pinned"] for c in row(t, "Дневальный")["cells"])
    fac_cells = cell_ids(t, "Дневальный")
    r = await admin.post(
        f"/schedules/{fac['id']}/delegate",
        json={"cell_ids": fac_cells[1:], "executor_unit_id": str(org.fac_a)},
    )
    assert r.status_code == 200, r.text


async def test_new_pinned_role_in_existing_schedule(admin: AsyncClient, org: Org) -> None:
    t_type = await add_type(admin, org.fac_a, "Наряд по факультету", roles=[role("Дежурный")])
    fac = await create_schedule(admin, org.fac_a)
    r = await admin.post(
        f"/duty-types/{t_type['id']}/roles",
        json={"name": "Дневальный", "assigned_unit_id": str(org.course_a1)},
    )
    assert r.status_code == 201, r.text
    t = await table(admin, fac["id"])
    assert states(t, "Дневальный") == {"delegated_pending"}
    course = await schedule_of(admin, org.course_a1)
    assert course is not None
    assert course["pending_incoming"] == DAYS
    assert str(MONTH) == course["month"]
