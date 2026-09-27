"""Распределение ячеек по прямым дочерним подразделениям (уровень 0 — «кому делегировать»).

Фаза 4 (open-questions №40): квота подразделения по каждой роли — пропорционально его
ёмкости (сколько его людей могут закрыть роль в эти дни) с поправкой на прошлую нагрузку
(«долг»), метод наибольшего остатка (Гамильтона). Затем жадная расстановка по дням в порядке
MRV. Точные методы — Сент-Лагю и min-cost flow — фаза 5.
"""

from typing import Any

import numpy as np

from allocation.engine.config import EngineConfig
from allocation.engine.feasibility import static_candidates
from allocation.engine.metrics import fairness
from allocation.engine.people import Timer, _date
from allocation.engine.problem import Cell, Problem
from allocation.engine.state import PeopleState


def _groups(problem: Problem, include_self: bool) -> tuple[list[int], np.ndarray]:
    """Прямые дочерние подразделения графика (и само оно, если можно оставить себе) и для
    каждого человека — номер группы, в чьё поддерево он входит (-1 — ни в одно)."""
    u = problem.schedule_unit
    children = [i for i, parent in enumerate(problem.unit_parent) if parent == u]
    groups = [*children, u] if include_self else children
    top: list[int] = []
    for i in range(len(problem.unit_ids)):
        node = i
        while (
            node != u and problem.unit_parent[node] is not None and problem.unit_parent[node] != u
        ):
            node = int(problem.unit_parent[node])  # type: ignore[arg-type]
        top.append(node)
    position = {g: k for k, g in enumerate(groups)}
    person_group = np.array(
        [position.get(top[pu], -1) if pu >= 0 else -1 for pu in problem.person_unit],
        dtype=np.int32,
    )
    return groups, person_group


def _hamilton(total: int, weights: np.ndarray, tiebreak: np.ndarray) -> np.ndarray:
    """Метод наибольшего остатка: целые квоты, пропорциональные весам, в сумме `total`."""
    if total == 0 or weights.sum() <= 0:
        return np.zeros(len(weights), dtype=np.int64)
    exact = total * weights / weights.sum()
    quota = np.floor(exact).astype(np.int64)
    rest = int(total - quota.sum())
    order = np.lexsort((tiebreak, -(exact - quota)))
    quota[order[:rest]] += 1
    result: np.ndarray = quota
    return result


def solve_units(problem: Problem, config: EngineConfig, seed: int) -> dict[str, Any]:
    timer = Timer()
    rng = np.random.default_rng(seed)
    groups, person_group = _groups(problem, config.include_self)
    g = len(groups)
    tiebreak = rng.permutation(max(g, 1)).astype(np.int64)
    u = problem.schedule_unit
    scope = {str(c) for c in config.cell_ids} if config.cell_ids else None
    occupied = {e.cell for e in problem.existing if e.cell is not None}
    targets: list[Cell] = [
        c
        for c in problem.cells
        if c.schedule_unit == u
        and c.executor == u
        and not c.pinned
        and c.index not in occupied
        and problem.roles[c.role].active
        and problem.month_start <= c.day <= problem.month_end
        and (scope is None or c.id in scope)
    ]
    state = PeopleState(problem, config.half_life_days, config.holiday_weight)
    for e in problem.existing:
        state.add(
            e.person,
            day=e.day,
            start=e.start,
            end=e.end,
            rest=e.rest,
            first_day=e.first_day,
            last_day=e.last_day,
            type_index=e.type_index,
            load=e.load,
        )
    timer.lap("level0")

    # --- уровень 1–2: ёмкость подразделений по ячейкам ----------------------------------
    in_scope = problem.person_unit >= 0
    capacity: dict[int, np.ndarray] = {}
    for c in targets:
        role = problem.roles[c.role]
        sc = static_candidates(problem, c, in_scope)
        people = sc.people
        ok = state.free(people, c.day, c.last_day) & state.rested(people, c.start, c.end, role.rest)
        ok &= state.within_limits(people, c.day)
        member = person_group[people[ok]]
        capacity[c.index] = np.bincount(member[member >= 0], minlength=g) if g else np.zeros(0)
    timer.lap("level1")
    deficits = []
    for c in targets:
        role = problem.roles[c.role]
        if not g or capacity[c.index].max(initial=0) < role.headcount:
            deficits.append(
                {
                    "cell": c.id,
                    "day": c.day,
                    "role": role.id,
                    "need": role.headcount,
                    "capacity": int(capacity[c.index].max(initial=0)) if g else 0,
                    "message": (
                        f"{_date(problem, c.day)}: роль «{role.name}» — ни одно подразделение "
                        f"не может выставить {role.headcount} чел."
                    ),
                }
            )

    # --- квоты по ролям: ёмкость × поправка на долг (№40) --------------------------------
    history = (
        state.load[:, : problem.month_start]
        @ state.kernel(problem.month_start)[: problem.month_start]
    )
    per_capita = np.zeros(g)
    for k in range(g):
        members = person_group == k
        if members.any():
            per_capita[k] = history[members].mean()
    mean = per_capita[per_capita > 0].mean() if (per_capita > 0).any() else 0.0
    lam = config.unit_weights.debt_lambda
    debt = np.clip(1 + lam * (mean - per_capita) / mean, 0.5, 1.5) if mean > 0 else np.ones(g)
    quota: dict[int, np.ndarray] = {}
    for r in {c.role for c in targets}:
        cells_r = [c for c in targets if c.role == r]
        # «Масса» ёмкости: сколько людей подразделения могут закрыть роль, по всем ячейкам
        mass = sum(capacity[c.index].astype(np.float64) for c in cells_r)
        quota[r] = _hamilton(len(cells_r), np.asarray(mass) * debt, tiebreak[:g])
    timer.lap("level2")

    # --- уровень 3–4: жадная расстановка в порядке MRV ----------------------------------
    w = config.unit_weights
    width = problem.width
    taken = np.zeros((g, width), dtype=np.int64)  # людей, отданных подразделению в эти сутки
    given = {r: np.zeros(g, dtype=np.int64) for r in quota}
    order = sorted(
        targets,
        key=lambda c: (
            int((capacity[c.index] >= problem.roles[c.role].headcount).sum()) if g else 0,
            c.day,
            c.role,
            c.index,
        ),
    )
    delegations: list[dict[str, Any]] = []
    unfilled: list[dict[str, Any]] = []
    for c in order:
        role = problem.roles[c.role]
        if not g:
            break
        days = slice(c.day, min(width, c.last_day + 1))
        free_cap = capacity[c.index] - taken[:, days].max(axis=1)
        ok = free_cap >= role.headcount
        if not ok.any():
            unfilled.append(
                {
                    "cell": c.id,
                    "missing": 1,
                    "message": f"{_date(problem, c.day)}: роль «{role.name}» — некому передать",
                }
            )
            continue
        cand = np.flatnonzero(ok)
        # Квота соблюдается, пока есть подразделения, не выбравшие её; иначе — сверх квоты
        under = cand[given[c.role][cand] < quota[c.role][cand]]
        if len(under):
            cand = under
        q = quota[c.role][cand]
        feats = {
            "quota": (given[c.role][cand] + 1) / np.maximum(q, 0.5),
            "same_day": taken[cand, c.day].astype(np.float64),
            "capacity": free_cap[cand] / max(1, int(free_cap.max())),
        }
        cost = (
            w.quota * feats["quota"]
            + w.same_day * feats["same_day"]
            - w.capacity * feats["capacity"]
        )
        ranked = np.lexsort((tiebreak[cand], cost))[: config.alternatives + 1]

        def describe(
            i: int, cand: Any = cand, cost: Any = cost, feats: Any = feats
        ) -> dict[str, Any]:
            return {
                "unit": problem.unit_ids[groups[int(cand[i])]],
                "cost": round(float(cost[i]), 6),
                "features": {k: round(float(v[i]), 6) for k, v in feats.items()},
            }

        best = int(cand[ranked[0]])
        delegations.append(
            {
                "cell": c.id,
                **describe(int(ranked[0])),
                "keep": groups[best] == u,
                "rank": 1,
                "candidates": len(cand),
                "alternatives": [describe(int(i)) for i in ranked[1:]],
                "capacity": {
                    problem.unit_ids[groups[k]]: int(capacity[c.index][k]) for k in range(g)
                },
            }
        )
        taken[best, days] += role.headcount
        given[c.role][best] += 1
    timer.lap("level4")

    # Справедливость между подразделениями: доля отданных ячеек к их ёмкости
    total_given = sum(given.values()) if given else np.zeros(g)
    mass_total = (
        sum(capacity[c.index].astype(np.float64) for c in targets) if targets else np.zeros(g)
    )
    share = np.where(
        np.asarray(mass_total) > 0, np.asarray(total_given) / np.maximum(mass_total, 1), 0.0
    )
    return {
        "kind": "units",
        "assignments": [],
        "removed": [],
        "delegations": delegations,
        "unfilled": unfilled,
        "deficits": deficits,
        "metrics": {
            "cells": len(targets),
            "places": len(targets),
            "filled": len(delegations),
            "shortage": len(targets) - len(delegations),
            "upper_bound": None,
            "quota": {
                problem.roles[r].id: {problem.unit_ids[groups[k]]: int(q[k]) for k in range(g)}
                for r, q in quota.items()
            },
            "fairness": fairness(share),
            "timings_ms": timer.ms,
        },
    }
