"""Пакетный импорт (фаза 6a): предпросмотр, применение, сопоставление по личному номеру,
права по строкам, «всё или ничего», устаревший предпросмотр, допуски и освобождения."""

from typing import Any

from conftest import ClientFactory, Org, add_person
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from test_clearances import CADET, duty_role

from dutyflow_common.audit import AuditLog
from dutyflow_common.outbox import OutboxEvent


def rows(*items: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"row": i + 2, "values": v} for i, v in enumerate(items)]


async def run(
    client: AsyncClient, kind: str, items: list[dict[str, Any]], **extra: Any
) -> dict[str, Any]:
    r = await client.post(f"/imports/{kind}", json={"rows": items, **extra})
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()
    return data


async def test_template_lists_scope_options(
    admin: AsyncClient, client_for: ClientFactory, org: Org
) -> None:
    t = (await admin.get("/imports/people/template")).json()
    unit = next(c for c in t["columns"] if c["key"] == "unit")
    assert "Академия / Факультет A / Курс A1" in unit["options"]
    assert any(c["key"] == "attr:category" for c in t["columns"])
    # Оператор факультета видит подписи от своего подразделения и только своё поддерево
    op = client_for(org.fac_a, "unit_admin")
    t = (await op.get("/imports/people/template")).json()
    unit = next(c for c in t["columns"] if c["key"] == "unit")
    assert sorted(unit["options"]) == ["Факультет A", "Факультет A / Курс A1"]
    assert (await op.get("/imports/other/template")).status_code == 422


async def test_people_preview_apply_and_update(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await add_person(
        admin, org.fac_a, "Старый", personal_no="A-1", attributes={"category": "Курсант"}
    )
    items = rows(
        {
            "personal_no": "A-2",
            "last_name": "Новиков",
            "first_name": "Пётр",
            "unit": "Академия / Факультет A / Курс A1",
            "rank": "Рядовой",
            "attr:category": "Курсант",
        },
        # Известный номер: пустые ячейки не трогают значения, заполненные — заменяют
        {"personal_no": "A-1", "rank": "Майор", "unit": "Академия / Факультет B"},
        {"personal_no": "A-1", "last_name": "Повтор"},
        {"last_name": "Безимени", "unit": "Академия / Нет такого"},
    )
    preview = await run(admin, "people", items)
    actions = [(r["row"], r["action"]) for r in preview["rows"]]
    assert actions == [(2, "create"), (3, "update"), (4, "error"), (5, "error")]
    assert preview["rows"][1]["changes"] == {
        "Звание": [None, "Майор"],
        "Подразделение": ["Академия / Факультет A", "Академия / Факультет B"],
    }
    assert "повторяется" in preview["rows"][2]["errors"][0]["message"]
    assert preview["rows"][3]["errors"][0]["column"] == "unit"

    # С ошибками «всё или ничего»: без skip_invalid применить нельзя
    r = await admin.post("/imports/people", json={"rows": items, "dry_run": False})
    assert r.status_code == 422
    applied = await run(
        admin,
        "people",
        items,
        dry_run=False,
        skip_invalid=True,
        expected_hash=preview["state_hash"],
    )
    assert applied["applied"] is True
    assert applied["summary"] == {"create": 1, "update": 1, "unchanged": 0, "error": 2}

    people = (await admin.get("/people", params={"q": "A-1"})).json()["items"]
    assert people[0]["rank_name"] == "Майор"
    assert people[0]["unit_name"] == "Факультет B"
    async with sessionmaker() as s:
        actions_logged = sorted(
            await s.scalars(select(AuditLog.action).where(AuditLog.comment == "Импорт"))
        )
        events = sorted(
            await s.scalars(
                select(OutboxEvent.event_type).where(OutboxEvent.aggregate_type == "person")
            )
        )
    assert actions_logged == ["person.create", "person.update"]
    assert events.count("person.created") == 2  # одиночное создание + импорт
    assert "person.transferred" in events

    # Повтор того же файла: всё уже как в файле
    again = await run(admin, "people", items[:2])
    assert [r["action"] for r in again["rows"]] == ["unchanged", "unchanged"]


async def test_duplicate_warning_and_stale_preview(admin: AsyncClient, org: Org) -> None:
    await add_person(admin, org.fac_a, "Двойник", "Иван", attributes={"category": "Курсант"})
    items = rows(
        {
            "last_name": "Двойник",
            "first_name": "Иван",
            "unit": "Академия / Факультет A",
            "attr:category": "Курсант",
        }
    )
    preview = await run(admin, "people", items)
    assert preview["rows"][0]["action"] == "create"
    assert "дубликат" in preview["rows"][0]["warnings"][0]["message"]

    # Данные изменились после предпросмотра — применение отклоняется
    await add_person(admin, org.fac_a, "Кто-то", attributes={"category": "Курсант"})
    other = rows({"personal_no": "Z", "last_name": "Z", "first_name": "Z"})
    stale = await admin.post(
        "/imports/people",
        json={"rows": other, "dry_run": False, "expected_hash": preview["state_hash"]},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "import_stale"


async def test_rights_are_checked_per_row(
    client_for: ClientFactory, admin: AsyncClient, org: Org
) -> None:
    await add_person(
        admin, org.fac_b, "Чужой", personal_no="B-1", attributes={"category": "Курсант"}
    )
    op = client_for(org.fac_a, "unit_admin")
    preview = await run(
        op,
        "people",
        rows(
            {"personal_no": "B-1", "rank": "Майор"},
            {
                "last_name": "Свой",
                "first_name": "Иван",
                "unit": "Факультет A",
                "attr:category": "Курсант",
            },
        ),
    )
    assert [r["action"] for r in preview["rows"]] == ["error", "create"]
    assert "зоны" in preview["rows"][0]["errors"][0]["message"]


async def test_clearances_and_exemptions(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await duty_role(sessionmaker, org.root, "Дежурный", type_name="Наряд академии")
    await duty_role(
        sessionmaker, org.fac_a, "Дневальный", type_name="Наряд факультета",
        attribute_requirements=CADET,
    )  # fmt: skip
    cadet = await add_person(
        admin, org.fac_a, "Курсантов", personal_no="C-1", attributes={"category": "Курсант"}
    )
    officer = await add_person(
        admin,
        org.fac_a,
        "Офицеров",
        personal_no="C-2",
        attributes={"category": "Постоянный состав"},
    )
    template = (await admin.get("/imports/clearances/template")).json()
    roles = next(c for c in template["columns"] if c["key"] == "role")["options"]
    assert roles == ["Наряд академии — Дежурный", "Наряд факультета — Дневальный"]

    items = rows(
        {"personal_no": "C-1", "role": "Наряд факультета — Дневальный", "valid_to": "31.12.2026"},
        {"personal_no": "C-2", "role": "Наряд факультета — Дневальный"},
        {
            "personal_no": "C-2",
            "role": "Наряд академии — Дежурный",
        },
        {
            "last_name": "Офицеров",
            "first_name": "Иван",
            "unit": "Академия / Факультет A",
            "role": "Наряд факультета — Дневальный",
            "override_comment": "Приказ № 5",
        },
    )
    preview = await run(admin, "clearances", items)
    assert [r["action"] for r in preview["rows"]] == ["create", "error", "create", "error"]
    assert "требования" in preview["rows"][1]["errors"][0]["message"]
    # Строка 5 — тот же человек (по ФИО) и та же роль, что в строке 3: повтор в файле
    assert "строке 3" in preview["rows"][3]["errors"][0]["message"]

    fixed = [items[0], items[2], items[3]]
    preview = await run(admin, "clearances", fixed)
    assert [r["action"] for r in preview["rows"]] == ["create", "create", "create"]
    assert preview["rows"][2]["warnings"][0]["message"].startswith("Выдаётся вопреки")
    await run(admin, "clearances", fixed, dry_run=False, expected_hash=preview["state_hash"])
    listed = (await admin.get(f"/people/{officer['id']}/clearances")).json()
    assert sorted(c["role_name"] for c in listed) == ["Дежурный", "Дневальный"]

    # Повтор со сменой срока — изменение, без срока — как было
    again = await run(
        admin,
        "clearances",
        rows({"personal_no": "C-1", "role": "Наряд факультета — Дневальный"}),
    )
    assert again["rows"][0]["action"] == "update"
    assert again["rows"][0]["changes"]["Срок действия"] == ["… – 31.12.2026", "… – …"]

    ex = rows(
        {
            "personal_no": "C-1",
            "reason": "Болезнь",
            "date_from": "2026-11-01",
            "date_to": "05.11.2026",
        },
        {
            "personal_no": "C-1",
            "reason": "Отпуск",
            "date_from": "2026-11-05",
            "date_to": "2026-11-09",
        },
        {
            "personal_no": "C-2",
            "reason": "Отпуск",
            "date_from": "2026-11-09",
            "date_to": "2026-11-01",
        },
    )
    preview = await run(admin, "exemptions", ex)
    assert [r["action"] for r in preview["rows"]] == ["create", "error", "error"]
    assert "строки 2" in preview["rows"][1]["errors"][0]["message"]
    await run(admin, "exemptions", ex[:1], dry_run=False)
    card = (await admin.get(f"/people/{cadet['id']}")).json()
    assert [(e["date_from"], e["date_to"]) for e in card["exemptions"]] == [
        ("2026-11-01", "2026-11-05")
    ]
    assert (await run(admin, "exemptions", ex[:1]))["rows"][0]["action"] == "unchanged"


async def test_bulk_import_without_n_plus_one(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    items = rows(
        *(
            {
                "personal_no": f"N-{i}",
                "last_name": f"Фамилия{i}",
                "first_name": "Имя",
                "unit": "Академия / Факультет A / Курс A1",
                "attr:category": "Курсант",
            }
            for i in range(2_000)
        )
    )
    preview = await run(admin, "people", items)
    assert preview["summary"]["create"] == 2_000
    await run(admin, "people", items, dry_run=False, expected_hash=preview["state_hash"])
    async with sessionmaker() as s:
        from personnel.models import Person

        assert await s.scalar(select(func.count()).select_from(Person)) == 2_000
