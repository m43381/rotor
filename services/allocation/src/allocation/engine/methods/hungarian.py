"""Венгерский алгоритм по дням (`scipy.optimize.linear_sum_assignment`).

Каждый день — задача о назначениях «места дня × допустимые люди» с матрицей стоимости
уровня 3: точный оптимум за O(n³). Недопустимые пары получают огромную стоимость, поэтому
сначала максимизируется число закрытых мест, затем минимизируется стоимость. Дни решаются
по порядку: решение дня входит в состояние следующего (отдых, лимиты, нагрузка). Оптимум —
по каждому дню, не по месяцу: разница с CP-SAT показывается в эксперименте.
"""

from collections import defaultdict

import numpy as np
from scipy.optimize import linear_sum_assignment

from allocation.engine.people import Pick, Prepared

INFEASIBLE = 1e9


def solve(prep: Prepared) -> list[Pick]:
    problem = prep.problem
    state = prep.base.copy()
    by_day: dict[int, list[int]] = defaultdict(list)
    for c in prep.need:
        by_day[problem.cells[c].day].append(c)
    picks: list[Pick] = []
    days = 0
    for day in sorted(by_day):
        cells = sorted(by_day[day])
        columns = [c for c in cells for _ in range(prep.need[c])]
        feasible = {c: prep.initial[c][prep.feasible(state, c, prep.initial[c])] for c in cells}
        pools = [f for f in feasible.values() if len(f)]
        if not pools:
            continue
        rows = np.unique(np.concatenate(pools))
        matrix = np.full((len(rows), len(columns)), INFEASIBLE)
        # Жребий по seed — сотые доли стоимости: детерминированно разводит равные варианты
        jitter = prep.tiebreak[rows] / (10.0 * len(prep.tiebreak))
        column = 0
        for c in cells:
            people = feasible[c]
            if len(people):
                cost, _ = prep.cost(state, c, people)
                idx = np.searchsorted(rows, people)
            for _ in range(prep.need[c]):
                if len(people):
                    matrix[idx, column] = cost + jitter[idx]
                column += 1
        chosen_rows, chosen_cols = linear_sum_assignment(matrix)
        today = [
            (columns[col], int(rows[r]))
            for r, col in zip(chosen_rows, chosen_cols, strict=True)
            if matrix[r, col] < INFEASIBLE
        ]
        for c, person in today:
            prep.take(state, c, person)
        picks += today
        days += 1
    prep.info = {"optimal": False, "optimal_per_day": True, "days": days}
    return picks
