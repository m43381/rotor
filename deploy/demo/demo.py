"""Демонстрационные данные DutyFlow: структура академии, справочники, личный состав, наряды,
допуски, освобождения и учётные записи операторов.

Загружается через публичный API стенда от имени суперадминистратора `admin`, поэтому проходит
все проверки и пишет журнал аудита, как ручной ввод. Детерминирован: ФИО и состав каждого
подразделения зависят только от его названия. Повторный запуск дописывает недостающее и ничего
не дублирует — подразделения ищутся по названию, люди по личному номеру, наряды по названию
у владельца, операторы по логину. Уже существующие записи не меняются.

На сервере (без Python):   ./dutyflow.sh demo
Переменные окружения:      DEMO_BASE_URL (по умолчанию http://gateway), DUTYFLOW_ADMIN_PASSWORD,
                           KEYCLOAK_ADMIN, KEYCLOAK_ADMIN_PASSWORD, DEMO_PASSWORD
"""

import asyncio
import datetime as dt
import os
import random
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import httpx
from names import fio

SEED = 20261001
FACULTIES = range(1, 10)
# Как у 6-го факультета: кафедры с номерами N1, N2, N5 и курсы N1–N5
FACULTY_KAFEDRAS = (1, 2, 5)
COURSES = range(1, 6)
ACADEMY_KAFEDRAS = ("102 Кафедра",)
# 9-й факультет готовит слушателей-офицеров — другая категория личного состава
LISTENER_FACULTIES = {9}
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demo-password-1")

UNIT_TYPES = [  # код, название, уровень, могут ли быть дочерние
    ("faculty", "Факультет", 1, True),
    ("kafedra", "Кафедра", 2, True),
    ("kurs", "Курс", 2, True),
    ("group", "Учебная группа", 3, False),
]
RANKS = [
    ("Рядовой", "ряд.", 10),
    ("Ефрейтор", "ефр.", 20),
    ("Младший сержант", "мл. с-т", 30),
    ("Сержант", "с-т", 40),
    ("Старший сержант", "ст. с-т", 50),
    ("Старшина", "ст-на", 60),
    ("Прапорщик", "прап.", 70),
    ("Старший прапорщик", "ст. прап.", 80),
    ("Младший лейтенант", "мл. л-т", 90),
    ("Лейтенант", "л-т", 100),
    ("Старший лейтенант", "ст. л-т", 110),
    ("Капитан", "к-н", 120),
    ("Майор", "м-р", 130),
    ("Подполковник", "п/п-к", 140),
    ("Полковник", "п-к", 150),
    ("Генерал-майор", "ген.-м.", 160),
]
RANK_ORDER = {name: order for name, _, order in RANKS}
POSITIONS = [
    "Начальник академии",
    "Заместитель начальника академии",
    "Офицер управления академии",
    "Начальник факультета",
    "Заместитель начальника факультета",
    "Офицер управления факультета",
    "Начальник курса",
    "Курсовой офицер",
    "Старшина курса",
    "Заместитель командира взвода",
    "Командир отделения",
    "Курсант",
    "Слушатель",
    "Начальник кафедры",
    "Заместитель начальника кафедры",
    "Профессор",
    "Доцент",
    "Старший преподаватель",
    "Преподаватель",
    "Инженер кафедры",
    "Лаборант",
]
CATEGORIES = [("civil", "Гражданский персонал", 4)]  # курсант, слушатель, постоянный — есть
ATTRIBUTES = [  # код, название, тип, варианты
    ("course_no", "Курс обучения", "int", None),
    ("gender", "Пол", "enum", ["М", "Ж"]),
    ("driver_license", "Водительское удостоверение", "bool", None),
    ("phys_grade", "Оценка по физподготовке", "enum", ["отлично", "хорошо", "удовлетворительно"]),
    ("weapon_access", "Допуск к оружию", "bool", None),
]


# --- HTTP: клиент с обновлением токена (живёт 5 минут, загрузка дольше) --------------------------


class Api:
    def __init__(self, base: str, password: str) -> None:
        self.http = httpx.AsyncClient(base_url=base, timeout=120.0)
        self.password = password
        self._token = ""
        self._at = 0.0
        self.sem = asyncio.Semaphore(8)

    async def _headers(self) -> dict[str, str]:
        if time.monotonic() - self._at > 200:
            r = await self.http.post(
                "/auth/realms/dutyflow/protocol/openid-connect/token",
                data={
                    "grant_type": "password",
                    "client_id": "dutyflow-cli",
                    "username": "admin",
                    "password": self.password,
                },
            )
            if r.status_code != 200:
                raise SystemExit(f"Не удалось войти как admin: {r.status_code} {r.text[:200]}")
            self._token, self._at = r.json()["access_token"], time.monotonic()
        return {"Authorization": f"Bearer {self._token}"}

    async def call(self, method: str, path: str, ok: Iterable[int] = (), **kw: Any) -> Any:
        async with self.sem:
            for attempt in range(5):
                try:
                    r = await self.http.request(method, path, headers=await self._headers(), **kw)
                except httpx.TransportError:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                if r.status_code >= 500:  # сервис ещё поднимается
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                break
        if r.status_code >= 400 and r.status_code not in ok:
            raise SystemExit(f"{method} {path} → {r.status_code}: {r.text[:400]}")
        return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else None

    async def get(self, path: str, **params: Any) -> Any:
        return await self.call("GET", path, params=params)

    async def post(self, path: str, body: Any, **kw: Any) -> Any:
        return await self.call("POST", path, json=body, **kw)


# --- структура ---------------------------------------------------------------------------------


@dataclass
class UnitPlan:
    name: str
    type_code: str
    kind: str  # academy / faculty / kafedra / course / group
    sort_order: int = 0
    faculty: int | None = None
    course: int | None = None
    children: list["UnitPlan"] = field(default_factory=list)
    id: str = ""


def plan_tree(root_name: str) -> UnitPlan:
    rng = random.Random(f"{SEED}:groups")
    root = UnitPlan(root_name, "academy", "academy")
    for f in FACULTIES:
        fac = UnitPlan(f"{f} Факультет", "faculty", "faculty", 0, faculty=f)
        for k in FACULTY_KAFEDRAS:
            fac.children.append(UnitPlan(f"{f}{k} Кафедра", "kafedra", "kafedra", 0, faculty=f))
        for c in COURSES:
            course = UnitPlan(f"{f}{c} Курс", "kurs", "course", 1, faculty=f, course=c)
            for g in range(1, rng.randint(4, 6) + 1):
                course.children.append(
                    UnitPlan(f"{f}{c}{g} Группа", "group", "group", g, faculty=f, course=c)
                )
            fac.children.append(course)
        root.children.append(fac)
    for name in ACADEMY_KAFEDRAS:
        root.children.append(UnitPlan(name, "kafedra", "kafedra", 1))
    return root


def walk(u: UnitPlan) -> Iterable[UnitPlan]:
    yield u
    for c in u.children:
        yield from walk(c)


async def ensure_types(api: Api) -> dict[str, str]:
    existing = {t["code"]: t for t in await api.get("/api/org/unit-types")}
    for code, name, level, children in UNIT_TYPES:
        if code not in existing:
            body = {"code": code, "name": name, "level": level, "can_have_children": children}
            existing[code] = await api.post("/api/org/unit-types", body)
    return {code: t["id"] for code, t in existing.items()}


async def ensure_units(api: Api, root: UnitPlan, types: dict[str, str]) -> None:
    units = await api.get("/api/org/units", include_inactive="true")
    by_parent: dict[str | None, dict[str, dict[str, Any]]] = {}
    for u in units:
        by_parent.setdefault(u["parent_id"], {})[u["name"].strip().lower()] = u
    root.id = next(u["id"] for u in units if u["parent_id"] is None)
    created = fixed = 0

    async def visit(parent: UnitPlan) -> None:
        nonlocal created, fixed
        for child in parent.children:
            found = by_parent.get(parent.id, {}).get(child.name.lower())
            want_type = types[child.type_code]
            if found is None:
                found = await api.post(
                    "/api/org/units",
                    {
                        "parent_id": parent.id,
                        "name": child.name,
                        "unit_type_id": want_type,
                        "sort_order": child.sort_order,
                    },
                )
                created += 1
            elif found["unit_type_id"] != want_type:
                # Например, курс, по ошибке заведённый с типом «Кафедра»
                found = await api.call(
                    "PATCH",
                    f"/api/org/units/{found['id']}",
                    json={"version": found["version"], "unit_type_id": want_type},
                )
                fixed += 1
            child.id = found["id"]
            await visit(child)

    await visit(root)
    print(f"Подразделения: создано {created}, исправлен тип у {fixed}")


# --- справочники -------------------------------------------------------------------------------


@dataclass
class Refs:
    ranks: dict[str, str]
    positions: dict[str, str]
    categories: dict[str, str]
    reasons: dict[str, str]


async def ensure_refs(api: Api) -> Refs:
    ranks = {r["name"]: r for r in await api.get("/api/org/ranks")}
    orders = {r["order"] for r in ranks.values()}
    for name, short, order in RANKS:
        if name not in ranks and order not in orders:
            ranks[name] = await api.post(
                "/api/org/ranks", {"name": name, "short_name": short, "order": order}
            )
    positions = {p["name"]: p["id"] for p in await api.get("/api/personnel/positions")}
    for order, name in enumerate(POSITIONS):
        if name not in positions:
            body = {"name": name, "sort_order": order * 10}
            positions[name] = (await api.post("/api/personnel/positions", body))["id"]
    cats = {c["code"]: c["id"] for c in await api.get("/api/personnel/person-categories")}
    for code, name, order in CATEGORIES:
        if code not in cats:
            body = {"code": code, "name": name, "sort_order": order}
            cats[code] = (await api.post("/api/personnel/person-categories", body))["id"]
    attrs = {a["code"] for a in await api.get("/api/personnel/attribute-definitions")}
    for order, (code, name, vtype, options) in enumerate(ATTRIBUTES):
        if code not in attrs:
            body = {
                "code": code,
                "name": name,
                "value_type": vtype,
                "enum_options": options,
                "sort_order": order * 10,
            }
            await api.post("/api/personnel/attribute-definitions", body)
    reasons = {r["code"]: r["id"] for r in await api.get("/api/personnel/exemption-reasons")}
    print(f"Справочники: званий {len(ranks)}, должностей {len(positions)}, категорий {len(cats)}")
    return Refs({n: r["id"] for n, r in ranks.items()}, positions, cats, reasons)


# --- личный состав -----------------------------------------------------------------------------


@dataclass
class Person:
    unit: UnitPlan
    no: str
    rank: str | None
    position: str
    category: str
    attributes: dict[str, Any]
    last: str = ""
    first: str = ""
    middle: str = ""
    id: str = ""


def plan_people(root: UnitPlan) -> list[Person]:
    people: list[Person] = []
    for u in walk(root):
        rng = random.Random(f"{SEED}:{u.name}")
        add = _adder(people, u, rng)
        if u.kind == "academy":
            add("Начальник академии", "Генерал-майор", "permanent")
            for _ in range(2):
                add("Заместитель начальника академии", "Полковник", "permanent")
            for _ in range(6):
                add("Офицер управления академии", rng.choice(["Подполковник", "Майор", "Капитан"]), "permanent")
        elif u.kind == "faculty":  # начальство факультета — прямо в факультете, без кафедр
            add("Начальник факультета", "Полковник", "permanent")
            for _ in range(2):
                add("Заместитель начальника факультета", "Подполковник", "permanent")
            for _ in range(3):
                add("Офицер управления факультета", rng.choice(["Майор", "Капитан", "Старший лейтенант"]), "permanent")
        elif u.kind == "course":
            add("Начальник курса", rng.choice(["Майор", "Капитан"]), "permanent")
            add("Курсовой офицер", rng.choice(["Капитан", "Старший лейтенант", "Лейтенант"]), "permanent")
            if u.faculty not in LISTENER_FACULTIES:
                add("Старшина курса", rng.choice(["Старшина", "Старший сержант"]), "cadet", course=u.course)
        elif u.kind == "kafedra":
            add("Начальник кафедры", "Полковник", "permanent")
            add("Заместитель начальника кафедры", "Подполковник", "permanent")
            for pos, n, ranks in [
                ("Профессор", rng.randint(1, 2), ["Полковник", None]),
                ("Доцент", rng.randint(2, 3), ["Подполковник", "Майор", None]),
                ("Старший преподаватель", rng.randint(2, 4), ["Майор", "Подполковник"]),
                ("Преподаватель", rng.randint(2, 4), ["Капитан", "Майор", "Старший лейтенант"]),
            ]:
                for _ in range(n):
                    rank = rng.choice(ranks)
                    add(pos, rank, "permanent" if rank else "civil")
            add("Инженер кафедры", None, "civil")
            if rng.random() < 0.6:
                add("Лаборант", None, "civil")
        elif u.kind == "group":
            if u.faculty in LISTENER_FACULTIES:
                for _ in range(rng.randint(12, 16)):
                    rank = rng.choice(["Лейтенант", "Старший лейтенант", "Капитан", "Майор"])
                    add("Слушатель", rank, "listener", course=u.course)
            else:
                size = rng.randint(18, 25)
                add("Заместитель командира взвода", rng.choice(["Сержант", "Старший сержант"]), "cadet", course=u.course)
                for _ in range(rng.choice([2, 3])):
                    add("Командир отделения", "Младший сержант", "cadet", course=u.course)
                while sum(1 for p in people if p.unit is u) < size:
                    rank = "Ефрейтор" if rng.random() < 0.2 else "Рядовой"
                    add("Курсант", rank, "cadet", course=u.course)
    return people


def _code(u: UnitPlan) -> str:
    digits = "".join(ch for ch in u.name if ch.isdigit())
    prefix = {"academy": "А", "faculty": "Ф", "kafedra": "КФ", "course": "К", "group": "Г"}[u.kind]
    return f"{prefix}{digits}"


def _adder(people: list[Person], u: UnitPlan, rng: random.Random) -> Any:
    def add(position: str, rank: str | None, category: str, course: int | None = None) -> None:
        n = sum(1 for p in people if p.unit is u) + 1
        female = 0.15 if category in ("permanent", "civil") else 0.06
        name = fio(rng, female_share=female)
        attrs: dict[str, Any] = {
            "gender": "Ж" if name.middle.endswith("на") else "М",
            "driver_license": rng.random() < (0.7 if category != "cadet" else 0.3),
            "phys_grade": rng.choices(["отлично", "хорошо", "удовлетворительно"], [3, 5, 2])[0],
        }
        if category in ("cadet", "listener"):
            attrs["course_no"] = course or 1
            # Допуск к оружию — со 2-го курса, у большинства
            attrs["weapon_access"] = (course or 1) >= 2 and rng.random() < 0.9
        elif category == "permanent":
            attrs["weapon_access"] = rng.random() < 0.8
        people.append(
            Person(u, f"ДЕМО-{_code(u)}-{n:02d}", rank, position, category, attrs, name.last, name.first, name.middle)
        )

    return add


async def ensure_people(api: Api, people: list[Person], refs: Refs) -> list[Person]:
    existing: dict[str, str] = {}
    offset = 0
    while True:
        page = await api.get("/api/personnel/people", include_archived="true", limit=500, offset=offset)
        for p in page["items"]:
            if p.get("personal_no"):
                existing[p["personal_no"]] = p["id"]
        offset += len(page["items"])
        if offset >= page["total"] or not page["items"]:
            break
    created: list[Person] = []

    async def create(p: Person) -> None:
        body = {
            "unit_id": p.unit.id,
            "last_name": p.last,
            "first_name": p.first,
            "middle_name": p.middle,
            "rank_id": refs.ranks.get(p.rank) if p.rank else None,
            "position_id": refs.positions[p.position],
            "category_id": refs.categories[p.category],
            "personal_no": p.no,
            "attributes": p.attributes,
        }
        p.id = (await api.post("/api/personnel/people", body))["id"]
        created.append(p)

    todo = []
    for p in people:
        if p.no in existing:
            p.id = existing[p.no]
        else:
            todo.append(create(p))
    for i in range(0, len(todo), 400):
        await asyncio.gather(*todo[i : i + 400])
        print(f"  личный состав: {min(i + 400, len(todo))} из {len(todo)}")
    print(f"Личный состав: всего {len(people)}, создано {len(created)}")
    return created


# --- наряды ------------------------------------------------------------------------------------


def role(name: str, headcount: int = 1, **req: Any) -> dict[str, Any]:
    return {"name": name, "headcount": headcount, **req}


def plan_duties(root: UnitPlan, refs: Refs) -> list[tuple[UnitPlan, dict[str, Any]]]:
    cadet, listener, permanent = (refs.categories[c] for c in ("cadet", "listener", "permanent"))
    weapon = [{"code": "weapon_access", "op": "eq", "value": True}]
    duties: list[tuple[UnitPlan, dict[str, Any]]] = []

    def duty(owner: UnitPlan, name: str, start: str, minutes: int, rest: int, roles: list[Any]) -> None:
        duties.append(
            (owner, {"name": name, "start_time": start, "duration_minutes": minutes, "rest_hours": rest, "owner_unit_id": owner.id, "roles": roles})
        )

    first_faculty = next(u for u in root.children if u.kind == "faculty")
    duty(root, "Дежурный по академии", "08:00", 1440, 48, [
        role("Дежурный по академии", allowed_category_ids=[permanent], min_rank_order=RANK_ORDER["Капитан"], attribute_requirements=weapon),
        role("Помощник дежурного по академии", allowed_category_ids=[permanent], min_rank_order=RANK_ORDER["Лейтенант"]),
    ])
    duty(root, "Караул", "18:00", 1440, 48, [
        role("Начальник караула", allowed_category_ids=[cadet], min_rank_order=RANK_ORDER["Сержант"], attribute_requirements=weapon, load_weight=1.2),
        role("Разводящий", 2, allowed_category_ids=[cadet], min_rank_order=RANK_ORDER["Младший сержант"], attribute_requirements=weapon, load_weight=1.2),
        role("Часовой", 6, allowed_category_ids=[cadet], attribute_requirements=[*weapon, {"code": "course_no", "op": "gte", "value": 2}], load_weight=1.2),
    ])
    duty(root, "Наряд по КПП", "08:00", 1440, 24, [
        role("Дежурный по КПП", allowed_category_ids=[cadet], min_rank_order=RANK_ORDER["Сержант"]),
        # Пример закрепления роли за подразделением (ADR-0018): дневальных даёт 1-й факультет
        role("Дневальный по КПП", 2, allowed_category_ids=[cadet], assigned_unit_id=first_faculty.id),
    ])
    duty(root, "Наряд по столовой", "06:00", 1440, 24, [
        role("Дежурный по столовой", allowed_category_ids=[cadet], min_rank_order=RANK_ORDER["Младший сержант"]),
        role("Рабочий по столовой", 8, allowed_category_ids=[cadet], attribute_requirements=[{"code": "course_no", "op": "lte", "value": 2}], load_weight=0.8),
    ])
    for u in walk(root):
        students = listener if u.faculty in LISTENER_FACULTIES else cadet
        if u.kind == "faculty":
            duty(u, "Дежурный по факультету", "08:00", 1440, 48, [
                role("Дежурный по факультету", allowed_category_ids=[permanent], min_rank_order=RANK_ORDER["Старший лейтенант"]),
                role("Помощник дежурного по факультету", allowed_category_ids=[students], min_rank_order=RANK_ORDER["Сержант"] if students == cadet else None),
            ])
        elif u.kind == "course":
            duty(u, "Наряд по курсу", "19:00", 1440, 24, [
                role("Дежурный по курсу", allowed_category_ids=[students], min_rank_order=RANK_ORDER["Младший сержант"] if students == cadet else None),
                role("Дневальный по курсу", 2, allowed_category_ids=[students]),
            ])
        elif u.kind == "kafedra":
            # Локальный наряд: владелец — кафедра, в графиках факультета и академии его нет
            duty(u, "Дежурный по кафедре", "09:00", 540, 12, [
                role("Дежурный по кафедре", allowed_category_ids=[permanent, refs.categories["civil"]]),
            ])
    return duties


async def ensure_duties(api: Api, duties: list[tuple[UnitPlan, dict[str, Any]]]) -> list[dict[str, Any]]:
    have = await api.get("/api/scheduling/duty-types", include_inactive="true")
    by_key = {(d["owner_unit_id"], d["name"].strip().lower()): d for d in have}
    result, created = [], 0
    for owner, body in duties:
        found = by_key.get((owner.id, body["name"].lower()))
        if found is None:
            found = await api.post("/api/scheduling/duty-types", body)
            created += 1
        result.append(found)
    print(f"Наряды: всего {len(result)}, создано {created}")
    return result


# --- допуски и освобождения ----------------------------------------------------------------------


async def grant_clearances(api: Api, duties: list[dict[str, Any]], owners: list[UnitPlan], people: list[Person]) -> None:
    """Допуск получает ~70% людей поддерева владельца; неподходящих по требованиям роли
    (категория, звание, характеристики, закрепление) сервер пропускает сам."""
    granted = skipped = 0
    for duty, owner in zip(duties, owners, strict=True):
        subtree = {id(u) for u in walk(owner)}
        pool = [p for p in people if id(p.unit) in subtree]
        for r in duty["roles"]:
            rng = random.Random(f"{SEED}:clearance:{r['id']}")
            chosen = [p.id for p in pool if rng.random() < 0.7]
            for i in range(0, len(chosen), 1000):
                res = await api.post("/api/personnel/clearances/bulk", {"person_ids": chosen[i : i + 1000], "duty_role_ids": [r["id"]]})
                granted += int(res["done"])
                skipped += len(res["skipped"]) if isinstance(res["skipped"], list) else int(res["skipped"])
    print(f"Допуски: выдано {granted}, пропущено (не подходят по требованиям или уже есть) {skipped}")


async def add_exemptions(api: Api, people: list[Person], refs: Refs) -> None:
    rng = random.Random(f"{SEED}:exemptions")
    today = dt.date.today()
    kinds = [("illness", 3, 10), ("leave", 10, 30), ("trip", 3, 14), ("other", 1, 3)]
    count = 0
    for p in people:
        if rng.random() >= 0.06:
            continue
        code, lo, hi = rng.choices(kinds, [4, 3, 2, 1])[0]
        start = today + dt.timedelta(days=rng.randint(-10, 45))
        end = start + dt.timedelta(days=rng.randint(lo, hi) - 1)
        await api.post(
            "/api/personnel/exemptions/bulk",
            {"reason_id": refs.reasons[code], "date_from": start.isoformat(), "date_to": end.isoformat(), "person_ids": [p.id]},
        )
        count += 1
    print(f"Освобождения: {count}")


# --- операторы ---------------------------------------------------------------------------------


def plan_operators(root: UnitPlan) -> list[tuple[str, str, UnitPlan]]:
    ops: list[tuple[str, str, UnitPlan]] = [("nablyudatel", "viewer", root)]
    for u in walk(root):
        digits = "".join(ch for ch in u.name if ch.isdigit())
        if u.kind == "faculty":
            ops += [(f"fak{digits}_admin", "unit_admin", u), (f"fak{digits}_operator", "operator", u)]
        elif u.kind == "course":
            ops.append((f"kurs{digits}", "operator", u))
        elif u.kind == "kafedra":
            ops.append((f"kaf{digits}", "operator", u))
    return ops


async def ensure_operators(api: Api, root: UnitPlan, kc_admin: str, kc_password: str) -> None:
    existing: set[str] = set()
    offset = 0
    while True:
        page = await api.get("/api/auth-admin/operators", limit=200, offset=offset)
        existing |= {o["username"] for o in page["items"]}
        offset += len(page["items"])
        if offset >= page["total"] or not page["items"]:
            break
    new: list[str] = []
    for username, role_name, unit in plan_operators(root):
        if username in existing:
            continue
        name = fio(random.Random(f"{SEED}:op:{username}"), female_share=0.2)
        body = {"username": username, "last_name": name.last, "first_name": name.first, "role": role_name, "unit_id": unit.id}
        new.append((await api.post("/api/auth-admin/operators", body))["id"])
    if new:
        await set_demo_passwords(api.http, new, kc_admin, kc_password)
    print(f"Операторы: создано {len(new)} (пароль {DEMO_PASSWORD})")


async def set_demo_passwords(http: httpx.AsyncClient, user_ids: list[str], kc_admin: str, kc_password: str) -> None:
    """Постоянный демо-пароль вместо временного: через Keycloak Admin API (master realm)."""
    r = await http.post(
        "/auth/realms/master/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": "admin-cli", "username": kc_admin, "password": kc_password},
    )
    if r.status_code != 200:
        print("!! Не удалось войти в Keycloak: у новых операторов временные пароли (см. журнал создания)")
        return
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    base = "/auth/admin/realms/dutyflow/users"
    for uid in user_ids:
        await http.put(f"{base}/{uid}/reset-password", headers=h, json={"type": "password", "value": DEMO_PASSWORD, "temporary": False})
        user = (await http.get(f"{base}/{uid}", headers=h)).json()
        await http.put(f"{base}/{uid}", headers=h, json={**user, "requiredActions": []})


# --- запуск ------------------------------------------------------------------------------------


async def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    base = os.environ.get("DEMO_BASE_URL", "http://gateway")
    api = Api(base, os.environ["DUTYFLOW_ADMIN_PASSWORD"])
    started = time.monotonic()
    try:
        me = await api.get("/api/org/me")
        root = plan_tree(me["unit"]["name"])
        types = await ensure_types(api)
        await ensure_units(api, root, types)
        refs = await ensure_refs(api)
        people = plan_people(root)
        created = await ensure_people(api, people, refs)
        duty_plan = plan_duties(root, refs)
        duties = await ensure_duties(api, duty_plan)
        await grant_clearances(api, duties, [o for o, _ in duty_plan], people)
        await add_exemptions(api, created, refs)
        await ensure_operators(api, root, os.environ.get("KEYCLOAK_ADMIN", ""), os.environ.get("KEYCLOAK_ADMIN_PASSWORD", ""))
    finally:
        await api.http.aclose()
    print(f"Готово за {time.monotonic() - started:.0f} с")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
