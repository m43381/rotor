"""Типы нарядов и роли: видимость по дереву, права, проверка требований, аудит, события."""

from typing import Any

from conftest import (
    CADET,
    CATEGORY_OLD,
    POSITION_OFFICER,
    POSITION_OLD,
    ClientFactory,
    Org,
    add_type,
    role,
)
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dutyflow_common.audit import AuditLog
from dutyflow_common.outbox import OutboxEvent


async def test_create_with_roles(admin: AsyncClient, org: Org) -> None:
    t = await add_type(
        admin,
        org.fac_a,
        "Наряд по факультету",
        roles=[
            role(
                "Дежурный по факультету",
                min_rank_order=100,
                allowed_position_ids=[str(POSITION_OFFICER)],
            ),
            role(
                "Дневальный",
                headcount=2,
                attribute_requirements=[{"code": "course_no", "op": "gte", "value": 2}],
                assigned_unit_id=str(org.course_a1),
                allowed_category_ids=[str(CADET)],
            ),
        ],
        rest_hours=72,
    )
    assert t["owner_unit_name"] == "Факультет A"
    assert t["start_time"] == "18:00:00"
    assert t["rest_hours"] == 72
    assert t["can_edit"] is True
    roles: list[dict[str, Any]] = t["roles"]  # type: ignore[assignment]
    assert [(r["name"], r["code"], r["headcount"]) for r in roles] == [
        ("Дежурный по факультету", "role1", 1),
        ("Дневальный", "role2", 2),
    ]
    assert roles[0]["min_rank_order"] == 100
    assert roles[1]["attribute_requirements"] == [{"code": "course_no", "op": "gte", "value": 2}]
    assert (roles[0]["assigned_unit_id"], roles[0]["allowed_category_ids"]) == (None, None)
    assert roles[1]["assigned_unit_name"] == "Курс A1"
    assert roles[1]["allowed_category_ids"] == [str(CADET)]


async def test_visibility_along_tree(
    client_for: ClientFactory, admin: AsyncClient, org: Org
) -> None:
    academy = await add_type(admin, org.root, "Дежурный по академии")
    fac_a = await add_type(admin, org.fac_a, "Наряд по факультету A")
    course = await add_type(admin, org.course_a1, "Наряд по курсу")
    fac_b = await add_type(admin, org.fac_b, "Наряд по факультету B")

    # Оператор курса видит свой наряд и наряды вышестоящих, но не соседнего факультета
    course_op = client_for(org.course_a1, "operator")
    names = {t["name"]: t["can_edit"] for t in (await course_op.get("/duty-types")).json()}
    assert names == {
        "Дежурный по академии": False,
        "Наряд по факультету A": False,
        "Наряд по курсу": True,
    }
    # Оператор факультета видит и поддерево (наряд курса), и может его менять
    fac_op = client_for(org.fac_a, "operator")
    names = {t["name"]: t["can_edit"] for t in (await fac_op.get("/duty-types")).json()}
    assert names == {
        "Дежурный по академии": False,
        "Наряд по факультету A": True,
        "Наряд по курсу": True,
    }
    # Фильтр «касается подразделения»: наряды самого подразделения и вышестоящих
    r = await fac_op.get("/duty-types", params={"unit_id": str(org.fac_a)})
    assert {t["name"] for t in r.json()} == {"Дежурный по академии", "Наряд по факультету A"}

    # Вышестоящий наряд можно смотреть, но не менять; чужой — не найден
    assert (await course_op.get(f"/duty-types/{academy['id']}")).status_code == 200
    body = {**_update_body(academy), "name": "Взлом"}
    assert (await course_op.put(f"/duty-types/{academy['id']}", json=body)).status_code == 403
    assert (await course_op.get(f"/duty-types/{fac_b['id']}")).status_code == 404
    body = {**_update_body(fac_b), "name": "Взлом"}
    assert (await course_op.put(f"/duty-types/{fac_b['id']}", json=body)).status_code == 404
    assert course["can_edit"] is True
    assert fac_a["can_edit"] is True


async def test_operator_creates_only_in_scope(client_for: ClientFactory, org: Org) -> None:
    course_op = client_for(org.course_a1, "operator")
    r = await course_op.post(
        "/duty-types",
        json={
            "name": "Чужой",
            "owner_unit_id": str(org.fac_a),
            "start_time": "08:00",
            "duration_minutes": 60,
            "roles": [role()],
        },
    )
    assert r.status_code == 403
    viewer = client_for(org.fac_a, "viewer")
    assert (await viewer.get("/duty-types")).status_code == 200
    r = await viewer.post(
        "/duty-types",
        json={
            "name": "Нельзя",
            "owner_unit_id": str(org.fac_a),
            "start_time": "08:00",
            "duration_minutes": 60,
            "roles": [role()],
        },
    )
    assert r.status_code == 403


async def test_validation(admin: AsyncClient, org: Org) -> None:
    async def bad(**overrides: Any) -> str:
        body = {
            "name": "Проверка",
            "owner_unit_id": str(org.fac_a),
            "start_time": "18:00",
            "duration_minutes": 24 * 60,
            "roles": [role()],
            **overrides,
        }
        r = await admin.post("/duty-types", json=body)
        assert r.status_code == 422, r.text
        message: str = r.json()["message"]
        return message

    assert "закрепить" in await bad(roles=[role(assigned_unit_id=str(org.fac_b))])
    assert "Категория" in await bad(roles=[role(allowed_category_ids=[str(CATEGORY_OLD)])])
    await bad(roles=[role(allowed_category_ids=[])])
    await bad(duration_minutes=30)
    await bad(duration_minutes=8 * 24 * 60)
    await bad(roles=[])
    assert "Звание" in await bad(roles=[role(min_rank_order=55)])
    assert "Должность" in await bad(roles=[role(allowed_position_ids=[str(POSITION_OLD)])])
    await bad(roles=[role(allowed_position_ids=[])])
    assert "не найдена" in await bad(
        roles=[role(attribute_requirements=[{"code": "nope", "op": "eq", "value": 1}])]
    )
    assert "нет такого варианта" in await bad(
        roles=[role(attribute_requirements=[{"code": "category", "op": "eq", "value": "Генерал"}])]
    )
    assert "только для чисел и дат" in await bad(
        roles=[role(attribute_requirements=[{"code": "category", "op": "gte", "value": "Курсант"}])]
    )
    assert "одно требование" in await bad(
        roles=[
            role(
                attribute_requirements=[
                    {"code": "course_no", "op": "gte", "value": 2},
                    {"code": "course_no", "op": "lte", "value": 4},
                ]
            )
        ]
    )


async def test_duplicate_active_name(admin: AsyncClient, org: Org) -> None:
    first = await add_type(admin, org.fac_a, "Патруль")
    r = await admin.post(
        "/duty-types",
        json={
            "name": "Патруль",
            "owner_unit_id": str(org.fac_a),
            "start_time": "18:00",
            "duration_minutes": 120,
            "roles": [role()],
        },
    )
    assert r.status_code == 409
    # Другое подразделение может завести наряд с тем же названием
    await add_type(admin, org.fac_b, "Патруль")
    # Выведенный из действия наряд имя не занимает
    r = await admin.put(
        f"/duty-types/{first['id']}", json={**_update_body(first), "is_active": False}
    )
    assert r.status_code == 200, r.text
    await add_type(admin, org.fac_a, "Патруль")


async def test_update_and_roles(
    admin: AsyncClient, org: Org, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    t = await add_type(admin, org.fac_a, "Караул")
    r = await admin.put(
        f"/duty-types/{t['id']}", json={**_update_body(t), "start_time": "09:00", "rest_hours": 24}
    )
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2
    # Устаревшая версия
    r = await admin.put(f"/duty-types/{t['id']}", json={**_update_body(t), "rest_hours": 12})
    assert r.status_code == 409

    r = await admin.post(
        f"/duty-types/{t['id']}/roles", json=role("Часовой", headcount=3, code="sentry")
    )
    assert r.status_code == 201, r.text
    roles = r.json()["roles"]
    assert [x["code"] for x in roles] == ["role1", "sentry"]
    sentry = roles[1]
    r = await admin.post(f"/duty-types/{t['id']}/roles", json=role("Ещё", code="sentry"))
    assert r.status_code == 409

    r = await admin.put(
        f"/duty-roles/{sentry['id']}",
        json={
            **role("Часовой", headcount=2, min_rank_order=10),
            "version": sentry["version"],
            "is_active": False,
        },
    )
    assert r.status_code == 200, r.text
    updated = r.json()["roles"][1]
    assert (updated["headcount"], updated["is_active"], updated["min_rank_order"]) == (2, False, 10)

    async with sessionmaker() as session:
        actions = list(
            await session.scalars(
                select(AuditLog.action)
                .where(AuditLog.scope_unit_id == org.fac_a)
                .order_by(AuditLog.occurred_at, AuditLog.id)
            )
        )
        events = list(
            await session.scalars(
                select(OutboxEvent.event_type)
                .where(OutboxEvent.event_type != "audit.recorded")
                .order_by(OutboxEvent.id)
            )
        )
        role_update = await session.scalar(
            select(AuditLog).where(AuditLog.action == "duty_role.update")
        )
    assert actions == [
        "duty_type.create",
        "duty_role.create",
        "duty_type.update",
        "duty_role.create",
        "duty_role.update",
    ]
    assert events == [
        "duty_type.changed",
        "duty_role.changed",
        "duty_type.changed",
        "duty_role.changed",
        "duty_role.changed",
    ]
    assert role_update is not None
    assert role_update.before == {
        "headcount": 3,
        "is_active": True,
        "min_rank_order": None,
    }

    r = await admin.get("/audit", params={"entity_type": "duty_role", "entity_id": sentry["id"]})
    assert r.json()["total"] == 2


async def test_audit_scope(client_for: ClientFactory, admin: AsyncClient, org: Org) -> None:
    await add_type(admin, org.fac_a, "Наряд A")
    fac_b_op = client_for(org.fac_b, "operator")
    assert (await fac_b_op.get("/audit")).json()["total"] == 0
    fac_a_op = client_for(org.fac_a, "viewer")
    assert (await fac_a_op.get("/audit")).json()["total"] == 2


async def test_internal_batch(admin: AsyncClient, internal: AsyncClient, org: Org) -> None:
    t = await add_type(
        admin,
        org.fac_a,
        "Наряд",
        roles=[role("Дежурный", min_rank_order=100), role("Дневальный", headcount=2)],
    )
    r = await internal.post("/internal/duty-roles/batch", json={})
    assert r.status_code == 200
    items = r.json()
    assert [i["name"] for i in items] == ["Дежурный", "Дневальный"]
    assert items[0]["duty_type"]["owner_unit_id"] == str(org.fac_a)
    assert items[0]["duty_type"]["name"] == "Наряд"
    one = await internal.post(
        "/internal/duty-roles/batch",
        json={"role_ids": [t["roles"][1]["id"]]},  # type: ignore[index]
    )
    assert [i["name"] for i in one.json()] == ["Дневальный"]
    no_token = await admin.post("/internal/duty-roles/batch", json={})
    assert no_token.status_code == 401


def _update_body(t: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "name",
        "short_name",
        "start_time",
        "duration_minutes",
        "rest_hours",
        "version",
        "is_active",
    )
    return {k: t[k] for k in keys}
