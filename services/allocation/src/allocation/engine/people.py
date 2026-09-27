"""Распределение людей по ячейкам подразделения графика (уровни 1–4, фаза 4).

Уровень 4 фазы 4 — жадный выбор в порядке MRV: ячейки с наименьшим числом допустимых
кандидатов заполняются первыми (устраняет проблему legacy «жадный по датам съедает лучших
в начале месяца», `docs/legacy-analysis.md` §4.4). Кандидат — с наименьшей стоимостью
уровня 3; равенство — детерминированно по seed. Точные методы — фаза 5.
"""

import time
from typing import Any

import numpy as np

from allocation.engine.config import EngineConfig
from allocation.engine.feasibility import StaticCandidates, flow_bound, static_candidates
from allocation.engine.metrics import fairness
from allocation.engine.problem import Cell, IntArray, Problem
from allocation.engine.state import PeopleState

REASONS = ("no_clearance", "exempt", "busy", "rest", "limit")


def _date(problem: Problem, day: int) -> str:
    return problem.days[day].strftime("%d.%m") if day < len(problem.days) else f"день {day}"


def target_cells(problem: Problem, config: EngineConfig) -> list[Cell]:
    """Ячейки, которые закрывает само подразделение графика: свои и принятые входящие,
    не переданные дальше, действующие роли, дни месяца, в области прогона."""
    scope = {str(c) for c in config.cell_ids} if config.cell_ids else None
    u = problem.schedule_unit
    return [
        c
        for c in problem.cells
        if c.schedule_unit == u
        and c.executor == u
        and problem.roles[c.role].active
        and problem.month_start <= c.day <= problem.month_end
        and (scope is None or c.id in scope)
    ]


class Timer:
    def __init__(self) -> None:
        self.ms: dict[str, float] = {}
        self._t = time.perf_counter()

    def lap(self, name: str) -> None:
        now = time.perf_counter()
        self.ms[name] = round((now - self._t) * 1000, 1)
        self._t = now


def solve_people(problem: Problem, config: EngineConfig, seed: int) -> dict[str, Any]:
    timer = Timer()
    rng = np.random.default_rng(seed)
    tiebreak = rng.permutation(problem.people).astype(np.int64)

    # --- уровень 0: область задачи и что пересматривается ------------------------------
    targets = target_cells(problem, config)
    target_idx = {c.index for c in targets}
    replaced = [
        e
        for e in problem.existing
        if config.mode == "rebuild"
        and e.cell in target_idx
        and e.auto
        and not e.pinned
        and not e.override
    ]
    replaced_ids = {e.id for e in replaced}
    state = PeopleState(problem, config.half_life_days, config.holiday_weight)
    fixed: dict[int, int] = {}
    for e in problem.existing:
        if e.id in replaced_ids:
            continue
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
        if e.cell is not None:
            fixed[e.cell] = fixed.get(e.cell, 0) + 1
    need = {
        c.index: problem.roles[c.role].headcount - fixed.get(c.index, 0)
        for c in targets
        if problem.roles[c.role].headcount - fixed.get(c.index, 0) > 0
    }
    scope = problem.person_unit >= 0
    timer.lap("level0")

    # --- уровень 1: статическая допустимость -------------------------------------------
    static: dict[int, StaticCandidates] = {
        c: static_candidates(problem, problem.cells[c], scope) for c in need
    }
    initial: dict[int, IntArray] = {}
    for c, sc in static.items():
        cell = problem.cells[c]
        role = problem.roles[cell.role]
        people = sc.people
        ok = state.free(people, cell.day, cell.last_day)
        ok &= state.rested(people, cell.start, cell.end, role.rest)
        ok &= state.within_limits(people, cell.day)
        initial[c] = people[ok]
    timer.lap("level1")

    # --- уровень 2: ёмкость, дефициты, граница выполнимости -----------------------------
    deficits = []
    for c, count in need.items():
        cap = len(initial[c])
        if cap < count:
            cell = problem.cells[c]
            sc = static[c]
            deficits.append(
                {
                    "cell": cell.id,
                    "day": cell.day,
                    "role": problem.roles[cell.role].id,
                    "need": count,
                    "capacity": cap,
                    "message": (
                        f"{_date(problem, cell.day)}: роль «{problem.roles[cell.role].name}» — "
                        f"нужно {count}, допустимых {cap} (нет допуска: {sc.no_clearance}, "
                        f"освобождены: {sc.exempt}, заняты другими нарядами или без отдыха: "
                        f"{len(sc.people) - cap})"
                    ),
                }
            )
    bound = (
        flow_bound(initial, need, problem.cells, config.strict_feasibility_max_edges)
        if config.strict_feasibility
        else None
    )
    timer.lap("level2")

    # --- уровни 3–4: скоринг и жадный выбор в порядке MRV -------------------------------
    w = config.people_weights
    weights = {"load": w.load, "same_type": w.same_type, "holiday": w.holiday, "recency": w.recency}
    order = sorted(
        need, key=lambda c: (len(initial[c]), problem.cells[c].day, problem.cells[c].role, c)
    )
    assignments: list[dict[str, Any]] = []
    unfilled: list[dict[str, Any]] = []
    for c in order:
        cell = problem.cells[c]
        role = problem.roles[cell.role]
        sc = static[c]
        for _ in range(need[c]):
            people = sc.people
            free = state.free(people, cell.day, cell.last_day)
            rested = state.rested(people, cell.start, cell.end, role.rest)
            limits = state.within_limits(people, cell.day)
            ok = free & rested & limits
            rejected = {
                "no_clearance": sc.no_clearance,
                "exempt": sc.exempt,
                "busy": int((~free).sum()),
                "rest": int((free & ~rested).sum()),
                "limit": int((free & rested & ~limits).sum()),
            }
            feasible = people[ok]
            if len(feasible) == 0:
                unfilled.append(
                    {
                        "cell": cell.id,
                        "missing": 1,
                        "rejected": rejected,
                        "message": (
                            f"{_date(problem, cell.day)}: роль «{role.name}» — некого поставить"
                        ),
                    }
                )
                continue
            feats = state.features(feasible, cell.day, role.type_index)
            cost: np.ndarray = np.zeros(len(feasible))
            for name, values in feats.items():
                cost = cost + weights[name] * values
            ranked = np.lexsort((tiebreak[feasible], cost))[: config.alternatives + 1]

            def describe(
                i: int, feats: dict[str, Any] = feats, cost: Any = cost, feasible: Any = feasible
            ) -> dict[str, Any]:
                return {
                    "person": problem.people_ids[int(feasible[i])],
                    "cost": round(float(cost[i]), 6),
                    "features": {k: round(float(v[i]), 6) for k, v in feats.items()},
                }

            best = int(feasible[ranked[0]])
            assignments.append(
                {
                    "cell": cell.id,
                    **describe(int(ranked[0])),
                    "rank": 1,
                    "candidates": len(feasible),
                    "alternatives": [describe(int(i)) for i in ranked[1:]],
                    "rejected": rejected,
                }
            )
            state.add(
                best,
                day=cell.day,
                start=cell.start,
                end=cell.end,
                rest=role.rest,
                first_day=cell.day,
                last_day=cell.last_day,
                type_index=role.type_index,
                load=(cell.last_day - cell.day + 1) * role.weight,
            )
    timer.lap("level4")

    eligible = (
        np.unique(np.concatenate([static[c].people for c in need]))
        if need
        else np.array([], dtype=np.int32)
    )
    places = sum(need.values())
    return {
        "kind": "people",
        "assignments": assignments,
        "removed": sorted(replaced_ids),
        "delegations": [],
        "unfilled": _merge_unfilled(unfilled),
        "deficits": deficits,
        "metrics": {
            "cells": len(targets),
            "places": places,
            "filled": len(assignments),
            "shortage": places - len(assignments),
            "upper_bound": bound,
            # По нагрузке (нарядо-сутки × вес) и по числу нарядов за месяц
            "fairness": fairness(state.month_load()[eligible]),
            "fairness_count": fairness(state.month_total[eligible].astype(np.float64)),
            "timings_ms": timer.ms,
        },
    }


def _merge_unfilled(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Несколько незакрытых мест одной ячейки — одной записью."""
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        if item["cell"] in merged:
            merged[item["cell"]]["missing"] += 1
        else:
            merged[item["cell"]] = dict(item)
    return list(merged.values())
