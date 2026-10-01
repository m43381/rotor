"""Удаление нарядов и ролей, возврат графика из архива (ADR-0023)."""

from conftest import ClientFactory, Org
from httpx import AsyncClient
from test_assignments import assign, person, setup


async def test_delete_role_and_type_unless_people_assigned(
    admin: AsyncClient, client_for: ClientFactory, org: Org
) -> None:
    s = await setup(admin, org)  # черновик графика с пустыми ячейками обеих ролей
    t = (await admin.get(f"/duty-types/{s.type['id']}")).json()
    roles = {r["name"]: r for r in t["roles"]}

    op = client_for(org.fac_a, "unit_admin")
    duty = roles["Дежурный"]
    r = await op.delete(f"/duty-roles/{duty['id']}", params={"version": duty["version"]})
    assert r.status_code == 403

    # Человек в ячейке «Дневальный» — роль и весь наряд удалить нельзя
    p = person(org, s, "Назначенный")
    r = await assign(admin, s.cell("Дневальный", 5), p)
    assert r.status_code == 201, r.text
    assignment_id = r.json()["assigned"][0]["id"]
    orderly = roles["Дневальный"]
    r = await admin.delete(f"/duty-roles/{orderly['id']}", params={"version": orderly["version"]})
    assert r.status_code == 409
    assert "назначений в наряды: 1" in r.text
    r = await admin.delete(f"/duty-types/{t['id']}", params={"version": t["version"]})
    assert r.status_code == 409

    # Пустые ячейки черновика не мешают: роль «Дежурный» удаляется вместе с ними
    r = await admin.delete(f"/duty-roles/{duty['id']}", params={"version": duty["version"]})
    assert r.status_code == 204, r.text
    table = (await admin.get(f"/schedules/{s.schedule['id']}/table")).json()
    assert {row["role_name"] for row in table["rows"]} == {"Дневальный"}

    # Последнюю роль не удалить — только наряд целиком
    r = await admin.delete(f"/duty-roles/{orderly['id']}", params={"version": orderly["version"]})
    assert r.status_code == 422

    # Сняли человека — наряд удаляется вместе с ячейками черновика
    assert (await admin.delete(f"/assignments/{assignment_id}")).status_code == 200
    t = (await admin.get(f"/duty-types/{t['id']}")).json()
    r = await admin.delete(f"/duty-types/{t['id']}", params={"version": t["version"]})
    assert r.status_code == 204, r.text
    assert (await admin.get(f"/duty-types/{t['id']}")).status_code == 404
    table = (await admin.get(f"/schedules/{s.schedule['id']}/table")).json()
    assert table["rows"] == []


async def test_unarchive_schedule(admin: AsyncClient, client_for: ClientFactory, org: Org) -> None:
    s = await setup(admin, org)
    sch = s.schedule
    r = await admin.post(f"/schedules/{sch['id']}/publish", json={"version": sch["version"]})
    sch = r.json()["schedule"]
    sch = (
        await admin.post(f"/schedules/{sch['id']}/archive", json={"version": sch["version"]})
    ).json()
    assert sch["status"] == "archived"

    op = client_for(org.fac_a, "unit_admin")
    r = await op.post(f"/schedules/{sch['id']}/unarchive", json={"version": sch["version"]})
    assert r.status_code == 403
    r = await admin.post(f"/schedules/{sch['id']}/unarchive", json={"version": sch["version"]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "published"
    r = await admin.post(f"/schedules/{sch['id']}/unarchive", json={"version": r.json()["version"]})
    assert r.status_code == 422
