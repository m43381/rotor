"""Демо-данные стенда: типы подразделений, звания, дерево и учётки операторов разных уровней.

Работает только через публичные API (org через шлюз, Keycloak Admin REST) — так же, как
работал бы оператор, без прямого доступа к БД. Повторный запуск ничего не дублирует.

    just seed        # после just up
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
DEMO_PASSWORD = "demo-password-1"  # noqa: S105 — только демо-учётки локального стенда

# Уровень задаёт допустимую вложенность: дочерний тип ниже родителя. «Кафедра» (2) встаёт
# и под факультет (1), и прямо под академию (0) — кафедры бывают вне факультетов (№31).
UNIT_TYPES = [
    ("faculty", "Факультет", 1),
    ("management", "Управление", 2),
    ("department", "Кафедра", 2),
    ("course", "Курс", 2),
    ("group", "Учебная группа", 3),
]
RANKS = [
    ("Рядовой", "ряд.", 10),
    ("Ефрейтор", "ефр.", 20),
    ("Младший сержант", "мл. с-т", 30),
    ("Сержант", "с-т", 40),
    ("Старший сержант", "ст. с-т", 50),
    ("Лейтенант", "л-т", 70),
    ("Старший лейтенант", "ст. л-т", 80),
    ("Капитан", "к-н", 90),
    ("Майор", "м-р", 100),
    ("Подполковник", "п/п-к", 110),
    ("Полковник", "п-к", 120),
]
FACULTIES = ["Факультет управления", "Инженерный факультет", "Факультет связи"]
# Кафедры факультетов (по две на факультет) и кафедры академии вне факультетов.
FACULTY_DEPARTMENTS = [
    ["Кафедра организации управления", "Кафедра тактики"],
    ["Кафедра эксплуатации техники", "Кафедра инженерного обеспечения"],
    ["Кафедра радиосвязи", "Кафедра автоматизированных систем"],
]
ACADEMY_DEPARTMENTS = ["Кафедра физической подготовки", "Кафедра иностранных языков"]
COURSES_PER_FACULTY = 4
GROUPS_PER_COURSE = 3


@dataclass
class Env:
    public_url: str
    admin_password: str
    kc_admin: str
    kc_admin_password: str


def read_env() -> Env:
    values: dict[str, str] = {}
    for line in (ROOT / "deploy" / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return Env(
        public_url=values["PUBLIC_URL"],
        admin_password=values["DUTYFLOW_ADMIN_PASSWORD"],
        kc_admin=values["KEYCLOAK_ADMIN"],
        kc_admin_password=values["KEYCLOAK_ADMIN_PASSWORD"],
    )


def token(client: httpx.Client, realm: str, client_id: str, user: str, password: str) -> str:
    r = client.post(
        f"/auth/realms/{realm}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": client_id,
            "username": user,
            "password": password,
        },
    )
    r.raise_for_status()
    return str(r.json()["access_token"])


def check(r: httpx.Response) -> Any:
    if r.is_error:
        raise SystemExit(f"{r.request.method} {r.request.url} → {r.status_code}: {r.text}")
    return r.json() if r.content else None


class OrgApi:
    def __init__(self, http: httpx.Client, bearer: str) -> None:
        self.http = http
        self.headers = {"Authorization": f"Bearer {bearer}"}

    def get(self, path: str) -> Any:
        return check(self.http.get(f"/api/org{path}", headers=self.headers))

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return check(self.http.post(f"/api/org{path}", json=body, headers=self.headers))


def ensure_types(api: OrgApi) -> dict[str, str]:
    existing = {t["code"]: t["id"] for t in api.get("/unit-types")}
    for code, name, level in UNIT_TYPES:
        if code not in existing:
            existing[code] = api.post("/unit-types", {"code": code, "name": name, "level": level})[
                "id"
            ]
    return existing


def ensure_ranks(api: OrgApi) -> None:
    existing = {r["order"] for r in api.get("/ranks")}
    for name, short, order in RANKS:
        if order not in existing:
            api.post("/ranks", {"name": name, "short_name": short, "order": order})


def ensure_tree(api: OrgApi, types: dict[str, str]) -> dict[str, str]:
    """Возвращает {название: id} всех демо-подразделений."""
    units = api.get("/units")
    by_parent_name: dict[tuple[str, str], str] = {
        (u["parent_id"], u["name"]): u["id"] for u in units
    }
    root = api.get("/me")["unit"]["id"]

    def ensure(parent: str, type_code: str, name: str, order: int) -> str:
        key = (parent, name)
        if key not in by_parent_name:
            by_parent_name[key] = api.post(
                "/units",
                {
                    "parent_id": parent,
                    "unit_type_id": types[type_code],
                    "name": name,
                    "sort_order": order,
                },
            )["id"]
        return by_parent_name[key]

    ids: dict[str, str] = {}
    for fi, faculty in enumerate(FACULTIES, start=1):
        f_id = ids[faculty] = ensure(root, "faculty", faculty, fi)
        management = f"Управление факультета {fi}"
        ids[management] = ensure(f_id, "management", management, 0)
        for di, department in enumerate(FACULTY_DEPARTMENTS[fi - 1], start=1):
            ids[department] = ensure(f_id, "department", department, 10 + di)
        for c in range(1, COURSES_PER_FACULTY + 1):
            course = f"{c} курс, факультет {fi}"
            c_id = ids[course] = ensure(f_id, "course", course, c)
            for g in range(1, GROUPS_PER_COURSE + 1):
                group = f"Группа {fi}{c}{g}"
                ids[group] = ensure(c_id, "group", group, g)
    for di, department in enumerate(ACADEMY_DEPARTMENTS, start=1):
        ids[department] = ensure(root, "department", department, 100 + di)
    return ids


def ensure_demo_users(http: httpx.Client, env: Env, units: dict[str, str]) -> list[str]:
    kc = token(http, "master", "admin-cli", env.kc_admin, env.kc_admin_password)
    h = {"Authorization": f"Bearer {kc}"}
    base = "/auth/admin/realms/dutyflow"
    roles = {r["name"]: r for r in check(http.get(f"{base}/roles", headers=h))}
    demo = [
        ("faculty_admin", "Иванов", "Пётр", "unit_admin", FACULTIES[0]),
        ("course_operator", "Петров", "Сергей", "operator", "1 курс, факультет 1"),
        ("faculty_viewer", "Сидорова", "Анна", "viewer", FACULTIES[1]),
        ("department_operator", "Кузнецов", "Андрей", "operator", ACADEMY_DEPARTMENTS[0]),
    ]
    created = []
    for username, last, first, role, unit_name in demo:
        found = check(
            http.get(f"{base}/users", params={"username": username, "exact": "true"}, headers=h)
        )
        if not found:
            check(
                http.post(
                    f"{base}/users",
                    headers=h,
                    json={
                        "username": username,
                        "enabled": True,
                        "firstName": first,
                        "lastName": last,
                        "attributes": {"unit_id": [units[unit_name]]},
                        "credentials": [
                            {"type": "password", "value": DEMO_PASSWORD, "temporary": False}
                        ],
                    },
                )
            )
            found = check(
                http.get(f"{base}/users", params={"username": username, "exact": "true"}, headers=h)
            )
        user_id = found[0]["id"]
        check(
            http.post(f"{base}/users/{user_id}/role-mappings/realm", headers=h, json=[roles[role]])
        )
        created.append(f"{username:20} {role:11} {unit_name}")
    return created


def main() -> int:
    if isinstance(sys.stdout, __import__("io").TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    env = read_env()
    with httpx.Client(base_url=env.public_url, timeout=30.0) as http:
        api = OrgApi(http, token(http, "dutyflow", "dutyflow-cli", "admin", env.admin_password))
        types = ensure_types(api)
        ensure_ranks(api)
        units = ensure_tree(api, types)
        users = ensure_demo_users(http, env, units)
    print(f"Подразделений в демо-дереве: {len(units) + 1}")
    print(f"Демо-учётки (пароль {DEMO_PASSWORD}):")
    for line in users:
        print("  " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
