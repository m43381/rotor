"""Независимая проверка решения по снимку — простым перебором, без numpy и без кода движка.

Нужна тестам свойств: векторные проверки движка сверяются с «наивной» реализацией тех же
правил (ADR-0008, ADR-0009, open-questions №9, 27, 41). Возвращает список нарушений.
"""

import datetime as dt
from collections import defaultdict
from typing import Any

DAY = 1440


def _minutes(value: str) -> int:
    t = dt.time.fromisoformat(value)
    return t.hour * 60 + t.minute


def verify(snapshot: dict[str, Any], solution: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    roles = snapshot["roles"]
    cells = snapshot["cells"]
    cell_by_id = {c["id"]: (i, c) for i, c in enumerate(cells)}
    people = snapshot["people"]
    person_by_id = {p["id"]: i for i, p in enumerate(people)}
    kinds = [k for _, k in snapshot["days"]]
    month_start = snapshot["horizon"]["month_start"]
    month_end = len(kinds) - 1
    unit = snapshot["schedule"]["unit"]
    removed = set(solution.get("removed", []))

    def holiday(day: int) -> bool:
        return day < len(kinds) and kinds[day] in ("weekend", "holiday")

    # Все наряды людей после применения решения: (начало, конец, отдых, первые/последние сутки,
    # день, новый ли)
    duties: dict[int, list[tuple[int, int, int, int, int, int, bool]]] = defaultdict(list)
    per_cell: dict[int, int] = defaultdict(int)
    for a in snapshot["assignments"]:
        if a["id"] in removed:
            if not a["auto"] or a["pinned"] or a["override"]:
                errors.append(f"снято ручное или закреплённое назначение {a['id']}")
            continue
        start, end = a["t"]
        duties[a["p"]].append(
            (start, end, a["rest"] * 60, a["days"][0], a["days"][1], a["d"], False)
        )
        if a["cell"] is not None:
            per_cell[a["cell"]] += 1

    for new in solution.get("assignments", []):
        idx, cell = cell_by_id[new["cell"]]
        p = person_by_id[new["person"]]
        role = roles[cell["r"]]
        if cell["s"] != unit or cell["e"] != unit or not role["active"]:
            errors.append(f"ячейка {cell['id']} не закрывается подразделением графика")
        day = cell["d"]
        start = day * DAY + _minutes(role["start_time"])
        end = start + role["duration_minutes"]
        last = (end - 1) // DAY
        if not any(
            r == cell["r"] and (f is None or f <= day) and (t is None or t >= day)
            for r, f, t in people[p]["c"]
        ):
            errors.append(f"{new['person']}: нет действующего допуска, ячейка {cell['id']}")
        if any(f <= last and t >= day for f, t in people[p]["x"]):
            errors.append(f"{new['person']}: освобождён, ячейка {cell['id']}")
        duties[p].append((start, end, role["rest_hours"] * 60, day, last, day, True))
        per_cell[idx] += 1

    for idx, count in per_cell.items():
        if count > roles[cells[idx]["r"]]["headcount"]:
            errors.append(f"ячейка {cells[idx]['id']}: людей больше, чем нужно")

    for p, items in duties.items():
        items.sort()
        for i, a in enumerate(items):
            for b in items[i + 1 :]:
                if not (a[6] or b[6]):
                    continue  # оба старые — не ответственность движка
                if a[3] <= b[4] and b[3] <= a[4]:
                    errors.append(f"{people[p]['id']}: два наряда в одни сутки")
                elif b[0] - a[1] < a[2]:
                    errors.append(f"{people[p]['id']}: не соблюдён отдых")
        limit = people[p].get("limit")
        if limit and any(d[6] for d in items):
            in_month = [d for d in items if month_start <= d[5] <= month_end]
            total, hol = limit
            if total is not None and len(in_month) > total:
                errors.append(f"{people[p]['id']}: превышен месячный лимит")
            if hol is not None and sum(holiday(d[5]) for d in in_month) > hol:
                errors.append(f"{people[p]['id']}: превышен лимит в выходные")
    return errors


def verify_units(
    snapshot: dict[str, Any], solution: dict[str, Any], include_self: bool = False
) -> list[str]:
    errors: list[str] = []
    unit = snapshot["schedule"]["unit"]
    units = snapshot["units"]
    allowed = {units[i]["id"] for i, u in enumerate(units) if u["parent"] == unit}
    if include_self:
        allowed.add(units[unit]["id"])
    cells = {c["id"]: c for c in snapshot["cells"]}
    seen = set()
    for d in solution.get("delegations", []):
        cell = cells[d["cell"]]
        if d["cell"] in seen:
            errors.append(f"ячейка {d['cell']} распределена дважды")
        seen.add(d["cell"])
        if cell["s"] != unit or cell["e"] != unit or cell["pinned"]:
            errors.append(f"ячейка {d['cell']} не может распределяться")
        if d["unit"] not in allowed:
            errors.append(f"ячейка {d['cell']}: подразделение не прямое дочернее")
    return errors
