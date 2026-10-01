"""Операторы (фаза 7a, open-questions №59, №61): scope, роли, временные пароли, блокировка,
аудит без паролей, настройка Keycloak."""

import httpx
from conftest import COURSE, FACULTY, OTHER, ROOT, ClientFactory, FakeKeycloak, People
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from auth_admin.bootstrap import PASSWORD_POLICY, bootstrap
from auth_admin.settings import AuthAdminSettings
from dutyflow_common.audit import AuditLog


def new(role: str, unit: object, username: str = "new_user") -> dict[str, object]:
    return {
        "username": username,
        "last_name": "Новиков",
        "first_name": "Пётр",
        "role": role,
        "unit_id": str(unit),
    }


async def test_list_by_scope(client_for: ClientFactory, people: People) -> None:
    fac = client_for(FACULTY, "unit_admin", sub=people.fac_admin)
    page = (await fac.get("/operators")).json()
    assert sorted(o["username"] for o in page["items"]) == [
        "course_admin",
        "fac_admin",
        "fac_operator",
    ]
    me = next(o for o in page["items"] if o["username"] == "fac_admin")
    assert (me["self"], me["can_edit"]) == (True, False)
    course = next(o for o in page["items"] if o["username"] == "course_admin")
    assert course["can_edit"] is True  # администратор нижестоящего
    assert course["unit_name"] == "1 курс"

    root = client_for(ROOT, "superadmin", sub=people.root_admin)
    assert (await root.get("/operators")).json()["total"] == 5
    found = (await root.get("/operators", params={"q": "OTHER"})).json()
    assert [o["username"] for o in found["items"]] == ["other_admin"]
    only = (await root.get("/operators", params={"unit_id": str(COURSE)})).json()
    assert [o["username"] for o in only["items"]] == ["course_admin"]

    operator = client_for(FACULTY, "operator", sub=people.fac_operator)
    assert (await operator.get("/operators")).status_code == 403


async def test_role_ceiling(client_for: ClientFactory, people: People) -> None:
    fac = client_for(FACULTY, "unit_admin", sub=people.fac_admin)
    assert (await fac.get("/operators/roles", params={"unit_id": str(FACULTY)})).json() == [
        "operator",
        "viewer",
    ]
    assert (await fac.get("/operators/roles", params={"unit_id": str(COURSE)})).json() == [
        "unit_admin",
        "operator",
        "viewer",
    ]
    for role, unit, status in (
        ("unit_admin", FACULTY, 403),  # равный себе
        ("superadmin", COURSE, 403),
        ("operator", OTHER, 403),  # вне поддерева
        ("unit_admin", COURSE, 201),
    ):
        r = await fac.post("/operators", json=new(role, unit, f"u_{role}_{status}"))
        assert r.status_code == status, (role, unit, r.text)
    bad = await fac.post("/operators", json={**new("operator", COURSE), "username": "Иван!"})
    assert bad.status_code == 422
    await fac.post("/operators", json=new("operator", COURSE, "dup"))
    assert (await fac.post("/operators", json=new("operator", COURSE, "dup"))).status_code == 409


async def test_create_update_block_reset(
    client_for: ClientFactory,
    people: People,
    keycloak: FakeKeycloak,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    fac = client_for(FACULTY, "unit_admin", sub=people.fac_admin)
    r = await fac.post("/operators", json=new("operator", COURSE))
    assert r.status_code == 201, r.text
    created = r.json()
    uid = created["id"]
    password = created["temporary_password"]
    assert len(password) == 12
    assert keycloak.passwords[uid] == (password, True)  # сменить при первом входе
    assert keycloak.users[uid]["requiredActions"] == ["UPDATE_PASSWORD"]
    assert keycloak.roles[uid] == {"operator"}

    upd = await fac.patch(f"/operators/{uid}", json={"role": "viewer", "unit_id": str(FACULTY)})
    assert upd.status_code == 200, upd.text
    assert keycloak.roles[uid] == {"viewer"}
    assert keycloak.users[uid]["attributes"]["unit_id"] == [str(FACULTY)]
    # Повысить до администратора своего же подразделения нельзя
    assert (await fac.patch(f"/operators/{uid}", json={"role": "unit_admin"})).status_code == 403
    # Себе — ни роль, ни подразделение
    me = await fac.patch(f"/operators/{people.fac_admin}", json={"role": "operator"})
    assert me.status_code in (403, 422)

    assert (await fac.post(f"/operators/{uid}/block")).json()["enabled"] is False
    assert uid in keycloak.logouts
    assert (await fac.post(f"/operators/{uid}/unblock")).json()["enabled"] is True
    assert (await fac.post(f"/operators/{people.fac_admin}/block")).status_code == 422

    keycloak.logouts.clear()
    assert (await fac.post(f"/operators/{uid}/logout")).status_code == 200
    assert keycloak.logouts == [uid]

    reset = (await fac.post(f"/operators/{uid}/reset-password")).json()
    assert reset["temporary_password"] != password
    assert keycloak.passwords[uid] == (reset["temporary_password"], True)

    # Чужой администратор (другой факультет) этим оператором не управляет
    other = client_for(OTHER, "unit_admin", sub=people.other_admin)
    assert (await other.post(f"/operators/{uid}/block")).status_code == 403

    async with sessionmaker() as s:
        rows = list(await s.scalars(select(AuditLog).order_by(AuditLog.occurred_at)))
    assert [r.action for r in rows] == [
        "operator.create",
        "operator.update",
        "operator.block",
        "operator.unblock",
        "operator.logout",
        "operator.reset_password",
    ]
    dump = str([(r.before, r.after) for r in rows])
    assert password not in dump
    assert reset["temporary_password"] not in dump


async def test_bootstrap_is_idempotent(settings: AuthAdminSettings, keycloak: FakeKeycloak) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/realms/master/protocol/openid-connect/token":
            return httpx.Response(200, json={"access_token": "admin"})
        return keycloak.handler(request)

    for _ in range(2):
        await bootstrap(settings, transport=httpx.MockTransport(handler))
    client = keycloak.clients["dutyflow-auth-admin"]
    assert client["secret"] == "secret"
    assert client["serviceAccountsEnabled"] is True
    assert client["standardFlowEnabled"] is False
    assert keycloak.client_roles["sa"] == [
        "manage-users",
        "query-users",
        "view-realm",
        "view-users",
    ]
    assert keycloak.realm["passwordPolicy"] == PASSWORD_POLICY
    assert keycloak.realm["waitIncrementSeconds"] == 900
    assert keycloak.realm["sslRequired"] == "none"


def test_spa_urls_follow_public_url() -> None:
    from auth_admin.bootstrap import spa_urls

    client = {
        "clientId": "dutyflow-spa",
        "redirectUris": ["http://localhost:8088/*", "http://localhost:5173/*"],
        "webOrigins": ["http://localhost:8088"],
        "attributes": {
            "post.logout.redirect.uris": "http://localhost:8088/*##http://localhost:5173/*"
        },
    }
    out = spa_urls(client, "https://localhost:8443/")
    assert "https://localhost:8443/*" in out["redirectUris"]
    assert "http://localhost:5173/*" in out["redirectUris"]
    assert "https://localhost:8443" in out["webOrigins"]
    assert "https://localhost:8443/*" in out["attributes"]["post.logout.redirect.uris"].split("##")


async def test_internal_usage_counts_operators_of_unit(
    app: object, settings: AuthAdminSettings, people: People
) -> None:
    """ADR-0023: org не удалит подразделение, к которому привязаны операторы."""
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    headers = {"X-Internal-Token": settings.internal_token}
    async with httpx.AsyncClient(transport=transport, base_url="http://t", headers=headers) as c:
        r = await c.post("/internal/usage/unit", json={"id": str(FACULTY)})
        assert r.status_code == 200, r.text
        assert r.json()["operators"] >= 1
        empty = "00000000-0000-7000-8000-0000000000ee"
        assert (await c.post("/internal/usage/unit", json={"id": empty})).json() == {"operators": 0}
        assert (await c.post("/internal/usage/rank", json={"id": empty})).json() == {}


async def test_delete_operator_superadmin_only(
    client_for: ClientFactory,
    people: People,
    keycloak: FakeKeycloak,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """ADR-0023 (меняет №59): удалить учётную запись может только суперадминистратор."""
    fac = client_for(FACULTY, "unit_admin", sub=people.fac_admin)
    assert (await fac.delete(f"/operators/{people.fac_operator}")).status_code == 403

    root = client_for(ROOT, "superadmin", sub=people.root_admin)
    assert (await root.delete(f"/operators/{people.root_admin}")).status_code == 422  # себя
    assert (await root.delete(f"/operators/{people.fac_operator}")).status_code == 204
    assert people.fac_operator not in keycloak.users

    async with sessionmaker() as session:
        entry = await session.scalar(select(AuditLog).where(AuditLog.action == "operator.delete"))
    assert entry is not None
    assert entry.before is not None
    assert entry.before["username"]  # логин остаётся в журнале


async def test_last_superadmin_cannot_be_deleted(
    client_for: ClientFactory, people: People, keycloak: FakeKeycloak
) -> None:
    other = keycloak.add("second_root", "superadmin", ROOT)
    root = client_for(ROOT, "superadmin", sub=other)
    # Второй суперадминистратор удаляет первого — первый не последний
    assert (await root.delete(f"/operators/{people.root_admin}")).status_code == 204
    # Остался один суперадминистратор «second_root»: его не удалит никто — ни он сам, ни
    # другой суперадминистратор из ещё действующего токена (учётка уже удалена в Keycloak)
    stale = client_for(ROOT, "superadmin", sub=people.root_admin)
    r = await stale.delete(f"/operators/{other}")
    assert r.status_code == 422
    assert "последний суперадминистратор" in r.text
