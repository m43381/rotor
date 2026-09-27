"""Уровни 1–2 воронки: статическая допустимость, ёмкость, дефициты, граница выполнимости.

Статическая допустимость не зависит от других решений: люди поддерева, действующий допуск
к роли на день ячейки (ADR-0009), нет освобождения ни в одни из занятых суток. Считается
векторно по всем людям сразу — вместо построчных запросов legacy `_calculate_capacity`.
"""

from dataclasses import dataclass

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import maximum_flow

from allocation.engine.problem import Cell, IntArray, Problem


@dataclass(slots=True)
class StaticCandidates:
    people: IntArray  # номера людей, прошедших статические проверки
    in_scope: int  # людей в поддереве
    no_clearance: int
    exempt: int


def static_candidates(problem: Problem, cell: Cell, scope: np.ndarray) -> StaticCandidates:
    """`scope` — маска людей, из которых вообще выбирают (поддерево исполнителя)."""
    r, d = cell.role, cell.day
    cleared = (
        scope
        & problem.clearance[:, r]
        & (problem.valid_from[:, r] <= d)
        & (problem.valid_to[:, r] >= d)
    )
    last = min(problem.width - 1, cell.last_day)
    free = problem.available[:, d : last + 1].all(axis=1)
    ok = cleared & free
    in_scope = int(scope.sum())
    n_cleared = int(cleared.sum())
    return StaticCandidates(
        people=np.flatnonzero(ok).astype(np.int32),
        in_scope=in_scope,
        no_clearance=in_scope - n_cleared,
        exempt=n_cleared - int(ok.sum()),
    )


def flow_bound(
    candidates: dict[int, IntArray], need: dict[int, int], cells: list[Cell], max_edges: int
) -> int | None:
    """Верхняя граница числа закрываемых мест — максимальный поток
    исток → человек → (человек, день) → ячейка → сток.

    Узел «человек, день» с пропускной способностью 1 не даёт поставить человека в две ячейки
    одного дня — это строгая (не эвристическая) граница по теореме Холла/Кёнига без учёта
    отдыха и лимитов. Для очень больших задач возвращает None (граница не считается).
    """
    cells_order = list(need)
    edges = sum(len(candidates[c]) for c in cells_order)
    if edges == 0:
        return 0
    if edges > max_edges:
        return None
    # Все пары «человек — ячейка» одним массивом; граф строится векторно, без циклов
    person = np.concatenate([candidates[c] for c in cells_order]).astype(np.int64)
    cell = np.repeat(np.arange(len(cells_order)), [len(candidates[c]) for c in cells_order])
    day = np.array([cells[c].day for c in cells_order], dtype=np.int64)[cell]
    width = int(day.max()) + 1
    pair_key, pair_of_edge = np.unique(person * width + day, return_inverse=True)
    persons, person_of_pair = np.unique(pair_key // width, return_inverse=True)
    n_people, n_pairs, n_cells = len(persons), len(pair_key), len(cells_order)
    first_person, first_pair = 1, 1 + n_people
    first_cell = first_pair + n_pairs
    sink = first_cell + n_cells
    need_arr = np.array([need[c] for c in cells_order], dtype=np.int64)
    rows = np.concatenate(
        [
            np.zeros(n_people, dtype=np.int64),  # исток → человек
            first_person + person_of_pair,  # человек → (человек, день), ёмкость 1
            first_pair + pair_of_edge,  # (человек, день) → ячейка, ёмкость 1
            first_cell + np.arange(n_cells),  # ячейка → сток, ёмкость = сколько нужно
        ]
    )
    cols = np.concatenate(
        [
            first_person + np.arange(n_people),
            first_pair + np.arange(n_pairs),
            first_cell + cell,
            np.full(n_cells, sink),
        ]
    )
    caps = np.concatenate(
        [
            np.full(n_people, int(need_arr.sum())),
            np.ones(n_pairs, dtype=np.int64),
            np.ones(len(person), dtype=np.int64),
            need_arr,
        ]
    ).astype(np.int32)
    graph = csr_matrix((caps, (rows, cols)), shape=(sink + 1, sink + 1))
    return int(maximum_flow(graph, 0, sink).flow_value)
