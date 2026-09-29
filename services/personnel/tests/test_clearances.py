"""Допуски к ролям нарядов: требования, выдача с подтверждением, scope, отчёт, массовая выдача."""

import uuid
from typing import Any

import httpx
from conftest import ClientFactory, Org, add_person
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dutyflow_common.audit import AuditLog
from dutyflow_common.events import Event
from dutyflow_common.ids import uuid7
from dutyflow_common.internal import InternalClient
from dutyflow_common.outbox import OutboxEvent
from personnel.duty_roles import handle_duty_event, resync_scheduling
from personnel.models import DutyRoleProjection

CADET = [{"code": "category", "op": "eq", "value": "Курсант"}]


async def duty_role(
    sessionmaker: async_sessionmaker[AsyncSession],
    owner: uuid.UUID,
    name: str = "Дежурный",
    *,
    type_name: str = "Наряд",
    type_id: uuid.UUID | None = None,
    role_id: uuid.UUID | None = None,
    version: int = 1,
    type_active: bool = True,
    **requirements: Any,
) -> uuid.UUID:
    """Роль попадает в локальную копию так же, как в работе — событиями scheduling."""
    type_id = type_id or uuid.uuid5(uuid.NAMESPACE_OID, f"{owner}:{type_name}")
    role_id = role_id or uuid7()
    async with sessionmaker() as session, session.begin():
        await handle_duty_event(
            session,
            Event(
                uuid7(),
                "duty_type.changed",
                type_id,
                {
                    "id": str(type_id),
                    "name": type_name,
                    "short_name": None,
                    "owner_unit_id": str(owner),
                    "is_active": type_active,
                    "version": version,
                },
            ),
        )
        await handle_duty_event(
            session,
            Event(
                uuid7(),
                "duty_role.changed",
                role_id,
                {
                    "id": str(role_id),
                    "duty_type_id": str(type_id),
                    "code": "r",
                    "name": name,
                    "sort_order": 0,
                    "min_rank_order": requirements.get("min_rank_order"),
                    "allowed_position_ids": requirements.get("allowed_position_ids"),
                    "attribute_requirements": requirements.get("attribute_requirements", []),
                    "is_active": True,
                    "version": version,
                },
            ),
        )
    return role_id


async def grant(
    client: AsyncClient, person: dict[str, Any], role_id: uuid.UUID, **extra: Any
) -> httpx.Response:
    return await client.post(
        f"/people/{person['id']}/clearances", json={"duty_role_id": str(role_id), **extra}
    )


async def test_grant_without_requirements(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    role = await duty_role(sessionmaker, org.fac_a, "Дневальный")
    person = await add_person(admin, org.course_a1, "Иванов")
    r = await grant(admin, person, role, valid_to="2099-12-31")
    assert r.status_code == 201, r.text
    [c] = r.json()
    assert (c["role_name"], c["duty_type_name"], c["owner_unit_name"]) == (
        "Дневальный",
        "Наряд",
        "Факультет A",
    )
    assert c["status"] == "active"
    assert c["violations"] == []
    assert c["overrides_requirements"] is False
    assert c["granted_by_name"] == "admin"

    again = await grant(admin, person, role)
    assert again.status_code == 409

    async with sessionmaker() as session:
        action = await session.scalar(
            select(AuditLog.action).where(AuditLog.entity_type == "clearance")
        )
        events = list(
            await session.scalars(
                select(OutboxEvent.event_type).where(OutboxEvent.aggregate_type == "clearance")
            )
        )
    assert action == "clearance.grant"
    assert "clearance.granted" in events


async def test_requirements_warning_and_override(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    role = await duty_role(
        sessionmaker,
        org.fac_a,
        "Дежурный по факультету",
        min_rank_order=100,
        attribute_requirements=[{"code": "category", "op": "eq", "value": "Постоянный состав"}],
    )
    cadet = await add_person(
        admin,
        org.course_a1,
        "Петров",
        rank_id=str(org.rank_private),
        attributes={"category": "Курсант"},
    )
    r = await grant(admin, cadet, role)
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "requirements_not_met"
    messages = [v["message"] for v in body["details"]["violations"]]
    assert messages == [
        "Звание ниже требуемого: нужно не ниже «Майор», у человека — «Рядовой»",
        "«Категория»: требуется «Постоянный состав», у человека — «Курсант»",
    ]

    # Подтверждение без комментария не принимается
    r = await grant(admin, cadet, role, confirm_override=True, override_comment="  ")
    assert r.status_code == 422
    r = await grant(
        admin, cadet, role, confirm_override=True, override_comment="Приказ начальника факультета"
    )
    assert r.status_code == 201, r.text
    [c] = r.json()
    assert c["overrides_requirements"] is True
    assert c["override_comment"] == "Приказ начальника факультета"
    # Допуск действует, но в карточке видно, что требования не выполнены
    assert c["status"] == "active"
    assert len(c["violations"]) == 2

    async with sessionmaker() as session:
        entry = await session.scalar(select(AuditLog).where(AuditLog.entity_type == "clearance"))
    assert entry is not None
    assert entry.action == "clearance.grant_override"
    assert entry.comment == "Приказ начальника факультета"


async def test_override_flag_only_when_needed(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    role = await duty_role(sessionmaker, org.fac_a, attribute_requirements=CADET)
    person = await add_person(admin, org.course_a1, "Сидоров", attributes={"category": "Курсант"})
    r = await grant(admin, person, role, confirm_override=True, override_comment="на всякий случай")
    [c] = r.json()
    assert c["overrides_requirements"] is False
    assert c["override_comment"] is None


async def test_role_must_cover_person_unit(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    academy_role = await duty_role(sessionmaker, org.root, type_name="Дежурный по академии")
    fac_b_role = await duty_role(sessionmaker, org.fac_b, type_name="Наряд факультета B")
    course_role = await duty_role(sessionmaker, org.course_a1, type_name="Наряд по курсу")
    person = await add_person(admin, org.fac_a, "Кузнецов")
    assert (await grant(admin, person, academy_role)).status_code == 201
    r = await grant(admin, person, fac_b_role)
    assert r.status_code == 422
    assert "не распространяется" in r.json()["message"]
    # Наряд нижестоящего подразделения человеку управления факультета не выдаётся
    assert (await grant(admin, person, course_role)).status_code == 422
    assert (await grant(admin, person, uuid7())).status_code == 422

    options = (await admin.get(f"/people/{person['id']}/clearance-options")).json()
    assert [(o["duty_type_name"], o["granted"]) for o in options] == [
        ("Дежурный по академии", True)
    ]


async def test_scope_and_viewer(
    admin: AsyncClient,
    client_for: ClientFactory,
    org: Org,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    role = await duty_role(sessionmaker, org.root)
    person = await add_person(admin, org.course_a1, "Смирнов")
    fac_b = client_for(org.fac_b, "operator")
    assert (await grant(fac_b, person, role)).status_code == 403
    assert (await fac_b.get(f"/people/{person['id']}/clearances")).status_code == 403
    viewer = client_for(org.fac_a, "viewer")
    assert (await grant(viewer, person, role)).status_code == 403
    assert (await viewer.get(f"/people/{person['id']}/clearances")).status_code == 200
    course_op = client_for(org.course_a1, "operator")
    assert (await grant(course_op, person, role)).status_code == 201


async def test_update_revoke_and_regrant(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    role = await duty_role(sessionmaker, org.fac_a)
    person = await add_person(admin, org.fac_a, "Волков")
    [c] = (await grant(admin, person, role, valid_from="2099-01-01")).json()
    assert c["status"] == "future"

    r = await admin.patch(
        f"/clearances/{c['id']}",
        json={"version": c["version"], "valid_from": "2020-01-01", "valid_to": "2020-12-31"},
    )
    assert r.status_code == 200, r.text
    [c2] = r.json()
    assert c2["status"] == "expired"
    stale = await admin.patch(f"/clearances/{c['id']}", json={"version": c["version"]})
    assert stale.status_code == 409
    bad = await admin.patch(
        f"/clearances/{c['id']}",
        json={"version": c2["version"], "valid_from": "2021-01-02", "valid_to": "2021-01-01"},
    )
    assert bad.status_code == 422

    r = await admin.post(f"/clearances/{c['id']}/revoke", json={"comment": "Перевод"})
    assert r.status_code == 200
    assert r.json() == []
    history = (
        await admin.get(f"/people/{person['id']}/clearances", params={"include_revoked": True})
    ).json()
    assert [h["status"] for h in history] == ["revoked"]
    assert (await admin.post(f"/clearances/{c['id']}/revoke", json={})).status_code == 422
    # После отзыва допуск можно выдать заново
    assert (await grant(admin, person, role)).status_code == 201


async def test_mismatch_report(
    admin: AsyncClient,
    client_for: ClientFactory,
    org: Org,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    role_id = uuid7()
    type_id = uuid7()
    await duty_role(
        sessionmaker,
        org.fac_a,
        "Дневальный",
        type_id=type_id,
        role_id=role_id,
        attribute_requirements=CADET,
    )
    ok = await add_person(admin, org.course_a1, "Алексеев", attributes={"category": "Курсант"})
    other = await add_person(admin, org.course_a1, "Борисов", attributes={"category": "Слушатель"})
    assert (await grant(admin, ok, role_id)).status_code == 201
    r = await grant(admin, other, role_id, confirm_override=True, override_comment="Нехватка людей")
    assert r.status_code == 201

    report = (await admin.get("/reports/clearance-mismatches")).json()
    assert report["total"] == 1
    item = report["items"][0]
    assert item["person_name"] == "Борисов Иван"
    assert item["overrides_requirements"] is True
    assert item["unit_name"] == "Курс A1"
    assert item["violations"][0]["message"].startswith("«Категория»")

    # Характеристика изменилась — ранее обычный допуск тоже попадает в отчёт
    r = await admin.patch(
        f"/people/{ok['id']}",
        json={"version": ok["version"], "attributes": {"category": "Постоянный состав"}},
    )
    assert r.status_code == 200, r.text
    report = (await admin.get("/reports/clearance-mismatches")).json()
    assert {i["person_name"] for i in report["items"]} == {"Алексеев Иван", "Борисов Иван"}

    # Требования роли сняли (новая версия роли) — несоответствий нет
    await duty_role(
        sessionmaker, org.fac_a, "Дневальный", type_id=type_id, role_id=role_id, version=2
    )
    assert (await admin.get("/reports/clearance-mismatches")).json()["total"] == 0
    # Устаревшее событие (версия 1) не возвращает требования
    await duty_role(
        sessionmaker,
        org.fac_a,
        "Дневальный",
        type_id=type_id,
        role_id=role_id,
        version=1,
        attribute_requirements=CADET,
    )
    assert (await admin.get("/reports/clearance-mismatches")).json()["total"] == 0

    # Scope: оператор соседнего факультета отчёт по чужим людям не видит
    fac_b = client_for(org.fac_b, "operator")
    assert (await fac_b.get("/reports/clearance-mismatches")).json()["total"] == 0


async def test_bulk_grant(
    admin: AsyncClient,
    client_for: ClientFactory,
    org: Org,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    duty = await duty_role(sessionmaker, org.fac_a, "Дежурный", attribute_requirements=CADET)
    orderly = await duty_role(sessionmaker, org.fac_a, "Дневальный")
    cadet = await add_person(admin, org.course_a1, "Григорьев", attributes={"category": "Курсант"})
    officer = await add_person(
        admin, org.course_a1, "Дмитриев", attributes={"category": "Постоянный состав"}
    )
    foreign = await add_person(admin, org.fac_b, "Егоров")
    body = {
        "person_ids": [cadet["id"], officer["id"], foreign["id"]],
        "duty_role_ids": [str(duty), str(orderly)],
    }
    course_op = client_for(org.course_a1, "operator")
    r = await course_op.post("/clearances/bulk", json=body)
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["done"] == 3  # курсант — обе роли, офицер — только дневальный
    assert result["needs_override"] == 1
    reasons = sorted(s["reason"] for s in result["skipped"])
    assert reasons == [
        "Не проходит требования роли",
        "Человек не найден или вне зоны ответственности",
    ]

    r = await course_op.post(
        "/clearances/bulk",
        json={**body, "confirm_override": True, "override_comment": "Решение командира"},
    )
    result = r.json()
    assert result["done"] == 1
    assert result["needs_override"] == 0
    assert sum(s["reason"] == "Допуск уже выдан" for s in result["skipped"]) == 3

    roles = (await course_op.get("/clearance-roles")).json()
    assert {r["role_name"] for r in roles} == {"Дежурный", "Дневальный"}


async def test_inactive_role_not_grantable(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    role = await duty_role(sessionmaker, org.fac_a, type_active=False)
    person = await add_person(admin, org.fac_a, "Жуков")
    assert (await grant(admin, person, role)).status_code == 422
    assert (await admin.get(f"/people/{person['id']}/clearance-options")).json() == []


async def test_snapshot_includes_clearances(
    admin: AsyncClient,
    internal: AsyncClient,
    org: Org,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    role = await duty_role(sessionmaker, org.fac_a)
    old_role = await duty_role(sessionmaker, org.fac_a, "Старая роль")
    person = await add_person(admin, org.course_a1, "Зайцев")
    await grant(admin, person, role, valid_from="2026-10-15")
    await grant(admin, person, old_role, valid_to="2026-09-30")
    r = await internal.post(
        "/internal/people/batch",
        json={"unit_ids": [str(org.fac_a)], "date_from": "2026-10-01", "date_to": "2026-10-31"},
    )
    [p] = r.json()
    assert p["clearances"] == [[str(role), "2026-10-15", None]]

    # Фильтр кандидатов: только люди с действующим в периоде допуском к роли
    await add_person(admin, org.course_a1, "Бездопусков")
    period = {"unit_ids": [str(org.fac_a)], "date_from": "2026-10-01", "date_to": "2026-10-31"}
    everyone = (await internal.post("/internal/people/batch", json=period)).json()
    assert len(everyone) == 2
    by_role = await internal.post(
        "/internal/people/batch", json={**period, "duty_role_ids": [str(role)]}
    )
    assert [x["id"] for x in by_role.json()] == [p["id"]]
    expired = await internal.post(
        "/internal/people/batch", json={**period, "duty_role_ids": [str(old_role)]}
    )
    assert expired.json() == []

    refs = (await internal.post("/internal/references", json={})).json()
    assert [a["code"] for a in refs["attributes"]] == ["category"]


async def test_resync_from_scheduling(
    sessionmaker: async_sessionmaker[AsyncSession], org: Org
) -> None:
    role_id, type_id = uuid7(), uuid7()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/internal/duty-roles/batch"
        return httpx.Response(
            200,
            json=[
                {
                    "id": str(role_id),
                    "duty_type_id": str(type_id),
                    "code": "role1",
                    "name": "Из scheduling",
                    "headcount": 2,
                    "sort_order": 0,
                    "min_rank_order": None,
                    "allowed_position_ids": None,
                    "attribute_requirements": [],
                    "is_active": True,
                    "version": 3,
                    "duty_type": {
                        "id": str(type_id),
                        "name": "Наряд",
                        "short_name": None,
                        "owner_unit_id": str(org.root),
                        "is_active": True,
                        "version": 1,
                    },
                }
            ],
        )

    client = InternalClient("http://scheduling", "t", transport=httpx.MockTransport(handler))
    assert await resync_scheduling(sessionmaker, client, only_if_empty=True) is True
    assert await resync_scheduling(sessionmaker, client, only_if_empty=True) is False
    await client.aclose()
    async with sessionmaker() as session:
        role = await session.get(DutyRoleProjection, role_id)
    assert role is not None
    assert (role.name, role.source_version) == ("Из scheduling", 3)
