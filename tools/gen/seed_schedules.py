"""Демо-графики на следующий месяц через API scheduling (после seed_duties).

Каждый факультет создаёт график, а роль «Помощник дежурного по факультету» делегирует
курсам по очереди (день 1 — 1-му курсу, день 2 — 2-му …). 1-й курс факультета 1 принимает
входящие, остальные курсы оставляют их непринятыми — видно в таблице и при публикации.
На первые 10 дней в график факультета 1 и 1-го курса назначаются люди — первые пригодные
кандидаты без нарушений. Повторный запуск ничего не дублирует.

    just seed
"""

import datetime as dt
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.gen.seed_org import FACULTIES, check, read_env, token

COURSES_PER_FACULTY = 4
HELPER = "Помощник дежурного по факультету"


def next_month(today: dt.date) -> dt.date:
    return (today.replace(day=28) + dt.timedelta(days=5)).replace(day=1)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    env = read_env()
    month = next_month(dt.date.today())
    with httpx.Client(base_url=env.public_url, timeout=60.0) as http:
        bearer = token(http, "dutyflow", "dutyflow-cli", "admin", env.admin_password)
        h = {"Authorization": f"Bearer {bearer}"}

        def get(path: str, **params: Any) -> Any:
            return check(http.get(path, headers=h, params=params))

        def post(path: str, body: dict[str, Any]) -> Any:
            return check(http.post(path, headers=h, json=body))

        units = {u["name"]: u for u in get("/api/org/units")}
        created = 0
        for fi, faculty in enumerate(FACULTIES, start=1):
            f_id = units[faculty]["id"]
            if get("/api/scheduling/schedules", month=str(month), unit_id=f_id):
                continue
            schedule = post("/api/scheduling/schedules", {"unit_id": f_id, "month": str(month)})
            created += 1
            table = get(f"/api/scheduling/schedules/{schedule['id']}/table")
            row = next(r for r in table["rows"] if r["role_name"] == HELPER)
            courses = [units[f"{c} курс, факультет {fi}"]["id"] for c in range(1, 5)]
            by_course: dict[str, list[str]] = {c: [] for c in courses}
            for day, cell in enumerate(row["cells"]):
                if cell:
                    by_course[courses[day % COURSES_PER_FACULTY]].append(cell["id"])
            for course, cells in by_course.items():
                post(
                    f"/api/scheduling/schedules/{schedule['id']}/delegate",
                    {"cell_ids": cells, "executor_unit_id": course},
                )
            if fi == 1:
                first = get("/api/scheduling/schedules", month=str(month), unit_id=courses[0])[0]
                post(f"/api/scheduling/schedules/{first['id']}/accept", {})
        print(f"Графиков факультетов на {month:%m.%Y}: создано {created}")

        # Назначения: факультет 1 (свои роли) и его 1-й курс (принятые входящие)
        assigned = 0
        for unit_name in (FACULTIES[0], "1 курс, факультет 1"):
            [schedule] = get(
                "/api/scheduling/schedules", month=str(month), unit_id=units[unit_name]["id"]
            )
            table = get(f"/api/scheduling/schedules/{schedule['id']}/table")
            for row in table["rows"]:
                for cell in row["cells"][:10]:
                    if not cell or cell["state"] not in ("own", "incoming_active"):
                        continue
                    for _ in range(row["headcount"] - cell["filled"]):
                        data = get(f"/api/scheduling/day-plans/{cell['id']}/candidates")
                        clean = [c for c in data["candidates"] if not c["violations"]]
                        if not clean:
                            break
                        post(
                            f"/api/scheduling/day-plans/{cell['id']}/assignments",
                            {"person_id": clean[0]["person_id"]},
                        )
                        assigned += 1
        print(f"Назначено людей: {assigned}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
