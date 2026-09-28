"""Демо-наряды и допуски стенда через API scheduling и personnel (после seed_org и seed_people).

Наряды разных уровней и длительности (ADR-0008), состав по ролям с требованиями (ADR-0009):
- академия: дежурный по академии (офицеры) и вечерний патруль на 6 часов;
- факультет: наряд по факультету (дежурный — офицер, помощник — курсант-сержант);
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

OFFICER = {"code": "category", "op": "eq", "value": "Постоянный состав"}
CADET = {"code": "category", "op": "eq", "value": "Курсант"}
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
                    min_rank_order=ranks["Капитан"],
                    attribute_requirements=[OFFICER],
                ),
                role(
                    "Помощник дежурного по академии",
                    min_rank_order=ranks["Лейтенант"],
                    attribute_requirements=[OFFICER],
                ),
            ],
            short_name="ДпА",
            load_weight=1.5,
        )
        duty(
            root,
            "Патруль по городку",
            "20:00",
            6,
            [
                role("Старший патруля", attribute_requirements=[OFFICER]),
                role("Патрульный", 2, attribute_requirements=[CADET]),
            ],
            rest_hours=24,
            load_weight=0.5,
        )
        for fi, faculty in enumerate(FACULTIES, start=1):
            f_id = units[faculty]["id"]
            duty(
                f_id,
                "Наряд по факультету",
                "18:00",
                24,
                [
                    role("Дежурный по факультету", attribute_requirements=[OFFICER]),
                    role(
                        "Помощник дежурного по факультету",
                        min_rank_order=ranks["Младший сержант"],
                        attribute_requirements=[CADET],
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
                            attribute_requirements=[CADET],
                        ),
                        role("Дневальный", 2, attribute_requirements=[CADET]),
                    ],
                    short_name="СН",
                )
        print(f"Добавлено нарядов: {created}")

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
