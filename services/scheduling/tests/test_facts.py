"""События фактов нарядов для analytics (фаза 6c): состав события, снятие людей при смене
делегирования, архивирование, выгрузка пачками."""

import datetime as dt
from typing import Any

from conftest import INTERNAL_TOKEN, Org
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from test_assignments import MONTH, assign, person, setup

from dutyflow_common.outbox import OutboxEvent


async def events(
    sessionmaker: async_sessionmaker[AsyncSession], event_type: str
) -> list[dict[str, Any]]:
    async with sessionmaker() as s:
        rows = await s.scalars(
            select(OutboxEvent).where(OutboxEvent.event_type == event_type).order_by(OutboxEvent.id)
        )
        return [e.payload for e in rows]


async def test_fact_event_and_bulk_removal(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    s = await setup(admin, org)
    a = person(org, s, "Алексеев")
    b = person(org, s, "Борисов")
    assert (await assign(admin, s.cell("Дежурный", 5), a)).status_code == 201
    assert (await assign(admin, s.cell("Дневальный", 5), b)).status_code == 201

    [created, orderly] = await events(sessionmaker, "assignment.created")
    day = MONTH.replace(day=5)
    # Названия наряда и роли — для разрезов аналитики
    assert (created["duty_type_name"], created["role_name"]) == ("Наряд", "Дежурный")
    assert created["person_name"] == "Алексеев И. П."
    assert created["schedule_id"] == s.schedule["id"]
    assert created["schedule_status"] == "draft"
    assert created["unit_id"] == str(org.fac_a)
    assert created["date"] == day.isoformat()
    # Наряд 18:00 + 24 ч занимает двое суток, вес по умолчанию 1
    assert (created["occupied_days"], created["load"]) == (2, 2.0)
    assert created["holiday"] is (day.weekday() >= 5)
    assert created["source"] == "manual"
    # Вес — у роли (ADR-0019): дневальный в том же наряде весит 0,5
    assert orderly["load"] == 1.0

    # Смена решения по ячейке со снятием людей — событие о снятом
    r = await admin.post(
        f"/schedules/{s.schedule['id']}/delegate",
        json={
            "cell_ids": [s.cell("Дежурный", 5)],
            "executor_unit_id": str(org.course_a1),
            "drop_assignments": True,
        },
    )
    assert r.status_code == 200, r.text
    removed = await events(sessionmaker, "assignment.removed")
    assert [e["assignment_id"] for e in removed] == [created["assignment_id"]]

    # Архив — тоже событие: аналитика учитывает статус графика (open-questions №57)
    publish = await admin.post(
        f"/schedules/{s.schedule['id']}/publish", json={"version": s.schedule["version"]}
    )
    assert publish.status_code == 200, publish.text
    version = publish.json()["schedule"]["version"]
    await admin.post(f"/schedules/{s.schedule['id']}/archive", json={"version": version})
    [archived] = await events(sessionmaker, "schedule.archived")
    assert archived["schedule_id"] == s.schedule["id"]


async def test_facts_export_in_pages(admin: AsyncClient, org: Org, app: object) -> None:
    s = await setup(admin, org)
    for day, last in ((1, "Первый"), (3, "Второй"), (6, "Третий")):
        await assign(admin, s.cell("Дежурный", day), person(org, s, last))
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
        headers={"X-Internal-Token": INTERNAL_TOKEN},
    ) as internal:
        first = (await internal.get("/internal/assignments/facts", params={"limit": 2})).json()
        rest = (
            await internal.get(
                "/internal/assignments/facts",
                params={"limit": 2, "after": first[-1]["assignment_id"]},
            )
        ).json()
    names = [f["person_name"] for f in first + rest]
    assert sorted(names) == ["Второй И. П.", "Первый И. П.", "Третий И. П."]
    assert len(first) == 2
    assert all(dt.date.fromisoformat(f["date"]).month == MONTH.month for f in first + rest)
