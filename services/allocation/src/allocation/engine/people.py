"""Распределение людей по ячейкам подразделения графика: уровни 0–2 воронки, выбор метода
уровня 4 и объяснение решения.

Методы уровня 4 (`allocation.engine.methods`) взаимозаменяемы: получают подготовленную задачу
и возвращают выбор «ячейка → человек». Объяснение строится одинаково для любого метода —
повтором решения в хронологическом порядке: для каждого назначения видно, из скольких
допустимых выбран человек, его место по стоимости признаков уровня 3, альтернативы и сводку
отсева на тот момент.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from allocation.engine.config import EngineConfig
from allocation.engine.feasibility import StaticCandidates, flow_bound, static_candidates
from allocation.engine.metrics import fairness
from allocation.engine.problem import Cell, IntArray, Problem
from allocation.engine.state import PeopleState

type Pick = tuple[int, int]  # (номер ячейки, номер человека)


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


@dataclass
class Prepared:
    """Задача после уровней 0–2: что заполнять, кем можно и что уже стоит."""

    problem: Problem
    config: EngineConfig
    seed: int
    base: PeopleState  # только фиксированные наряды (история, ручные, закреплённые)
    targets: list[Cell]
    need: dict[int, int]  # ячейка → сколько людей ещё нужно
    static: dict[int, StaticCandidates]
    initial: dict[int, IntArray]  # допустимые с учётом фиксированных нарядов
    replaced: set[str]
    deficits: list[dict[str, Any]]
    bound: int | None
    tiebreak: np.ndarray
    weights: dict[str, float]
    timer: Timer
    info: dict[str, Any] = field(default_factory=dict)  # что сообщает метод (статус, оптимум)

    @property
    def pairs(self) -> int:
        return sum(len(v) for v in self.initial.values())

    # --- общие операции методов ------------------------------------------------------

    def feasible(self, state: PeopleState, c: int, people: IntArray | None = None) -> np.ndarray:
        cell = self.problem.cells[c]
        role = self.problem.roles[cell.role]
        people = self.static[c].people if people is None else people
        ok = state.free(people, cell.day, cell.last_day)
        ok &= state.rested(people, cell.start, cell.end, role.rest)
        ok &= state.within_limits(people, cell.day)
        return ok

    def cost(
        self, state: PeopleState, c: int, people: IntArray
    ) -> tuple[np.ndarray, dict[str, Any]]:
        cell = self.problem.cells[c]
        feats = state.features(people, cell.day, self.problem.roles[cell.role].type_index)
        cost: np.ndarray = np.zeros(len(people))
        for name, values in feats.items():
            cost = cost + self.weights[name] * values
        return cost, feats

    def take(self, state: PeopleState, c: int, person: int) -> None:
        cell = self.problem.cells[c]
        role = self.problem.roles[cell.role]
        state.add(
            person,
            day=cell.day,
            start=cell.start,
            end=cell.end,
            rest=role.rest,
            first_day=cell.day,
            last_day=cell.last_day,
            type_index=role.type_index,
            load=(cell.last_day - cell.day + 1) * role.weight,
        )

    def unit_load(self, c: int) -> float:
        cell = self.problem.cells[c]
        role = self.problem.roles[cell.role]
        return self.base.unit_load((cell.last_day - cell.day + 1) * role.weight, cell.day)


def prepare(problem: Problem, config: EngineConfig, seed: int) -> Prepared:
    timer = Timer()
    rng = np.random.default_rng(seed)
    tiebreak = rng.permutation(problem.people).astype(np.int64)

    # --- уровень 0: область задачи и что пересматривается ------------------------------
    targets = target_cells(problem, config)
    target_idx = {c.index for c in targets}
    replaced = {
        e.id
        for e in problem.existing
        if config.mode == "rebuild"
        and e.cell in target_idx
        and e.auto
        and not e.pinned
        and not e.override
    }
    base = PeopleState(problem, config.half_life_days, config.holiday_weight)
    fixed: dict[int, int] = {}
    for e in problem.existing:
        if e.id in replaced:
            continue
        base.add(
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

    # --- уровень 1: статическая допустимость и фиксированные наряды --------------------
    static = {c: static_candidates(problem, problem.cells[c], scope) for c in need}
    w = config.people_weights
    prep = Prepared(
        problem=problem,
        config=config,
        seed=seed,
        base=base,
        targets=targets,
        need=need,
        static=static,
        initial={},
        replaced=replaced,
        deficits=[],
        bound=None,
        tiebreak=tiebreak,
        weights={
            "load": w.load,
            "same_type": w.same_type,
            "holiday": w.holiday,
            "recency": w.recency,
        },
        timer=timer,
    )
    for c, sc in static.items():
        prep.initial[c] = sc.people[prep.feasible(base, c)]
    timer.lap("level1")

    # --- уровень 2: ёмкость, дефициты, граница выполнимости -----------------------------
    for c, count in need.items():
        cap = len(prep.initial[c])
        if cap < count:
            cell = problem.cells[c]
            sc = static[c]
            prep.deficits.append(
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
    prep.bound = (
        flow_bound(prep.initial, need, problem.cells, config.strict_feasibility_max_edges)
        if config.strict_feasibility
        else None
    )
    timer.lap("level2")
    return prep


def run_auto(prep: Prepared) -> tuple[str, list[Pick]]:
    """Автоматический выбор метода (open-questions №46), пороги — в настройках (бенчмарк).

    1. Очень большая задача — жадный MRV.
    2. Иначе — локальный поиск (он стартует с лучшего из жадного и венгерского по дням).
    3. Если закрыто столько мест, сколько даёт строгая граница max-flow, покрытие доказано
       максимальным — считать дольше незачем. Иначе на небольшой задаче CP-SAT пытается
       закрыть больше мест, стартуя с решения локального поиска.
    """
    from allocation.engine.methods import cpsat, greedy, local_search

    cfg = prep.config
    if prep.pairs > cfg.auto_local_search_max_pairs:
        return "greedy", greedy.solve(prep)
    picks = local_search.solve(prep)
    info = dict(prep.info)
    if prep.bound is not None and len(picks) >= prep.bound:
        prep.info = {**info, "filled_optimal": True, "proof": "max_flow_bound"}
        return "local_search", picks
    if prep.pairs <= cfg.auto_cpsat_max_pairs:
        better = cpsat.solve(prep, start=picks)
        if len(better) >= len(picks):
            return "local_search+cpsat", better
        prep.info = info
    return "local_search", picks


def explain(
    prep: Prepared, picks: list[Pick]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], PeopleState]:
    """Объяснение выбора, повтором в хронологическом порядке, и незакрытые места."""
    problem, config = prep.problem, prep.config
    state = prep.base.copy()
    assignments: list[dict[str, Any]] = []
    order = sorted(picks, key=lambda x: (problem.cells[x[0]].start, x[0], x[1]))
    for c, person in order:
        cell = problem.cells[c]
        sc = prep.static[c]
        people = sc.people
        free = state.free(people, cell.day, cell.last_day)
        rested = state.rested(people, cell.start, cell.end, problem.roles[cell.role].rest)
        limits = state.within_limits(people, cell.day)
        feasible = people[free & rested & limits]
        cost, feats = prep.cost(state, c, feasible)
        ranked = np.lexsort((prep.tiebreak[feasible], cost))
        position = np.flatnonzero(feasible[ranked] == person)
        own = int(ranked[position[0]]) if len(position) else None

        def describe(
            i: int, feats: dict[str, Any] = feats, cost: Any = cost, feasible: Any = feasible
        ) -> dict[str, Any]:
            return {
                "person": problem.people_ids[int(feasible[i])],
                "cost": round(float(cost[i]), 6),
                "features": {k: round(float(v[i]), 6) for k, v in feats.items()},
            }

        chosen = (
            describe(own)
            if own is not None
            else {"person": problem.people_ids[person], "cost": None, "features": {}}
        )
        assignments.append(
            {
                "cell": cell.id,
                **chosen,
                "rank": int(position[0]) + 1 if len(position) else None,
                "candidates": len(feasible),
                "alternatives": [
                    describe(int(i))
                    for i in ranked[: config.alternatives + 1]
                    if int(feasible[i]) != person
                ][: config.alternatives],
                "rejected": {
                    "no_clearance": sc.no_clearance,
                    "exempt": sc.exempt,
                    "busy": int((~free).sum()),
                    "rest": int((free & ~rested).sum()),
                    "limit": int((free & rested & ~limits).sum()),
                },
            }
        )
        prep.take(state, c, person)

    taken: dict[int, int] = {}
    for c, _ in picks:
        taken[c] = taken.get(c, 0) + 1
    unfilled = []
    for c, count in prep.need.items():
        missing = count - taken.get(c, 0)
        if missing <= 0:
            continue
        cell = problem.cells[c]
        sc = prep.static[c]
        people = sc.people
        free = state.free(people, cell.day, cell.last_day)
        rested = state.rested(people, cell.start, cell.end, problem.roles[cell.role].rest)
        limits = state.within_limits(people, cell.day)
        unfilled.append(
            {
                "cell": cell.id,
                "missing": missing,
                "rejected": {
                    "no_clearance": sc.no_clearance,
                    "exempt": sc.exempt,
                    "busy": int((~free).sum()),
                    "rest": int((free & ~rested).sum()),
                    "limit": int((free & rested & ~limits).sum()),
                },
                "message": (
                    f"{_date(problem, cell.day)}: роль «{problem.roles[cell.role].name}» — "
                    "некого поставить"
                ),
            }
        )
    return assignments, unfilled, state


def solve_people(problem: Problem, config: EngineConfig, seed: int) -> dict[str, Any]:
    from allocation.engine.methods import cpsat, greedy, hungarian, local_search

    prep = prepare(problem, config, seed)
    if config.method == "auto":
        method, picks = run_auto(prep)
    else:
        method = config.method
        solvers = {
            "greedy": greedy.solve,
            "hungarian": hungarian.solve,
            "local_search": local_search.solve,
            "cpsat": cpsat.solve,
        }
        picks = solvers[method](prep)
    if prep.bound is not None and len(picks) >= prep.bound:
        prep.info = {**prep.info, "filled_optimal": True}
    prep.timer.lap("level4")
    assignments, unfilled, state = explain(prep, picks)
    prep.timer.lap("explain")

    eligible = (
        np.unique(np.concatenate([prep.static[c].people for c in prep.need]))
        if prep.need
        else np.array([], dtype=np.int32)
    )
    places = sum(prep.need.values())
    return {
        "kind": "people",
        "method": method,
        "method_info": prep.info,
        "assignments": assignments,
        "removed": sorted(prep.replaced),
        "delegations": [],
        "unfilled": unfilled,
        "deficits": prep.deficits,
        "metrics": {
            "cells": len(prep.targets),
            "places": places,
            "filled": len(assignments),
            "shortage": places - len(assignments),
            "upper_bound": prep.bound,
            "pairs": prep.pairs,
            # По нагрузке (нарядо-сутки × вес) и по числу нарядов за месяц
            "fairness": fairness(state.month_load()[eligible]),
            "fairness_count": fairness(state.month_total[eligible].astype(np.float64)),
            # С учётом прошлых нарядов (затухание к середине месяца) — то, что выравнивают
            # локальный поиск и CP-SAT (open-questions №49)
            "fairness_decayed": fairness((state.load @ state.kernel(round((state.mid))))[eligible]),
            "timings_ms": prep.timer.ms,
        },
    }
