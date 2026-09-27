"""Жадный выбор в порядке MRV (фаза 4): ячейки с наименьшим числом допустимых кандидатов
заполняются первыми, кандидат — с наименьшей стоимостью уровня 3, равенство — по seed.

Он же — начальное решение для локального поиска и подсказка (hint) для CP-SAT.
"""

from collections.abc import Iterable

import numpy as np

from allocation.engine.people import Pick, Prepared
from allocation.engine.state import PeopleState


def run(prep: Prepared, state: PeopleState, cells: Iterable[int]) -> list[Pick]:
    """Жадно заполняет `cells`, изменяя `state`. Кандидаты — из `prep.initial`."""
    problem = prep.problem
    order = sorted(
        cells,
        key=lambda c: (len(prep.initial[c]), problem.cells[c].day, problem.cells[c].role, c),
    )
    picks: list[Pick] = []
    for c in order:
        for _ in range(prep.need[c]):
            people = prep.initial[c]
            feasible = people[prep.feasible(state, c, people)]
            if len(feasible) == 0:
                break
            cost, _ = prep.cost(state, c, feasible)
            best = int(feasible[np.lexsort((prep.tiebreak[feasible], cost))[0]])
            picks.append((c, best))
            prep.take(state, c, best)
    return picks


def solve(prep: Prepared) -> list[Pick]:
    prep.info = {"optimal": False}
    return run(prep, prep.base.copy(), prep.need)
