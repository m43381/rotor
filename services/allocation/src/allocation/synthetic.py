"""Генератор синтетических снимков формата ADR-0013 — для тестов, бенчмарков и
экспериментального стенда фазы 5 (`docs/allocation-design.md`, «Экспериментальная часть»).

Детерминирован по seed. Подразделение графика — корень поддерева: дочерние подразделения
(«курсы»), у каждого — группы; люди распределены по группам. Роли — наряды разной
длительности (6 ч, сутки, трое суток), у людей — допуски к части ролей, освобождения,
у части — лимиты. История — назначения за прошлые 90 дней без проверки правил (фон нагрузки).
"""

import datetime as dt
import hashlib
import random
import uuid
from typing import Any

from pydantic_core import to_json

HISTORY_DAYS = 90
DAY = 1440


def _id(rng: random.Random) -> str:  # детерминированные id синтетики, не для безопасности
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def generate_snapshot(
    *,
    people: int = 300,
    children: int = 4,
    groups_per_child: int = 3,
    duty_types: int = 6,
    month: dt.date = dt.date(2026, 11, 1),
    clearance_share: float = 0.35,
    exemption_share: float = 0.12,
    limit_share: float = 0.2,
    history_fill: float = 0.6,
    delegate_share: float = 0.0,
    seed: int = 1,
) -> dict[str, Any]:
    rng = random.Random(seed)
    first = month - dt.timedelta(days=HISTORY_DAYS)
    next_month = (month.replace(day=28) + dt.timedelta(days=5)).replace(day=1)
    days = [first + dt.timedelta(days=i) for i in range((next_month - first).days)]
    holidays = {dt.date(month.year, 11, 4), dt.date(month.year, 1, 1)}
    kinds = [
        "holiday" if d in holidays else "weekend" if d.weekday() >= 5 else "workday" for d in days
    ]
    month_start = days.index(month)

    # --- подразделения -------------------------------------------------------------------
    units: list[dict[str, Any]] = [{"id": _id(rng), "parent": None, "name": "Факультет"}]
    leaves: list[int] = []
    for c in range(children):
        units.append({"id": _id(rng), "parent": 0, "name": f"{c + 1} курс"})
        child = len(units) - 1
        for gidx in range(groups_per_child):
            units.append({"id": _id(rng), "parent": child, "name": f"Группа {c + 1}{gidx + 1}"})
            leaves.append(len(units) - 1)

    # --- роли ------------------------------------------------------------------------------
    templates = [
        ("18:00:00", 1440, 48),
        ("08:00:00", 1440, 48),
        ("20:00:00", 360, 24),
        ("09:00:00", 4320, 72),
    ]
    roles: list[dict[str, Any]] = []
    for t in range(duty_types):
        start, duration, rest = templates[t % len(templates)]
        type_id = _id(rng)
        for k in range(1 + t % 3):
            roles.append(
                {
                    "id": _id(rng),
                    "duty_type_id": type_id,
                    "duty_type": f"Наряд {t + 1}",
                    "name": f"Роль {k + 1}",
                    "headcount": 1 + (k == 1),
                    "start_time": start,
                    "duration_minutes": duration,
                    "rest_hours": rest,
                    "load_weight": 1.0 if duration <= 1440 else 1.5,
                    "active": True,
                }
            )

    # --- люди --------------------------------------------------------------------------------
    persons: list[dict[str, Any]] = []
    for _ in range(people):
        clearances: list[list[int | None]] = []
        for r in range(len(roles)):
            if rng.random() < clearance_share:
                valid_from = None if rng.random() < 0.9 else month_start + rng.randint(0, 20)
                valid_to = None if rng.random() < 0.9 else month_start + rng.randint(10, 29)
                if valid_from is not None and valid_to is not None and valid_to < valid_from:
                    valid_from, valid_to = valid_to, valid_from
                clearances.append([r, valid_from, valid_to])
        exemptions = []
        if rng.random() < exemption_share:
            a = rng.randint(0, len(days) - 3)
            exemptions.append([a, min(len(days) - 1, a + rng.randint(2, 14))])
        limit = None
        if rng.random() < limit_share:
            limit = [rng.randint(2, 6), rng.choice([None, 1, 2])]
        persons.append(
            {
                "id": _id(rng),
                "u": rng.choice(leaves),
                "c": clearances,
                "x": exemptions,
                "limit": limit,
            }
        )

    # --- ячейки месяца: свои роли подразделения графика -------------------------------------
    cells: list[dict[str, Any]] = []
    for d in range(month_start, len(days)):
        for r in range(len(roles)):
            delegated = rng.random() < delegate_share
            cells.append(
                {
                    "id": _id(rng),
                    "d": d,
                    "r": r,
                    "s": 0,
                    "e": 1 + rng.randrange(children) * (groups_per_child + 1) if delegated else 0,
                    "origin": "own",
                    "status": "none",
                    "pinned": False,
                    "parent": None,
                }
            )

    # --- история: наряды прошлых дней (фон нагрузки) ---------------------------------------
    assignments: list[dict[str, Any]] = []
    for d in range(0, month_start):
        for r, role in enumerate(roles):
            if rng.random() > history_fill:
                continue
            p = rng.randrange(people)
            begin = d * DAY + int(role["start_time"][:2]) * 60
            finish = begin + int(role["duration_minutes"])
            occupied = (finish - 1) // DAY - d + 1
            assignments.append(
                {
                    "id": _id(rng),
                    "p": p,
                    "cell": None,
                    "d": d,
                    "r": r,
                    "dt": role["duty_type_id"],
                    "t": [begin, finish],
                    "rest": role["rest_hours"],
                    "days": [d, d + occupied - 1],
                    "load": occupied * role["load_weight"],
                    "pinned": False,
                    "auto": True,
                    "override": False,
                }
            )

    content: dict[str, Any] = {
        "snapshot_version": 1,
        "timezone": "Europe/Moscow",
        "schedule": {"id": _id(rng), "unit": 0, "month": month.isoformat(), "status": "draft"},
        "horizon": {
            "from": first.isoformat(),
            "to": days[-1].isoformat(),
            "month_start": month_start,
        },
        "days": [[d.isoformat(), k] for d, k in zip(days, kinds, strict=True)],
        "units": units,
        "roles": roles,
        "people": persons,
        "cells": cells,
        "assignments": assignments,
    }
    return {
        "snapshot_version": 1,
        "hash": hashlib.sha256(to_json(content)).hexdigest(),
        "created_at": "synthetic",
        **{k: v for k, v in content.items() if k != "snapshot_version"},
    }
