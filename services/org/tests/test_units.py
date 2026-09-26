import pytest
from conftest import INTERNAL_TOKEN, ClientFactory
from helpers import build_tree, create_unit, get_unit
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from org.settings import OrgSettings


async def test_health(anon: AsyncClient) -> None:
    r = await anon.get("/health")
    assert r.json() == {"status": "ok", "service": "org"}


async def test_requires_token(anon: AsyncClient) -> None:
    r = await anon.get("/units")
    assert r.status_code == 401
    assert r.json()["code"] == "unauthorized"


async def test_me_returns_root_for_superadmin(admin: AsyncClient, settings: OrgSettings) -> None:
    r = await admin.get("/me")
    assert r.status_code == 200
    body = r.json()
    assert body["unit"]["id"] == str(settings.root_unit_id)
    assert body["roles"] == ["superadmin"]
    assert "X-Request-Id" in r.headers


async def test_operator_sees_only_own_subtree(
    admin: AsyncClient, client_for: ClientFactory, settings: OrgSettings
) -> None:
    tree = await build_tree(admin, settings.root_unit_id)
    op = client_for(tree.faculty1, "operator")

    r = await op.get("/units")
    assert r.status_code == 200
    names = {u["name"] for u in r.json()}
    assert names == {"Факультет 1", "Курс 1.1", "Курс 1.2", "Группа 111"}

    # Чужое подразделение недоступно даже по прямому id
    assert (await op.get(f"/units/{tree.faculty2}")).status_code == 403
    assert (await op.get(f"/units/{settings.root_unit_id}")).status_code == 403


async def test_permissions_in_response(
    admin: AsyncClient, client_for: ClientFactory, settings: OrgSettings
) -> None:
    tree = await build_tree(admin, settings.root_unit_id)
    op = client_for(tree.faculty1, "operator")
    own = await get_unit(op, tree.faculty1)
    child = await get_unit(op, tree.course11)
    # Своё подразделение оператор не переносит и не расформировывает, но может добавлять дочерние
    assert own["permissions"] == {
        "update": False,
        "move": False,
        "delete": False,
        "create_child": True,
    }
    assert child["permissions"] == {
        "update": True,
        "move": True,
        "delete": True,
        "create_child": True,
    }

    viewer = client_for(tree.faculty1, "viewer")
    assert (await get_unit(viewer, tree.course11))["permissions"] == {
        "update": False,
        "move": False,
        "delete": False,
        "create_child": False,
    }


async def test_operator_cannot_create_outside_scope(
    admin: AsyncClient, client_for: ClientFactory, settings: OrgSettings
) -> None:
    tree = await build_tree(admin, settings.root_unit_id)
    op = client_for(tree.faculty1, "operator")
    r = await op.post(
        "/units",
        json={
            "parent_id": str(tree.faculty2),
            "unit_type_id": str(tree.types["course"]),
            "name": "Чужой курс",
        },
    )
    assert r.status_code == 403
    # а внутри своего поддерева — можно
    await create_unit(op, tree.faculty1, tree.types["course"], "Курс 1.3")


async def test_hierarchy_levels_enforced(admin: AsyncClient, settings: OrgSettings) -> None:
    tree = await build_tree(admin, settings.root_unit_id)
    r = await admin.post(
        "/units",
        json={
            "parent_id": str(tree.group111),
            "unit_type_id": str(tree.types["faculty"]),
            "name": "Факультет внутри группы",
        },
    )
    assert r.status_code == 422


async def test_duplicate_name_under_parent_rejected(
    admin: AsyncClient, settings: OrgSettings
) -> None:
    tree = await build_tree(admin, settings.root_unit_id)
    r = await admin.post(
        "/units",
        json={
            "parent_id": str(tree.faculty1),
            "unit_type_id": str(tree.types["course"]),
            "name": "Курс 1.1",
        },
    )
    assert r.status_code == 409


async def test_move_subtree_rewrites_descendant_paths(
    admin: AsyncClient, settings: OrgSettings
) -> None:
    tree = await build_tree(admin, settings.root_unit_id)
    course = await get_unit(admin, tree.course11)
    group_before = await get_unit(admin, tree.group111)

    r = await admin.post(
        f"/units/{tree.course11}/move",
        json={"new_parent_id": str(tree.faculty2), "version": course["version"]},
    )
    assert r.status_code == 200, r.text
    moved = r.json()
    f2 = await get_unit(admin, tree.faculty2)
    assert moved["parent_id"] == str(tree.faculty2)
    assert str(moved["path"]).startswith(f"{f2['path']}.")

    group_after = await get_unit(admin, tree.group111)
    # Группа уехала вместе с курсом, её собственная метка в пути не изменилась
    assert group_after["path"] == f"{moved['path']}.{str(group_before['path']).split('.')[-1]}"
    assert group_after["depth"] == group_before["depth"]


async def test_cannot_move_into_own_descendant(admin: AsyncClient, settings: OrgSettings) -> None:
    tree = await build_tree(admin, settings.root_unit_id)
    f1 = await get_unit(admin, tree.faculty1)
    r = await admin.post(
        f"/units/{tree.faculty1}/move",
        json={"new_parent_id": str(tree.course11), "version": f1["version"]},
    )
    assert r.status_code == 422


async def test_operator_cannot_move_own_unit(
    admin: AsyncClient, client_for: ClientFactory, settings: OrgSettings
) -> None:
    tree = await build_tree(admin, settings.root_unit_id)
    op = client_for(tree.course11, "operator")
    course = await get_unit(op, tree.course11)
    r = await op.post(
        f"/units/{tree.course11}/move",
        json={"new_parent_id": str(tree.faculty2), "version": course["version"]},
    )
    assert r.status_code == 403


async def test_stale_version_conflict(admin: AsyncClient, settings: OrgSettings) -> None:
    tree = await build_tree(admin, settings.root_unit_id)
    unit = await get_unit(admin, tree.course12)
    first = await admin.patch(
        f"/units/{tree.course12}", json={"name": "Курс 1.2 (А)", "version": unit["version"]}
    )
    assert first.status_code == 200
    assert first.json()["version"] == int(str(unit["version"])) + 1
    second = await admin.patch(
        f"/units/{tree.course12}", json={"name": "Курс 1.2 (Б)", "version": unit["version"]}
    )
    assert second.status_code == 409


async def test_rename_is_audited_with_diff(admin: AsyncClient, settings: OrgSettings) -> None:
    tree = await build_tree(admin, settings.root_unit_id)
    unit = await get_unit(admin, tree.course12)
    await admin.patch(f"/units/{tree.course12}", json={"name": "Новое", "version": unit["version"]})
    r = await admin.get("/audit", params={"entity_type": "unit", "entity_id": str(tree.course12)})
    items = r.json()["items"]
    assert [i["action"] for i in items] == ["unit.update", "unit.create"]
    assert items[0]["before"] == {"name": "Курс 1.2"}
    assert items[0]["after"] == {"name": "Новое"}
    assert items[0]["actor_name"] == "admin"


async def test_operator_sees_audit_only_in_scope(
    admin: AsyncClient, client_for: ClientFactory, settings: OrgSettings
) -> None:
    tree = await build_tree(admin, settings.root_unit_id)
    op = client_for(tree.faculty2, "operator")
    items = (await op.get("/audit", params={"entity_type": "unit"})).json()["items"]
    assert {i["entity_id"] for i in items} == {str(tree.faculty2)}


async def test_audit_log_is_append_only(admin: AsyncClient, settings: OrgSettings) -> None:
    await build_tree(admin, settings.root_unit_id)
    engine = create_async_engine(settings.database_url)
    try:
        with pytest.raises(DBAPIError, match="append-only"):
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM audit_log"))
    finally:
        await engine.dispose()


async def test_deactivate_requires_no_active_children(
    admin: AsyncClient, settings: OrgSettings
) -> None:
    tree = await build_tree(admin, settings.root_unit_id)
    c11 = await get_unit(admin, tree.course11)
    r = await admin.delete(f"/units/{tree.course11}", params={"version": c11["version"]})
    assert r.status_code == 409

    g = await get_unit(admin, tree.group111)
    r = await admin.delete(f"/units/{tree.group111}", params={"version": g["version"]})
    assert r.status_code == 200
    assert r.json()["is_active"] is False
    names = {u["name"] for u in (await admin.get("/units")).json()}
    assert "Группа 111" not in names


async def test_events_written_to_outbox(admin: AsyncClient, settings: OrgSettings) -> None:
    tree = await build_tree(admin, settings.root_unit_id)
    unit = await get_unit(admin, tree.course12)
    await admin.post(
        f"/units/{tree.course12}/move",
        json={"new_parent_id": str(tree.faculty2), "version": unit["version"]},
    )
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        types = (await conn.execute(text("SELECT event_type FROM outbox"))).scalars().all()
    await engine.dispose()
    assert types.count("unit.created") == 6  # корень + 5 узлов
    assert "unit.moved" in types
    assert "audit.recorded" in types


async def test_internal_batch_requires_token(
    client_for: ClientFactory, admin: AsyncClient, anon: AsyncClient, settings: OrgSettings
) -> None:
    tree = await build_tree(admin, settings.root_unit_id)
    body = {"unit_ids": [str(tree.faculty1)]}
    assert (await anon.post("/internal/units/descendants-batch", json=body)).status_code == 401

    r = await anon.post(
        "/internal/units/descendants-batch",
        json=body,
        headers={"X-Internal-Token": INTERNAL_TOKEN},
    )
    assert r.status_code == 200
    assert {u["name"] for u in r.json()} == {"Факультет 1", "Курс 1.1", "Курс 1.2", "Группа 111"}

    r = await anon.post(
        "/internal/units/batch",
        json={"unit_ids": []},
        headers={"X-Internal-Token": INTERNAL_TOKEN},
    )
    assert len(r.json()) == 6


async def test_ancestors(admin: AsyncClient, settings: OrgSettings) -> None:
    tree = await build_tree(admin, settings.root_unit_id)
    r = await admin.get(f"/units/{tree.group111}/ancestors")
    assert [u["name"] for u in r.json()] == ["Академия", "Факультет 1", "Курс 1.1"]


async def test_root_cannot_be_moved_or_deactivated(
    admin: AsyncClient, settings: OrgSettings
) -> None:
    root = await get_unit(admin, settings.root_unit_id)
    assert root["permissions"] == {
        "update": True,
        "move": False,
        "delete": False,
        "create_child": True,
    }
    r = await admin.delete(f"/units/{settings.root_unit_id}", params={"version": root["version"]})
    assert r.status_code == 422
