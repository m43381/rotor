"""OR-Tools CP-SAT на месяц подразделения — постановка Nurse Rostering
(`docs/allocation-design.md`).

Переменные — булевы «человек × ячейка» только для допустимых пар уровня 1. Жёсткие ограничения:
численность роли, «≤ 1 наряда в сутки» по занятым суткам, отдых (пары ячеек одного человека,
между которыми меньше отдыха, взаимоисключающие), месячные лимиты с учётом уже стоящих нарядов.
Закрепления и ручные назначения — фиксированный контекст (они уже в состоянии и отсекли
недопустимые пары).

Цель лексикографическая (open-questions №49): этап 1 — максимум закрытых мест; этап 2 при
найденном максимуме — сумма квадратов нагрузки людей с затуханием, включая прошлые наряды
(та же величина, что в метрике справедливости), отдельно — праздничные, и в последнюю очередь
стоимость признаков уровня 3.

Жадное решение передаётся как подсказка. Детерминизм — фиксированный seed и предел
«детерминированного времени» решателя; настенный предел — страховка (тогда `optimal` = False).
Большая задача решается окнами по дням (скользящий горизонт): прошлые окна зафиксированы.
"""

import time
from collections import defaultdict
from typing import Any

import numpy as np
from ortools.sat.python import cp_model

from allocation.engine.methods import greedy, local_search
from allocation.engine.people import Pick, Prepared
from allocation.engine.state import PeopleState

LOAD_SCALE = 10  # нагрузка в целых десятых: решателю нужны целые коэффициенты
TANGENTS = 10  # касательных: нагрузка до +9 нарядов с шагом в типичный наряд


def _params(prep: Prepared, share: float) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    cfg = prep.config
    solver.parameters.random_seed = prep.seed
    solver.parameters.num_workers = cfg.cpsat_workers
    solver.parameters.max_deterministic_time = cfg.cpsat_deterministic_time * share
    solver.parameters.max_time_in_seconds = cfg.cpsat_time_limit_s * share
    return solver


def _repair(prep: Prepared, state: PeopleState, cells: list[int], start: list[Pick]) -> list[Pick]:
    """Допустимое на текущем состоянии решение окна: назначения стартового решения, которые
    ещё допустимы, плюс жадное дозаполнение остального. Всегда допустимо — это и подсказка,
    и запасной вариант, если решатель не успел."""
    trial = state.copy()
    wanted = set(cells)
    picks: list[Pick] = []
    left = dict(prep.need)
    for c, p in sorted(start, key=lambda x: (prep.problem.cells[x[0]].start, x[0], x[1])):
        if c not in wanted or left[c] <= 0:
            continue
        if prep.feasible(trial, c, np.array([p], dtype=np.int32))[0]:
            prep.take(trial, c, p)
            picks.append((c, p))
            left[c] -= 1
    rest = [c for c in cells if left[c] > 0]
    if rest:
        saved = prep.need
        prep.need = {**saved, **{c: left[c] for c in rest}}
        picks += greedy.run(prep, trial, rest)
        prep.need = saved
    return picks


def _window(
    prep: Prepared, state: PeopleState, cells: list[int], share: float, start: list[Pick]
) -> tuple[list[Pick], dict[str, Any]]:
    problem = prep.problem
    candidates = {c: prep.initial[c][prep.feasible(state, c, prep.initial[c])] for c in cells}
    hint = set(_repair(prep, state, cells, start))
    # Сужение модели: каждому месту — лучшие по стоимости признаков кандидаты и человек из
    # подсказки (решение жадного метода всегда остаётся допустимым для модели)
    top = prep.config.cpsat_candidates_per_place
    if top > 0:
        in_hint: dict[int, set[int]] = defaultdict(set)
        for c, p in hint:
            in_hint[c].add(p)
        for c in cells:
            people = candidates[c]
            limit = top * prep.need[c]
            if len(people) > limit:
                cost, _ = prep.cost(state, c, people)
                keep = people[np.lexsort((prep.tiebreak[people], cost))[:limit]]
                extra = np.array(sorted(in_hint[c] - {int(p) for p in keep}), dtype=people.dtype)
                candidates[c] = np.concatenate([keep, extra])
    model = cp_model.CpModel()
    x: dict[Pick, cp_model.IntVar] = {}
    by_person: dict[int, list[int]] = defaultdict(list)
    for c in cells:
        for p in candidates[c]:
            p = int(p)
            x[c, p] = model.new_bool_var(f"x{c}_{p}")
            by_person[p].append(c)
            model.add_hint(x[c, p], (c, p) in hint)
    if not x:
        return [], {"status": "EMPTY", "optimal": True, "variables": 0}
    for c in cells:
        vars_c = [x[c, int(p)] for p in candidates[c]]
        if vars_c:
            model.add(sum(vars_c) <= prep.need[c])

    constraints = 0
    for p, person_cells in by_person.items():
        person_cells.sort(key=lambda c: problem.cells[c].start)
        # «≤ 1 наряда в сутки»: по каждым суткам — не больше одной ячейки
        per_day: dict[int, list[cp_model.IntVar]] = defaultdict(list)
        for c in person_cells:
            cell = problem.cells[c]
            for d in range(cell.day, cell.last_day + 1):
                per_day[d].append(x[c, p])
        for items in per_day.values():
            if len(items) > 1:
                model.add_at_most_one(items)
                constraints += 1
        # Отдых: следующая ячейка раньше «конец + отдых» предыдущей — не обе
        for i, c1 in enumerate(person_cells):
            a = problem.cells[c1]
            rest = problem.roles[a.role].rest
            for c2 in person_cells[i + 1 :]:
                b = problem.cells[c2]
                if b.start >= a.end + rest:
                    break
                if b.day > a.last_day:  # пересечение по суткам уже запрещено выше
                    model.add_bool_or([x[c1, p].negated(), x[c2, p].negated()])
                    constraints += 1
        # Лимиты месяца с учётом уже стоящих нарядов
        limit = int(problem.limit_total[p])
        if limit >= 0:
            model.add(
                sum(x[c, p] for c in person_cells) <= max(0, limit - int(state.month_total[p]))
            )
        hol = int(problem.limit_holiday[p])
        holiday_cells = [c for c in person_cells if problem.is_holiday(problem.cells[c].day)]
        if hol >= 0 and holiday_cells:
            model.add(
                sum(x[c, p] for c in holiday_cells) <= max(0, hol - int(state.month_holiday[p]))
            )

    # --- этап 1: максимум закрытых мест ------------------------------------------------
    filled = sum(x.values())
    places = sum(prep.need[c] for c in cells)
    if len(hint) == places:
        # Жадный метод закрыл все места — максимум известен, этап 1 не нужен, а в этап 2
        # подсказкой идёт жадное решение (оно уже неплохое по равномерности)
        best, stage1_optimal = places, True
        stage1 = {key: key in hint for key in x}
    else:
        model.maximize(filled)
        solver = _params(prep, share / 2)
        status1 = solver.solve(model)
        if status1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return sorted(hint), {
                "status": solver.status_name(status1),
                "optimal": False,
                "fallback": True,
            }
        best = round(solver.objective_value)
        stage1_optimal = status1 == cp_model.OPTIMAL
        stage1 = {key: bool(solver.value(var)) for key, var in x.items()}
        if len(hint) == best:  # жадное решение тоже максимальное — оно лучше как старт
            stage1 = {key: key in hint for key in x}
    # Подсказка этапа 2 — полная, включая вспомогательные переменные: с неполной
    # подсказкой решатель может не найти ни одного решения за отведённое время
    model.clear_hints()  # type: ignore[no-untyped-call]
    for key, var in x.items():
        model.add_hint(var, stage1[key])

    # --- этап 2: равномерность при максимуме мест, затем стоимость признаков -----------------
    model.add(filled >= best)
    # Нагрузка человека с затуханием к середине месяца — ровно то, что измеряет метрика
    # справедливости: T_p = прошлое + Σ вес_наряда·затухание·x. Цель — Σ T_p² (квадраты
    # штрафуют перекосы сильнее суммы), праздничные — отдельной суммой квадратов.
    mid = round(state.mid)
    prior = state.load @ state.kernel(mid)
    weight = {c: prep.unit_load(c) * state.decay ** abs(problem.cells[c].day - mid) for c in cells}
    terms: list[Any] = []
    for p, person_cells in by_person.items():
        loads = {c: round(LOAD_SCALE * weight[c]) for c in person_cells}
        base = round(LOAD_SCALE * float(prior[p]))
        top = base + sum(loads.values())
        total = model.new_int_var(base, top, f"t{p}")
        model.add(total == base + sum(loads[c] * x[c, p] for c in person_cells))
        hint_total = base + sum(loads[c] for c in person_cells if stage1[c, p])
        model.add_hint(total, hint_total)
        step = round(np.mean(list(loads.values()))) if loads else 1
        terms.append(_convex_square(model, total, base, top, hint_total, f"s{p}", step))
        holiday_cells = [c for c in person_cells if problem.is_holiday(problem.cells[c].day)]
        if holiday_cells:
            h_base = round(LOAD_SCALE * float(state.holiday_load[p]))
            h_top = h_base + LOAD_SCALE * len(holiday_cells)
            h_total = model.new_int_var(h_base, h_top, f"h{p}")
            model.add(h_total == h_base + sum(LOAD_SCALE * x[c, p] for c in holiday_cells))
            h_hint = h_base + LOAD_SCALE * sum(stage1[c, p] for c in holiday_cells)
            model.add_hint(h_total, h_hint)
            terms.append(
                _convex_square(model, h_total, h_base, h_top, h_hint, f"hs{p}", LOAD_SCALE)
            )
    # Стоимость признаков уровня 3 — младший критерий, на порядок меньше квадратов нагрузки
    for c in cells:
        if len(candidates[c]):
            cost, _ = prep.cost(state, c, candidates[c])
            for p, value in zip(candidates[c], cost, strict=True):
                terms.append(round(LOAD_SCALE * value) * x[c, int(p)])
    model.minimize(sum(terms))
    solver = _params(prep, share / 2)
    status2 = solver.solve(model)
    if status2 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # Этап 2 не успел — остаёмся с решением этапа 1 (оно в подсказке)
        return _from_hint(model, x), {
            "status": solver.status_name(status2),
            "optimal": False,
            "filled_optimal": stage1_optimal,
        }
    picks = [key for key, var in x.items() if solver.value(var)]
    return picks, {
        "status": solver.status_name(status2),
        "optimal": stage1_optimal and status2 == cp_model.OPTIMAL,
        "filled_optimal": stage1_optimal,
        "variables": len(x),
        "constraints": constraints,
        "objective": solver.objective_value,
        "bound": solver.best_objective_bound,
    }


def _convex_square(
    model: cp_model.CpModel, value: Any, low: int, high: int, hint: int, name: str, step: int
) -> cp_model.IntVar:
    """Оценка value² снизу выпуклой ломаной — касательными к параболе. Касательные — с шагом
    в один типичный наряд от текущей нагрузки: там оценка почти точна, а реальные решения
    дальше нескольких нарядов на человека не уходят. Линейные ограничения решателю даются
    намного легче произведения переменных; при минимизации переменная прижимается к ломаной."""
    step = max(1, step)
    points = sorted({min(high, low + k * step) for k in range(TANGENTS)} | {high})
    square = model.new_int_var(0, high * high, name)
    for t in points:
        model.add(square >= 2 * t * value - t * t)
    model.add_hint(square, max(2 * t * hint - t * t for t in points))
    return square


def _from_hint(model: cp_model.CpModel, x: dict[Pick, cp_model.IntVar]) -> list[Pick]:
    hint = model.proto.solution_hint
    chosen = {v for v, value in zip(hint.vars, hint.values, strict=True) if value}
    return [key for key, var in x.items() if var.index in chosen]


def solve(prep: Prepared, start: list[Pick] | None = None) -> list[Pick]:
    problem = prep.problem
    cfg = prep.config
    started = time.perf_counter()
    cells = sorted(prep.need, key=lambda c: (problem.cells[c].day, c))
    if prep.pairs > cfg.cpsat_window_pairs and cfg.window_days > 0:
        first = problem.cells[cells[0]].day if cells else 0
        groups: dict[int, list[int]] = defaultdict(list)
        for c in cells:
            groups[(problem.cells[c].day - first) // cfg.window_days].append(c)
        windows = [groups[k] for k in sorted(groups)]
    else:
        windows = [cells]
    # Старт и подсказка — решение локального поиска (или жадное, если так настроено)
    if start is None:
        start = local_search.solve(prep) if cfg.cpsat_hint == "local_search" else greedy.solve(prep)
    state = prep.base.copy()
    picks: list[Pick] = []
    details = []
    for w in windows:
        chosen, info = _window(prep, state, w, 1.0 / len(windows), start)
        for c, p in chosen:
            prep.take(state, c, p)
        picks += chosen
        details.append(info)
    prep.info = {
        "optimal": len(windows) == 1 and all(d.get("optimal") for d in details),
        "filled_optimal": all(d.get("filled_optimal", d.get("optimal")) for d in details),
        "windows": len(windows),
        "status": [d["status"] for d in details],
        "variables": sum(d.get("variables", 0) for d in details),
    }
    prep.timer.ms["cpsat_wall"] = round((time.perf_counter() - started) * 1000, 1)
    return picks
