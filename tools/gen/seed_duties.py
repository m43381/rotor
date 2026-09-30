"""Демо-наряды и допуски стенда через API scheduling и personnel (после seed_org и seed_people).

Наряды разных уровней и длительности (ADR-0008), состав по ролям с требованиями (ADR-0009),
категориями личного состава и закреплением ролей (ADR-0018), весом нагрузки у роли
(ADR-0019):
- академия: дежурный по академии (офицеры) и вечерний патруль на 6 часов;
- факультет: наряд по факультету (дежурный — офицер, помощник — курсант-сержант
  4 курса: роль закреплена за курсом и уходит ему автоматически);
- курс: суточный наряд (дежурный — командир отделения или замкомвзвода, дневальные).

Допуски выдаются массово тем, кто проходит требования, плюс один демонстрационный допуск
«вопреки требованиям» — он виден в отчёте о несоответствиях. Повторный запуск ничего
не дублирует.

    just seed
"""

import sys
import time
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.gen.seed_org import FACULTIES, check, read_env, token, verify

COURSES_PER_FACULTY = 4


def role(name: str, headcount: int = 1, **req: Any) -> dict[str, Any]:
    return {"name": name, "headcount": headcount, "attribute_requirements": [], **req}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    env = read_env()
    with httpx.Client(base_url=env.public_url, timeout=60.0, verify=verify()) as http:
        bearer = token(http, "dutyflow", "dutyflow-cli", "admin", env.admin_password)
        h = {"Authorization": f"Bearer {bearer}"}

        def get(path: str, **params: Any) -> Any:
            return check(http.get(path, headers=h, params=params))

        def post(path: str, body: dict[str, Any]) -> Any:
            return check(http.post(path, headers=h, json=body))

        units = {u["name"]: u for u in get("/api/org/units")}
        root = get("/api/org/me")["unit"]["id"]
        ranks = {r["name"]: r["order"] for r in get("/api/org/ranks")}
        positions = {p["name"]: p["id"] for p in get("/api/personnel/positions")}
        categories = {c["name"]: c["id"] for c in get("/api/personnel/person-categories")}
        officer = [categories["Постоянный состав"]]
        cadet = [categories["Курсант"]]
        existing = {
            (t["owner_unit_id"], t["name"])
            for t in get("/api/scheduling/duty-types", include_inactive="true")
        }
        created = 0

        def duty(
            owner: str, name: str, start: str, hours: int, roles: list[dict[str, Any]], **extra: Any
        ) -> None:
            nonlocal created
            if (owner, name) in existing:
                return
            post(
                "/api/scheduling/duty-types",
                {
                    "name": name,
                    "owner_unit_id": owner,
                    "start_time": start,
                    "duration_minutes": hours * 60,
                    "roles": roles,
                    **extra,
                },
            )
            created += 1

        duty(
            root,
            "Дежурство по академии",
            "08:00",
            24,
            [
                role(
                    "Дежурный по академии",
                    load_weight=1.5,
                    min_rank_order=ranks["Капитан"],
                    allowed_category_ids=officer,
                ),
                role(
                    "Помощник дежурного по академии",
                    load_weight=1.25,
                    min_rank_order=ranks["Лейтенант"],
                    allowed_category_ids=officer,
                ),
            ],
            short_name="ДпА",
        )
        duty(
            root,
            "Патруль по городку",
            "20:00",
            6,
            [
                role("Старший патруля", allowed_category_ids=officer, load_weight=0.6),
                role("Патрульный", 2, allowed_category_ids=cadet, load_weight=0.5),
            ],
            rest_hours=24,
        )
        for fi, faculty in enumerate(FACULTIES, start=1):
            f_id = units[faculty]["id"]
            duty(
                f_id,
                "Наряд по факультету",
                "18:00",
                24,
                [
                    role("Дежурный по факультету", allowed_category_ids=officer, load_weight=1.25),
                    role(
                        "Помощник дежурного по факультету",
                        min_rank_order=ranks["Младший сержант"],
                        allowed_category_ids=cadet,
                        assigned_unit_id=units[f"{COURSES_PER_FACULTY} курс, факультет {fi}"]["id"],
                    ),
                ],
                short_name="НпФ",
            )
            for c in range(1, COURSES_PER_FACULTY + 1):
                course = units[f"{c} курс, факультет {fi}"]["id"]
                duty(
                    course,
                    "Суточный наряд по курсу",
                    "18:00",
                    24,
                    [
                        role(
                            "Дежурный по курсу",
                            allowed_position_ids=[
                                positions["Командир отделения"],
                                positions["Заместитель командира взвода"],
                            ],
                            allowed_category_ids=cadet,
                        ),
                        role("Дневальный", 2, allowed_category_ids=cadet, load_weight=0.8),
                    ],
                    short_name="СН",
                )
        print(f"Добавлено нарядов: {created}")

        # Закрепление помощника дежурного по факультету за старшим курсом (ADR-0018) — и на
        # стендах, где наряд был создан раньше: роль обновляется, если закрепления ещё нет.
        pinned = 0
        for t in get("/api/scheduling/duty-types"):
            if t["name"] != "Наряд по факультету" or not t["can_edit"]:
                continue
            owner = t["owner_unit_id"]
            num = next((i for i, f in enumerate(FACULTIES, 1) if units[f]["id"] == owner), None)
            senior = units.get(f"{COURSES_PER_FACULTY} курс, факультет {num}") if num else None
            for r in t["roles"]:
                helper = r["name"] == "Помощник дежурного по факультету"
                if not helper or r["assigned_unit_id"] or not senior:
                    continue
                keys = (
                    "name", "code", "headcount", "load_weight", "sort_order", "min_rank_order",
                    "allowed_position_ids", "attribute_requirements", "allowed_category_ids",
                    "is_active", "version",
                )  # fmt: skip
                body = {k: r[k] for k in keys} | {"assigned_unit_id": senior["id"]}
                check(http.put(f"/api/scheduling/duty-roles/{r['id']}", headers=h, json=body))
                pinned += 1
        if pinned:
            print(f"Закреплено ролей за курсами: {pinned}")

        # Требования ролей доходят до personnel событиями — ждём, пока появятся все роли.
        all_types = get("/api/scheduling/duty-types")
        role_ids = [r["id"] for t in all_types for r in t["roles"] if r["is_active"]]
        for _ in range(60):
            known = {r["duty_role_id"] for r in get("/api/personnel/clearance-roles")}
            if set(role_ids) <= known:
                break
            time.sleep(1)
        else:
            raise SystemExit("personnel не получил роли нарядов за 60 с — проверьте consumer")

        # Допуски: по подразделениям верхнего уровня. Кто не проходит требования роли или
        # к кому наряд не относится, пропускается сервисом — это и есть нужное поведение.
        granted = 0
        for top in [
            *FACULTIES,
            *(u for u in units if u.startswith("Кафедра") and units[u]["parent_id"] == root),
        ]:
            people: list[str] = []
            offset = 0
            while True:
                page = get(
                    "/api/personnel/people", unit_id=units[top]["id"], limit=500, offset=offset
                )
                people += [p["id"] for p in page["items"]]
                offset += 500
                if offset >= page["total"]:
                    break
            for i in range(0, len(people), 1000):
                r = post(
                    "/api/personnel/clearances/bulk",
                    {"person_ids": people[i : i + 1000], "duty_role_ids": role_ids},
                )
                granted += r["done"]
        print(f"Выдано допусков: {granted}")

        # Один допуск вопреки требованиям — для отчёта о несоответствиях: курсант без
        # сержантской должности назначен дежурным по курсу на время отпуска командира.
        course = units["1 курс, факультет 1"]["id"]
        duty_role = next(
            r["id"]
            for t in all_types
            if t["owner_unit_id"] == course
            for r in t["roles"]
            if r["name"] == "Дежурный по курсу"
        )
        cadets = get(
            "/api/personnel/people",
            unit_id=course,
            position_id=positions["Курсант"],
            limit=1,
        )["items"]
        if cadets:
            r = http.post(
                f"/api/personnel/people/{cadets[0]['id']}/clearances",
                headers=h,
                json={
                    "duty_role_id": duty_role,
                    "confirm_override": True,
                    "override_comment": "Временно, на период отпуска командира отделения",
                },
            )
            if r.status_code not in (201, 409):
                check(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
