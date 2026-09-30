from conftest import CADET, PERMANENT, ClientFactory, Org, add_person, emit, unit_payload
from httpx import AsyncClient

CATEGORY = "skill"


async def names(client: AsyncClient, **params: object) -> list[str]:
    r = await client.get("/people", params={k: str(v) for k, v in params.items()})
    assert r.status_code == 200, r.text
    return [p["last_name"] for p in r.json()["items"]]


async def test_operator_sees_only_own_subtree(
    admin: AsyncClient, client_for: ClientFactory, org: Org
) -> None:
    await add_person(admin, org.fac_a, "Алексеев")
    await add_person(admin, org.course_a1, "Борисов")
    await add_person(admin, org.fac_b, "Васильев")

    op_a = client_for(org.fac_a, "operator")
    assert await names(op_a) == ["Алексеев", "Борисов"]
    assert await names(client_for(org.fac_b, "viewer")) == ["Васильев"]
    # Фильтр по подразделению без поддерева
    assert await names(op_a, unit_id=org.fac_a, subtree="false") == ["Алексеев"]


async def test_card_and_foreign_person_hidden(
    admin: AsyncClient, client_for: ClientFactory, org: Org
) -> None:
    person = await add_person(admin, org.fac_b, "Чужой", rank_id=str(org.rank_major))
    r = await admin.get(f"/people/{person['id']}")
    assert r.json()["rank_name"] == "Майор"
    assert r.json()["unit_name"] == "Факультет B"
    # Для оператора другого факультета человека «нет»
    op_a = client_for(org.fac_a, "operator")
    assert (await op_a.get(f"/people/{person['id']}")).status_code == 403


async def test_viewer_cannot_create(client_for: ClientFactory, org: Org) -> None:
    viewer = client_for(org.fac_a, "viewer")
    r = await viewer.post(
        "/people",
        json={
            "unit_id": str(org.fac_a),
            "category_id": str(CADET),
            "last_name": "X",
            "first_name": "Y",
        },
    )
    assert r.status_code == 403


async def test_attributes_validated_and_stored(admin: AsyncClient, org: Org) -> None:
    bad = await admin.post(
        "/people",
        json={
            "unit_id": str(org.fac_a),
            "category_id": str(CADET),
            "last_name": "Иванов",
            "first_name": "Пётр",
            "attributes": {CATEGORY: "Высший класс"},
        },
    )
    assert bad.status_code == 422
    assert "допустимые значения" in bad.json()["message"]

    unknown = await admin.post(
        "/people",
        json={
            "unit_id": str(org.fac_a),
            "category_id": str(CADET),
            "last_name": "Иванов",
            "first_name": "Пётр",
            "attributes": {"x": 1},
        },
    )
    assert unknown.status_code == 422

    person = await add_person(admin, org.fac_a, "Иванов", attributes={CATEGORY: "1 класс"})
    assert person["attributes"] == {CATEGORY: "1 класс"}


async def test_required_attribute(admin: AsyncClient, org: Org) -> None:
    r = await admin.post(
        "/attribute-definitions",
        json={
            "code": "driver",
            "name": "Водительское удостоверение",
            "value_type": "bool",
            "is_required": True,
        },
    )
    assert r.status_code == 201
    missing = await admin.post(
        "/people",
        json={
            "unit_id": str(org.fac_a),
            "category_id": str(CADET),
            "last_name": "А",
            "first_name": "Б",
        },
    )
    assert missing.status_code == 422
    assert "Водительское удостоверение" in missing.json()["message"]
    ok = await add_person(admin, org.fac_a, "А", attributes={"driver": True})
    assert ok["attributes"]["driver"] is True  # type: ignore[index]


async def test_personal_no_unique(admin: AsyncClient, org: Org) -> None:
    await add_person(admin, org.fac_a, "Первый", personal_no="Ж-123")
    r = await admin.post(
        "/people",
        json={
            "unit_id": str(org.fac_a),
            "category_id": str(CADET),
            "last_name": "Второй",
            "first_name": "И",
            "personal_no": "Ж-123",
        },
    )
    assert r.status_code == 409


async def test_search_by_fio_substring_and_personal_no(admin: AsyncClient, org: Org) -> None:
    await add_person(admin, org.fac_a, "Кузнецов", "Андрей", middle_name="Петрович")
    await add_person(admin, org.fac_a, "Смирнов", "Олег", personal_no="АБ-7")
    await add_person(admin, org.fac_a, "Кузьмин", "Олег")
    assert await names(admin, q="кузн") == ["Кузнецов"]
    assert await names(admin, q="олег") == ["Кузьмин", "Смирнов"]
    assert await names(admin, q="АБ-7") == ["Смирнов"]
    assert await names(admin, q="100%") == []  # спецсимволы LIKE экранируются


async def test_update_version_conflict_and_audit(admin: AsyncClient, org: Org) -> None:
    person = await add_person(admin, org.fac_a, "Орлов", attributes={CATEGORY: "1 класс"})
    pid, version = person["id"], person["version"]
    r = await admin.patch(
        f"/people/{pid}",
        json={"version": version, "first_name": "Павел", "attributes": {CATEGORY: "2 класс"}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["version"] == int(str(version)) + 1
    stale = await admin.patch(f"/people/{pid}", json={"version": version, "first_name": "Х"})
    assert stale.status_code == 409

    audit = (await admin.get("/audit", params={"entity_id": str(pid)})).json()["items"]
    assert audit[0]["action"] == "person.update"
    assert audit[0]["before"] == {"first_name": "Иван", "attributes": {CATEGORY: "1 класс"}}
    assert audit[0]["after"] == {"first_name": "Павел", "attributes": {CATEGORY: "2 класс"}}


async def test_attribute_only_change_bumps_version(admin: AsyncClient, org: Org) -> None:
    person = await add_person(admin, org.fac_a, "Лебедев")
    r = await admin.patch(
        f"/people/{person['id']}",
        json={"version": person["version"], "attributes": {CATEGORY: "1 класс"}},
    )
    assert r.json()["version"] == int(str(person["version"])) + 1


async def test_archive_and_restore(admin: AsyncClient, org: Org) -> None:
    person = await add_person(admin, org.fac_a, "Архивов")
    r = await admin.post(
        f"/people/{person['id']}/archive",
        json={"version": person["version"], "comment": "Выпуск 2026"},
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is False
    assert r.json()["archived_at"] is not None
    assert await names(admin) == []
    assert await names(admin, include_archived="true") == ["Архивов"]
    blocked = await admin.patch(
        f"/people/{person['id']}", json={"version": r.json()["version"], "note": "x"}
    )
    assert blocked.status_code == 422
    restored = await admin.post(
        f"/people/{person['id']}/restore", json={"version": r.json()["version"]}
    )
    assert restored.json()["is_active"] is True


async def test_transfer_scope_and_atomicity(
    admin: AsyncClient, client_for: ClientFactory, org: Org
) -> None:
    a = await add_person(admin, org.fac_a, "Переводов")
    b = await add_person(admin, org.fac_b, "Чужаков")
    op_a = client_for(org.fac_a, "operator")

    # Цель вне scope
    r = await op_a.post(
        "/people/transfer", json={"person_ids": [a["id"]], "unit_id": str(org.fac_b)}
    )
    assert r.status_code == 403
    # Один из людей вне scope — не переводится никто
    r = await op_a.post(
        "/people/transfer", json={"person_ids": [a["id"], b["id"]], "unit_id": str(org.course_a1)}
    )
    assert r.status_code == 403
    assert (await admin.get(f"/people/{a['id']}")).json()["unit_id"] == str(org.fac_a)

    r = await op_a.post(
        "/people/transfer", json={"person_ids": [a["id"]], "unit_id": str(org.course_a1)}
    )
    assert r.json() == {"done": 1, "skipped": []}
    card = (await admin.get(f"/people/{a['id']}")).json()
    assert card["unit_name"] == "Курс A1"


async def test_moved_subtree_changes_scope(
    admin: AsyncClient, client_for: ClientFactory, org: Org, sessionmaker: object
) -> None:
    """Перенос подразделения в org → событие unit.moved → люди «переезжают» в чужой scope."""
    await add_person(admin, org.course_a1, "Курсантов")
    op_a, op_b = client_for(org.fac_a, "operator"), client_for(org.fac_b, "operator")
    assert await names(op_a) == ["Курсантов"]

    await emit(
        sessionmaker,
        "unit.moved",
        org.course_a1,
        {  # type: ignore[arg-type]
            **unit_payload(org.course_a1, org.fac_b, "1.4.3", "Курс A1", version=2),
            "old_path": "1.2.3",
            "new_path": "1.4.3",
        },
    )
    assert await names(op_a) == []
    assert await names(op_b) == ["Курсантов"]


async def test_stale_unit_event_ignored(admin: AsyncClient, org: Org, sessionmaker: object) -> None:
    await emit(
        sessionmaker,
        "unit.updated",
        org.fac_a,  # type: ignore[arg-type]
        unit_payload(org.fac_a, org.root, "1.2", "Факультет A (нов.)", version=3),
    )
    await emit(
        sessionmaker,
        "unit.updated",
        org.fac_a,  # type: ignore[arg-type]
        unit_payload(org.fac_a, org.root, "1.2", "Факультет A (стар.)", version=2),
    )
    person = await add_person(admin, org.fac_a, "Проверкин")
    assert person["unit_name"] == "Факультет A (нов.)"


async def test_operator_unit_not_in_projection(client_for: ClientFactory) -> None:
    import uuid

    r = await client_for(uuid.uuid4(), "operator").get("/people")
    assert r.status_code == 403


async def test_category_filter_and_exempt_today(admin: AsyncClient, org: Org) -> None:
    """Категория и отметка «освобождён сегодня» — в списке и фильтрах (ADR-0018, фаза 8)."""
    import datetime as dt

    cadet = await add_person(admin, org.fac_a, "Курсантов")
    officer = await add_person(admin, org.fac_a, "Офицеров", category_id=str(PERMANENT))
    assert await names(admin, category_id=PERMANENT) == ["Офицеров"]
    assert cadet["category_name"] == "Курсант"
    assert officer["category_name"] == "Постоянный состав"

    reasons = (await admin.get("/exemption-reasons")).json()
    today = dt.date.today()
    r = await admin.post(
        f"/people/{cadet['id']}/exemptions",
        json={
            "reason_id": reasons[0]["id"],
            "date_from": str(today - dt.timedelta(days=1)),
            "date_to": str(today + dt.timedelta(days=2)),
        },
    )
    assert r.status_code == 201, r.text
    assert await names(admin, exempt_today=True) == ["Курсантов"]
    items = (await admin.get("/people")).json()["items"]
    exempt = {i["last_name"]: i["exempt_until"] for i in items}
    assert exempt == {"Курсантов": str(today + dt.timedelta(days=2)), "Офицеров": None}

    bad = await admin.post(
        "/people",
        json={"unit_id": str(org.fac_a), "last_name": "Б", "first_name": "К"},
    )
    assert bad.status_code == 422  # без категории человека не завести


async def test_person_categories_reference(
    admin: AsyncClient, client_for: ClientFactory, org: Org
) -> None:
    """Справочник категорий ведёт суперадминистратор, читают все (ADR-0018)."""
    listed = (await admin.get("/person-categories")).json()
    assert [c["name"] for c in listed] == ["Курсант", "Слушатель", "Постоянный состав"]
    op = client_for(org.fac_a, "operator")
    assert len((await op.get("/person-categories")).json()) == 3
    body = {"code": "contract", "name": "Контрактник", "sort_order": 5}
    assert (await op.post("/person-categories", json=body)).status_code == 403
    r = await admin.post("/person-categories", json=body)
    assert r.status_code == 201, r.text
    assert (await admin.post("/person-categories", json=body)).status_code == 409
    r = await admin.put(f"/person-categories/{r.json()['id']}", json={**body, "is_active": False})
    assert r.status_code == 200
    # Выведенную из действия категорию новому человеку не назначить
    bad = await admin.post(
        "/people",
        json={
            "unit_id": str(org.fac_a),
            "last_name": "К",
            "first_name": "К",
            "category_id": r.json()["id"],
        },
    )
    assert bad.status_code == 422


async def test_people_counts_by_unit(
    admin: AsyncClient, client_for: ClientFactory, org: Org
) -> None:
    await add_person(admin, org.fac_a, "Первый")
    await add_person(admin, org.course_a1, "Второй")
    await add_person(admin, org.course_a1, "Третий")
    await add_person(admin, org.fac_b, "Чужой")
    counts = {c["unit_id"]: c["people"] for c in (await admin.get("/people/counts")).json()}
    assert counts == {str(org.fac_a): 1, str(org.course_a1): 2, str(org.fac_b): 1}
    op = client_for(org.fac_a, "operator")
    counts = {c["unit_id"]: c["people"] for c in (await op.get("/people/counts")).json()}
    assert counts == {str(org.fac_a): 1, str(org.course_a1): 2}
