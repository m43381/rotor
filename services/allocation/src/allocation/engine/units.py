"""Распределение ячеек по прямым дочерним подразделениям (уровень 0 — «кому делегировать»).

Фаза 4 (open-questions №40): квота подразделения по каждой роли — пропорционально его
ёмкости (сколько его людей могут закрыть роль в эти дни) с поправкой на прошлую нагрузку
(«долг»), метод наибольшего остатка (Гамильтона). Затем жадная расстановка по дням в порядке
MRV. Точные методы — Сент-Лагю и min-cost flow — фаза 5.

Ёмкость (фаза 5c, по итогам эксперимента): передавая ячейку, движок резервирует под неё
конкретных людей подразделения — «свидетелей» того, что его люди могут её закрыть, — в общем
состоянии с отдыхом, многосуточностью и лимитами. Ёмкость следующих ячеек считается по этому
состоянию. Прежняя оценка «допущенные к роли минус все, кого подразделение уже отдало в эти
сутки» вычитала и людей других ролей и теряла до 5 % мест, которые подразделения могли бы
закрыть (`docs/experiments.md`). Свидетели — не назначение: людей потом выбирает само
подразделение, но полное закрытие переданного ему заведомо возможно.
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


def _sainte_lague(total: int, weights: np.ndarray, tiebreak: np.ndarray) -> np.ndarray:
    """Метод Сент-Лагю (наибольшее частное с делителями 1, 3, 5, …): без «парадокса
    Алабамы» и без систематического перекоса в пользу крупных — поэтому предсказуем."""
    seats = np.zeros(len(weights), dtype=np.int64)
    if total == 0 or weights.sum() <= 0:
        return seats
    for _ in range(total):
        quotient = weights / (2 * seats + 1)
        seats[np.lexsort((tiebreak, -quotient))[0]] += 1
    return seats


def _place_by_flow(
    problem: Problem,
    targets: list[Cell],
    quota: dict[int, np.ndarray],
    free_capacity: Any,
    taken: np.ndarray,
    w: Any,
    place: Any,
    g: int,
) -> dict[str, Any]:
    """Расстановка по дням min-cost flow (OR-Tools): исток → подразделение (квота роли) →
    ячейка (есть ёмкость) → сток. Точный оптимум транспортной задачи по стоимости: занятость
    подразделения в эти сутки и запас людей. Роли решаются по очереди, чтобы учитывать, кого
    подразделение уже отдало в эти сутки. Недопустимое после применения и то, что не влезло
    в квоты, добирает жадный проход."""
    from ortools.graph.python import min_cost_flow

    leftovers: list[Cell] = []
    flows = 0
    for r in sorted(quota):
        cells_r = sorted((c for c in targets if c.role == r), key=lambda c: (c.day, c.index))
        head = problem.roles[r].headcount
        net = min_cost_flow.SimpleMinCostFlow()
        sink = 1 + g + len(cells_r)
        for k in range(g):
            if quota[r][k] > 0:
                net.add_arc_with_capacity_and_unit_cost(0, 1 + k, int(quota[r][k]), 0)
        for n, c in enumerate(cells_r):
            node = 1 + g + n
            free = free_capacity(c)
            top = max(1, int(free.max(initial=0)))
            for k in range(g):
                if free[k] >= head:
                    cost = w.same_day * taken[k, c.day] - w.capacity * free[k] / top
                    net.add_arc_with_capacity_and_unit_cost(
                        1 + k, node, 1, round(100 * (cost + 10))
                    )
            net.add_arc_with_capacity_and_unit_cost(node, sink, 1, 0)
        chosen: dict[int, int] = {}
        if net.num_arcs() and net.solve_max_flow_with_min_cost() == net.OPTIMAL:
            flows += 1
            for arc in range(net.num_arcs()):
                tail, head_node = net.tail(arc), net.head(arc)
                if net.flow(arc) > 0 and 1 <= tail <= g and head_node > g:
                    chosen[head_node - 1 - g] = tail - 1
        for n, c in enumerate(cells_r):
            if n in chosen and place(c, chosen[n]):
                continue
            leftovers.append(c)
    for c in sorted(leftovers, key=lambda c: (c.day, c.index)):
        place(c)
    return {"optimal": False, "flow_roles": flows, "greedy_leftovers": len(leftovers)}


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
    in_scope = person_group >= 0
    static: dict[int, np.ndarray] = {
        c.index: static_candidates(problem, c, in_scope).people for c in targets
    }

    def feasible(c: Cell) -> np.ndarray:
        """Люди, которые могут закрыть ячейку при текущем состоянии (с резервами)."""
        people = static[c.index]
        role = problem.roles[c.role]
        ok = state.free(people, c.day, c.last_day) & state.rested(people, c.start, c.end, role.rest)
        ok &= state.within_limits(people, c.day)
        result: np.ndarray = people[ok]
        return result

    def free_capacity(c: Cell, people: np.ndarray | None = None) -> np.ndarray:
        member = person_group[feasible(c) if people is None else people]
        return np.bincount(member, minlength=g) if g else np.zeros(0, dtype=np.int64)

    capacity = {c.index: free_capacity(c) for c in targets}
    # Гибкость человека — к скольким ролям задачи он допущен: в свидетели берём наименее
    # гибких, чтобы не занимать тех, кто нужен редким ролям
    target_roles = sorted({c.role for c in targets})
    flexibility = problem.clearance[:, target_roles].sum(axis=1) if target_roles else None
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
        weights = np.asarray(mass) * debt
        quota[r] = (
            _sainte_lague(len(cells_r), weights, tiebreak[:g])
            if config.apportionment == "sainte_lague"
            else _hamilton(len(cells_r), weights, tiebreak[:g])
        )
    timer.lap("level2")

    # --- уровень 3–4: расстановка ячеек по дням -----------------------------------------
    w = config.unit_weights
    width = problem.width
    taken = np.zeros((g, width), dtype=np.int64)  # людей, отданных подразделению в эти сутки
    given = {r: np.zeros(g, dtype=np.int64) for r in quota}
    delegations: list[dict[str, Any]] = []
    unfilled: list[dict[str, Any]] = []

    def options(
        c: Cell,
    ) -> tuple[np.ndarray, dict[str, np.ndarray], np.ndarray, np.ndarray]:
        """Кому можно отдать ячейку сейчас, признаки, стоимость (уровень 3) и допустимые люди."""
        role = problem.roles[c.role]
        people = feasible(c)
        free_cap = free_capacity(c, people)
        cand = np.flatnonzero(free_cap >= role.headcount)
        q = quota[c.role][cand]
        feats = {
            "quota": (given[c.role][cand] + 1) / np.maximum(q, 0.5),
            "same_day": taken[cand, c.day].astype(np.float64),
            "capacity": free_cap[cand] / max(1, int(free_cap.max(initial=0))),
        }
        cost = (
            w.quota * feats["quota"]
            + w.same_day * feats["same_day"]
            - w.capacity * feats["capacity"]
        )
        return cand, feats, cost, people

    def place(c: Cell, chosen: int | None = None) -> bool:
        """Отдаёт ячейку: выбранному заранее (min-cost flow) или лучшему сейчас (жадно).
        Квота соблюдается, пока есть подразделения, не выбравшие её."""
        role = problem.roles[c.role]
        cand, feats, cost, people = options(c)
        if not len(cand):
            if chosen is None:
                unfilled.append(
                    {
                        "cell": c.id,
                        "missing": 1,
                        "message": f"{_date(problem, c.day)}: роль «{role.name}» — некому передать",
                    }
                )
            return False
        ranked = np.lexsort((tiebreak[cand], cost))
        if chosen is None:
            under = [i for i in ranked if given[c.role][cand[i]] < quota[c.role][cand[i]]]
            pick = int(under[0]) if under else int(ranked[0])
        else:
            hit = np.flatnonzero(cand == chosen)
            if not len(hit):
                return False  # решение потока уже недопустимо — ячейку добирает жадный проход
            pick = int(hit[0])

        def describe(i: int) -> dict[str, Any]:
            return {
                "unit": problem.unit_ids[groups[int(cand[i])]],
                "cost": round(float(cost[i]), 6),
                "features": {k: round(float(v[i]), 6) for k, v in feats.items()},
            }

        best = int(cand[pick])
        # Свидетели: наименее гибкие, затем наименее загруженные люди подразделения
        people = people[person_group[people] == best]
        assert flexibility is not None
        order = np.lexsort((people, state.month_total[people], flexibility[people]))
        for person in people[order[: role.headcount]]:
            state.add(
                int(person),
                day=c.day,
                start=c.start,
                end=c.end,
                rest=role.rest,
                first_day=c.day,
                last_day=c.last_day,
                type_index=role.type_index,
                load=(c.last_day - c.day + 1) * role.weight,
            )
        delegations.append(
            {
                "cell": c.id,
                **describe(pick),
                "keep": groups[best] == u,
                "rank": int(np.flatnonzero(ranked == pick)[0]) + 1,
                "candidates": len(cand),
                "alternatives": [
                    describe(int(i)) for i in ranked[: config.alternatives + 1] if int(i) != pick
                ][: config.alternatives],
                "capacity": {
                    problem.unit_ids[groups[k]]: int(capacity[c.index][k]) for k in range(g)
                },
            }
        )
        days = slice(c.day, min(width, c.last_day + 1))
        taken[best, days] += role.headcount
        given[c.role][best] += 1
        return True

    method = "flow" if config.units_method in ("auto", "flow") else "greedy"
    info: dict[str, Any] = {}
    if g and method == "flow":
        info = _place_by_flow(problem, targets, quota, free_capacity, taken, w, place, g)
    elif g:
        order = sorted(
            targets,
            key=lambda c: (
                int((capacity[c.index] >= problem.roles[c.role].headcount).sum()),
                c.day,
                c.role,
                c.index,
            ),
        )
        for c in order:
            place(c)
        info = {"optimal": False}
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
        "method": method,
        "method_info": {**info, "apportionment": config.apportionment},
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
