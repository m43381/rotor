"""Демо-личный состав стенда через API personnel (после `just seed-org`).

В каждую учебную группу — 20–25 курсантов, на курс — начальник курса и старшина,
на факультет — несколько офицеров постоянного состава. Часть людей получает освобождения.
Детерминирован по seed; повторный запуск не дублирует людей (проверка по личному номеру).

    just seed        # подразделения, затем люди
"""

import datetime as dt
import random
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.gen.names import fio
from tools.gen.seed_org import check, read_env, token, verify

SEED = 20260926
OFFICER = "Постоянный состав"
POSITIONS = [
    "Курсант",
    "Командир отделения",
    "Заместитель командира взвода",
    "Старшина курса",
    "Начальник курса",
    "Начальник факультета",
    "Заместитель начальника факультета",
    "Офицер управления",
    "Начальник кафедры",
    "Старший преподаватель",
    "Преподаватель",
]
# Офицеры — постоянный состав (open-questions №31): управление факультета, кафедры, курсы.
OFFICER_RANKS = ["Лейтенант", "Старший лейтенант", "Капитан", "Майор", "Подполковник"]


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

        existing_pos = {p["name"]: p["id"] for p in get("/api/personnel/positions")}
        for order, name in enumerate(POSITIONS):
            if name not in existing_pos:
                existing_pos[name] = post(
                    "/api/personnel/positions", {"name": name, "sort_order": order}
                )["id"]
        ranks = {r["name"]: r["id"] for r in get("/api/org/ranks")}
        reasons = [r["id"] for r in get("/api/personnel/exemption-reasons")]
        units = get("/api/org/units")
        types = {t["id"]: t["code"] for t in get("/api/org/unit-types")}
        taken: set[str] = set()
        offset = 0
        while True:
            page = get("/api/personnel/people", limit=500, offset=offset, include_archived="true")
            taken |= {p["personal_no"] for p in page["items"] if p["personal_no"]}
            offset += 500
            if offset >= page["total"]:
                break

        created = 0
        today = dt.date.today()

        def person(
            rng: random.Random,
            unit: dict[str, Any],
            seq: str,
            rank: str,
            position: str,
            category: str,
        ) -> None:
            nonlocal created
            personal_no = f"Д-{seq}"
            if personal_no in taken:
                return
            f = fio(rng)
            body = {
                "unit_id": unit["id"],
                "last_name": f.last,
                "first_name": f.first,
                "middle_name": f.middle,
                "rank_id": ranks.get(rank),
                "position_id": existing_pos[position],
                "personal_no": personal_no,
                "attributes": {"category": category},
            }
            p = post("/api/personnel/people", body)
            created += 1
            if rng.random() < 0.12:  # у части людей — освобождение в ближайшие два месяца
                start = today + dt.timedelta(days=rng.randint(0, 50))
                post(
                    f"/api/personnel/people/{p['id']}/exemptions",
                    {
                        "reason_id": rng.choice(reasons),
                        "date_from": start.isoformat(),
                        "date_to": (start + dt.timedelta(days=rng.randint(1, 14))).isoformat(),
                    },
                )

        for u in sorted(units, key=lambda x: x["path"]):
            # Свой генератор на подразделение: состав не зависит от того, кого пропустили
            # при повторном запуске, — поэтому seed идемпотентен.
            rng = random.Random(f"{SEED}-{u['path']}")
            code = types.get(u["unit_type_id"])
            key = u["path"].replace(".", "")
            if code == "group":
                for i in range(rng.randint(20, 25)):
                    position = (
                        "Командир отделения"
                        if i in (1, 2, 3)
                        else "Заместитель командира взвода"
                        if i == 0
                        else "Курсант"
                    )
                    rank = "Младший сержант" if i == 0 else "Ефрейтор" if i < 4 else "Рядовой"
                    person(rng, u, f"{key}-{i:02d}", rank, position, "Курсант")
            elif code == "course":
                person(rng, u, f"{key}-nk", "Майор", "Начальник курса", OFFICER)
                # Старшина курса — из курсантов (сержант), не офицер
                person(rng, u, f"{key}-st", "Старший сержант", "Старшина курса", "Курсант")
            elif code == "management":
                person(rng, u, f"{key}-nf", "Полковник", "Начальник факультета", OFFICER)
                person(
                    rng,
                    u,
                    f"{key}-zn",
                    "Подполковник",
                    "Заместитель начальника факультета",
                    OFFICER,
                )
                for i in range(3):
                    person(
                        rng,
                        u,
                        f"{key}-o{i}",
                        rng.choice(OFFICER_RANKS),
                        "Офицер управления",
                        OFFICER,
                    )
            elif code == "department":
                person(rng, u, f"{key}-nk", "Полковник", "Начальник кафедры", OFFICER)
                for i in range(rng.randint(4, 7)):
                    position = "Старший преподаватель" if i < 2 else "Преподаватель"
                    person(rng, u, f"{key}-t{i}", rng.choice(OFFICER_RANKS), position, OFFICER)
    print(f"Добавлено людей: {created}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
