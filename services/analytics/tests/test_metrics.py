"""Read-model и метрики analytics (фаза 6c): события → факты, сводка, справедливость как в
движке, черновики, scope, нагрузка по людям, перестроение."""

import datetime as dt
import uuid
from typing import Any

import numpy as np
import pytest
from conftest import ClientFactory, Org, emit, fact
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from allocation.engine.metrics import fairness as engine_fairness
from analytics.metrics import fairness
from analytics.models import DutyFact
from analytics.people import handle_category_event, handle_person_event
from analytics.rebuild import rebuild
from dutyflow_common.events import Event
from dutyflow_common.ids import uuid7

NOV = dt.date(2026, 11, 1)
PERIOD = {"date_from": "2026-11-01", "date_to": "2026-11-30"}


async def count(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as s:
        return int(await s.scalar(select(func.count()).select_from(DutyFact)) or 0)


@pytest.mark.parametrize("values", [[], [0.0, 0.0], [1.0, 2.0, 7.0], [3.0] * 5, [0.5, 4.0, 4.0]])
def test_fairness_matches_engine(values: list[float]) -> None:
    assert fairness(values) == engine_fairness(np.array(values))


async def test_events_build_facts(sessionmaker: async_sessionmaker[AsyncSession], org: Org) -> None:
    schedule = uuid.uuid4()
    f = fact(person=uuid.uuid4(), unit=org.course_a1, date=NOV, schedule=schedule, status="draft")
    await emit(sessionmaker, "assignment.created", f)
    await emit(sessionmaker, "assignment.created", f)  # повтор — тот же факт
    assert await count(sessionmaker) == 1
    await emit(
        sessionmaker,
        "schedule.published",
        {"schedule_id": str(schedule), "unit_id": str(org.course_a1)},
    )
    async with sessionmaker() as s:
        assert await s.scalar(select(DutyFact.schedule_status)) == "published"
    # Событие старого формата (без фактических полей) пропускается
    await emit(
        sessionmaker,
        "assignment.created",
        {"assignment_id": str(uuid.uuid4()), "unit_id": str(org.fac_a)},
    )
    assert await count(sessionmaker) == 1
    await emit(sessionmaker, "assignment.removed", f)
    assert await count(sessionmaker) == 0


async def seed(sessionmaker: async_sessionmaker[AsyncSession], org: Org) -> dict[str, uuid.UUID]:
    """Курс A1: Алексеев — 3 наряда (1 в выходной), Борисов — 1; курс A2: Васильев — 2 суточных
    ×1,5; факультет A сам: Григорьев — 1; черновик: Дмитриев; факультет B: Егоров."""
    people = {
        n: uuid.uuid4()
        for n in ("Алексеев", "Борисов", "Васильев", "Григорьев", "Дмитриев", "Егоров")
    }
    s1, s2, s3, draft, sb = (uuid.uuid4() for _ in range(5))

    def f(last: str, unit: uuid.UUID, day: dt.date | int, schedule: uuid.UUID, **kw: Any) -> Any:
        date = NOV.replace(day=day) if isinstance(day, int) else day
        name = f"{last} {last[0]}. {last[0]}."
        return fact(person=people[last], unit=unit, date=date, schedule=schedule, name=name, **kw)

    a1, a2 = org.course_a1, org.course_a2
    items = [
        f("Алексеев", a1, 2, s1),
        f("Алексеев", a1, 7, s1, holiday=True),
        f("Алексеев", a1, 20, s1),
        f("Борисов", a1, 3, s1),
        f("Васильев", a2, 4, s2, days=2, weight=1.5),
        f("Васильев", a2, 14, s2, days=2, weight=1.5),
        f("Григорьев", org.fac_a, 5, s3),
        f("Дмитриев", a1, 6, draft, status="draft"),
        f("Егоров", org.fac_b, 6, sb),
        f("Борисов", a1, dt.date(2026, 10, 31), uuid.uuid4()),  # вне периода
    ]
    for item in items:
        await emit(sessionmaker, "assignment.created", item)
    return people


async def test_overview(
    client_for: ClientFactory, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await seed(sessionmaker, org)
    op = client_for(org.fac_a, "operator")
    r = await op.get("/metrics/overview", params={"unit_id": str(org.fac_a), **PERIOD})
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()
    assert data["totals"] == {"people": 4, "duties": 7, "duty_days": 9, "load": 11.0, "holidays": 1}
    # Нагрузка по людям: Алексеев 3, Борисов 1, Васильев 6, Григорьев 1
    assert data["fairness"]["load"] == engine_fairness(np.array([3.0, 1.0, 6.0, 1.0]))
    assert data["fairness"]["count"]["max"] == 3
    assert [p["person_name"] for p in data["top"][:2]] == ["Васильев В. В.", "Алексеев А. А."]
    assert data["bottom"][0]["load"] == 1.0
    units = {u["unit_name"]: u for u in data["units"]}
    assert units["Факультет A"]["own"] is True
    assert (units["Курс A1"]["people"], units["Курс A1"]["duties"]) == (2, 4)
    assert units["Курс A2"]["load_per_person"] == 6.0
    assert data["histogram"] == [
        {"duties": 1, "people": 2},
        {"duties": 2, "people": 1},
        {"duties": 3, "people": 1},
    ]
    assert data["trend"][0]["month"] == "2026-11"

    # С черновиками — появляется Дмитриев
    drafts = (
        await op.get(
            "/metrics/overview", params={"unit_id": str(org.fac_a), **PERIOD, "drafts": True}
        )
    ).json()
    assert drafts["totals"]["people"] == 5


async def test_scope_and_validation(
    client_for: ClientFactory, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await seed(sessionmaker, org)
    viewer = client_for(org.fac_b, "viewer")
    r = await viewer.get("/metrics/overview", params={"unit_id": str(org.fac_a), **PERIOD})
    assert r.status_code == 404
    own = await viewer.get("/metrics/overview", params={"unit_id": str(org.fac_b), **PERIOD})
    assert own.json()["totals"]["people"] == 1
    bad = await viewer.get(
        "/metrics/overview",
        params={"unit_id": str(org.fac_b), "date_from": "2026-11-30", "date_to": "2026-11-01"},
    )
    assert bad.status_code == 422


async def test_people_page(
    client_for: ClientFactory, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await seed(sessionmaker, org)
    admin = client_for(org.root, "superadmin")
    page = (
        await admin.get("/metrics/people", params={"unit_id": str(org.root), **PERIOD, "limit": 2})
    ).json()
    assert page["total"] == 5
    assert [p["person_name"] for p in page["items"]] == ["Васильев В. В.", "Алексеев А. А."]
    assert page["items"][1]["holidays"] == 1
    low = (
        await admin.get(
            "/metrics/people",
            params={"unit_id": str(org.root), **PERIOD, "limit": 1, "ascending": True},
        )
    ).json()
    assert low["items"][0]["load"] == 1.0


class FakeScheduling:
    def __init__(self, facts: list[dict[str, Any]]) -> None:
        self.facts = sorted(facts, key=lambda f: f["assignment_id"])

    async def get(self, path: str) -> list[dict[str, Any]]:
        query = dict(p.split("=") for p in path.split("?", 1)[1].split("&"))
        after = query.get("after")
        items = [f for f in self.facts if after is None or f["assignment_id"] > after]
        return items[: int(query["limit"])]


async def test_rebuild_replaces_facts(
    sessionmaker: async_sessionmaker[AsyncSession], org: Org, monkeypatch: pytest.MonkeyPatch
) -> None:
    await seed(sessionmaker, org)
    fresh = [
        fact(
            person=uuid.uuid4(), unit=org.course_a1, date=NOV.replace(day=d), schedule=uuid.uuid4()
        )
        for d in range(1, 6)
    ]
    monkeypatch.setattr("analytics.rebuild.PAGE", 2)
    total = await rebuild(sessionmaker, FakeScheduling(fresh))  # type: ignore[arg-type]
    assert total == 5
    assert await count(sessionmaker) == 5


async def test_breakdowns_and_dimensions(
    client_for: ClientFactory, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    """Разрезы фазы 8: измерения, два измерения, распределение, календарь, Лоренц, наряд дня."""
    people = await seed(sessionmaker, org)
    cadet, officer = uuid.uuid4(), uuid.uuid4()
    async with sessionmaker() as session, session.begin():
        await handle_category_event(
            session, Event(uuid7(), "person_category.changed", cadet, {"name": "Курсант"})
        )
        await handle_category_event(
            session,
            Event(
                uuid7(),
                "person_category.changed",
                officer,
                {"name": "Постоянный состав", "sort_order": 1},
            ),
        )
        for last, cat in (("Алексеев", cadet), ("Борисов", cadet), ("Григорьев", officer)):
            payload = {
                "person_id": str(people[last]),
                "unit_id": str(org.fac_a),
                "category_id": str(cat),
                "is_active": True,
                "version": 2,
            }
            await handle_person_event(
                session, Event(uuid7(), "person.updated", people[last], payload)
            )
        # Устаревшее событие (версия 1) категорию не возвращает
        stale = {"person_id": str(people["Алексеев"]), "unit_id": str(org.fac_a), "version": 1}
        await handle_person_event(
            session, Event(uuid7(), "person.created", people["Алексеев"], stale)
        )

    op = client_for(org.fac_a, "operator")
    base = {"unit_id": str(org.fac_a), **PERIOD}

    async def get(path: str, **params: Any) -> Any:
        r = await op.get(path, params={**base, **params})
        assert r.status_code == 200, r.text
        return r.json()

    units = await get("/metrics/breakdown", dimension="unit")
    assert [(i["label"], i["duties"]) for i in units["items"]] == [
        ("Факультет A (само)", 1),
        ("Курс A1", 4),
        ("Курс A2", 2),
    ]
    cats = {i["label"]: i for i in (await get("/metrics/breakdown", dimension="category"))["items"]}
    assert (cats["Курсант"]["people"], cats["Курсант"]["load"]) == (2, 4.0)
    assert cats["Постоянный состав"]["duties"] == 1
    assert cats["Не указана"]["people"] == 1  # Васильев — нет в проекции людей

    week = await get("/metrics/breakdown", dimension="weekday")
    assert sum(i["duties"] for i in week["items"]) == 7
    assert [i["label"] for i in week["items"]] == sorted(
        (i["label"] for i in week["items"]), key=["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].index
    )
    kinds = {
        i["label"]: i["duties"]
        for i in (await get("/metrics/breakdown", dimension="day_kind"))["items"]
    }
    assert kinds == {"Будни": 6, "Выходные и праздники": 1}

    # Два измерения: подразделение × роль
    pivot = await get("/metrics/breakdown", dimension="unit", split="role")
    assert {i["split_label"] for i in pivot["items"]} == {"Наряд — Дежурный"}
    assert pivot["split"] == "role"

    dist = await get("/metrics/distribution", dimension="unit")
    a1 = next(i for i in dist["items"] if i["label"] == "Курс A1")
    assert (a1["people"], a1["min"], a1["max"], a1["median"]) == (2, 1.0, 3.0, 2.0)

    cal = await get("/metrics/calendar")
    assert [d["date"] for d in cal][:2] == ["2026-11-02", "2026-11-03"]
    assert sum(d["duties"] for d in cal) == 7

    overview = await get("/metrics/overview")
    assert overview["lorenz"][0] == [0.0, 0.0]
    assert overview["lorenz"][-1] == [1.0, 1.0]

    # Наряд дня: Васильев заступил 4-го на двое суток — в наряде и 5-го
    roster = (
        await op.get("/metrics/roster", params={"unit_id": str(org.fac_a), "day": "2026-11-05"})
    ).json()
    assert {r["person_name"] for r in roster} == {"Васильев В. В.", "Григорьев Г. Г."}
    assert roster[0]["duty_type_name"] == "Наряд"

    bad = await op.get("/metrics/breakdown", params={**base, "dimension": "nope"})
    assert bad.status_code == 422
