"""Legacy-baseline: алгоритмы старой системы на снимке в памяти (`docs/legacy-analysis.md`
§2.4–2.5). Код legacy не копируется — повторяется логика: порядок обхода, счётчики, веса,
сортировка. ORM-запросы заменены эквивалентными выборками из массивов снимка, поэтому
сравнение идёт по алгоритму, а не по инфраструктуре.

Перенос на модель новой системы (бизнес-правила legacy не меняются, меняется только
то, чего в legacy не было):
- ячейка legacy — «дата × тип наряда»; здесь — «дата × роль», счётчики «того же наряда»
  ведутся по типу наряда, как в legacy;
- люди — из поддерева исполнителя (open-questions №37), в legacy — только из самого
  подразделения; допуск — к роли с учётом срока действия (в legacy допуски бессрочные).

Всё остальное — как в legacy:
- `people_*` (`AssignmentAutomationService`): ячейки по (дата, наряд); кандидаты — с допуском,
  не освобождённые **в дату начала**, не стоящие в наряде **с той же датой начала**;
  стоимость `месяц × 10 + тот же наряд × 5 + вчера 20 (+30, если и позавчера)`; сортировка
  (стоимость, месяц, тот же наряд, имя), берутся первые `need`. Отдых, многосуточные наряды
  и лимиты не проверяются — такие нарушения стенд считает, а не запрещает.
- В legacy счётчики и занятость берутся из БД один раз на предпросмотр и не учитывают выбор
  этого же прогона (`faithful`): один человек может получить все наряды дня. Вариант
  `incremental` обновляет их после каждого выбора — это «лучшее прочтение» legacy, чтобы
  сравнение не сводилось к одной этой ошибке.
- `units` (`PlanAutomationService`, режим «только дочерние с учётом людей»): проход по типу
  наряда, внутри — по датам; ёмкость дочернего — люди с допуском, не освобождённые и не
  начинающие в эту дату другой наряд, должна быть ≥ требуемого; сортировка
  (ротация, тот же наряд за месяц, всего за месяц, тот же наряд за день, всего за день,
  взвешенный score, имя). Счётчики накапливаются по ходу прохода (как в legacy), ёмкость —
  нет (в legacy она из БД).
"""

from typing import Any

import numpy as np

from allocation.engine.problem import Problem, load_problem

MONTH_WEIGHT = 10
SAME_DUTY_WEIGHT = 5
RECENT_PENALTY = 20
CONSECUTIVE_PENALTY = 30

UNIT_BASE_WEIGHT = 8.0
UNIT_SAME_DUTY_WEIGHT = 4.0
UNIT_DAY_WEIGHT = 20.0
UNIT_DAY_SAME_DUTY_WEIGHT = 12.0


def _starts(problem: Problem) -> np.ndarray:
    """[люди × дни]: человек начинает наряд в этот день (по существующим назначениям)."""
    starts = np.zeros((problem.people, problem.width), dtype=np.bool_)
    for e in problem.existing:
        if 0 <= e.day < problem.width:
            starts[e.person, e.day] = True
    return starts


def _cleared(problem: Problem, role: int, day: int) -> np.ndarray:
    return (
        problem.clearance[:, role]
        & (problem.valid_from[:, role] <= day)
        & (problem.valid_to[:, role] >= day)
    )


def people(snapshot: dict[str, Any], incremental: bool = False) -> dict[str, Any]:
    """Распределение людей по ячейкам подразделения графика (режим «дозаполнить»)."""
    problem = load_problem(snapshot)
    u = problem.schedule_unit
    cells = [
        c
        for c in problem.cells
        if c.schedule_unit == u
        and c.executor == u
        and problem.roles[c.role].active
        and problem.month_start <= c.day <= problem.month_end
    ]
    # Порядок legacy: дата, название наряда (и роль — в legacy её не было)
    cells.sort(
        key=lambda c: (c.day, problem.roles[c.role].duty_type, problem.roles[c.role].name, c.index)
    )
    filled: dict[int, int] = {}
    starts = _starts(problem)
    month = np.zeros(problem.people, dtype=np.int64)
    same = np.zeros((problem.people, max(1, len(problem.type_ids))), dtype=np.int64)
    for e in problem.existing:
        if e.cell is not None:
            filled[e.cell] = filled.get(e.cell, 0) + 1
        if problem.month_start <= e.day <= problem.month_end:
            month[e.person] += 1
            same[e.person, e.type_index] += 1
    scope = problem.person_unit >= 0
    order_key = np.array([int(pid[1:]) for pid in problem.people_ids])  # «по имени»

    picks: list[tuple[int, int]] = []
    for c in cells:
        role = problem.roles[c.role]
        need = role.headcount - filled.get(c.index, 0)
        if need <= 0:
            continue
        ok = scope & _cleared(problem, c.role, c.day) & problem.available[:, c.day]
        ok &= ~starts[:, c.day]
        cand = np.flatnonzero(ok)
        if not len(cand):
            continue
        yesterday = starts[cand, c.day - 1]
        before = starts[cand, c.day - 2]
        recent = RECENT_PENALTY * yesterday + CONSECUTIVE_PENALTY * (yesterday & before)
        m, s = month[cand], same[cand, role.type_index]
        score = m * MONTH_WEIGHT + s * SAME_DUTY_WEIGHT + recent
        chosen = cand[np.lexsort((order_key[cand], s, m, score))[:need]]
        for p in chosen:
            picks.append((c.index, int(p)))
            if incremental:
                starts[p, c.day] = True
                month[p] += 1
                same[p, role.type_index] += 1
    return {
        "kind": "people",
        "method": "legacy_incremental" if incremental else "legacy",
        "assignments": [
            {"cell": problem.cells[c].id, "person": problem.people_ids[p]} for c, p in picks
        ],
        "removed": [],
    }


def units(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Распределение ячеек подразделения графика по прямым дочерним."""
    problem = load_problem(snapshot)
    u = problem.schedule_unit
    children = [i for i, parent in enumerate(problem.unit_parent) if parent == u]
    # Для каждого человека — дочерний узел, в чьём поддереве он состоит
    top = []
    for i in range(len(problem.unit_ids)):
        node = i
        while problem.unit_parent[node] is not None and problem.unit_parent[node] != u:
            node = int(problem.unit_parent[node])  # type: ignore[arg-type]
        top.append(node)
    position = {ch: k for k, ch in enumerate(children)}
    group = np.array(
        [position.get(top[pu], -1) if pu >= 0 else -1 for pu in problem.person_unit],
        dtype=np.int64,
    )
    g = len(children)
    names = [problem.unit_names[ch] for ch in children]
    starts = _starts(problem)
    occupied = {e.cell for e in problem.existing if e.cell is not None}
    cells = [
        c
        for c in problem.cells
        if c.schedule_unit == u
        and c.executor == u
        and not c.pinned
        and c.index not in occupied
        and problem.roles[c.role].active
        and problem.month_start <= c.day <= problem.month_end
    ]
    # Проход по типу наряда (по названию), внутри — по датам (и ролям)
    cells.sort(
        key=lambda c: (problem.roles[c.role].duty_type, c.day, problem.roles[c.role].name, c.index)
    )
    month_load = np.zeros(g, dtype=np.int64)
    type_month = np.zeros((g, max(1, len(problem.type_ids))), dtype=np.int64)
    day_load: dict[tuple[int, int], int] = {}
    day_type: dict[tuple[int, int, int], int] = {}
    rotation = np.zeros((g, max(1, len(problem.type_ids))), dtype=np.int64)

    delegations = []
    for c in cells:
        role = problem.roles[c.role]
        t = role.type_index
        ok = _cleared(problem, c.role, c.day) & problem.available[:, c.day] & ~starts[:, c.day]
        member = group[ok]
        capacity = np.bincount(member[member >= 0], minlength=g) if g else np.zeros(0)
        best: tuple[Any, ...] | None = None
        for k in range(g):
            if capacity[k] <= 0 or capacity[k] < role.headcount:
                continue
            dl, dtl = day_load.get((c.day, k), 0), day_type.get((c.day, k, t), 0)
            score = (
                month_load[k] * UNIT_BASE_WEIGHT
                + type_month[k, t] * UNIT_SAME_DUTY_WEIGHT
                + dl * UNIT_DAY_WEIGHT
                + dtl * UNIT_DAY_SAME_DUTY_WEIGHT
            )
            key = (
                int(rotation[k, t]),
                int(type_month[k, t]),
                int(month_load[k]),
                dtl,
                dl,
                round(float(score), 4),
                names[k],
                k,
            )
            if best is None or key < best:
                best = key
        if best is None:
            continue
        k = best[-1]
        delegations.append({"cell": c.id, "unit": problem.unit_ids[children[k]]})
        month_load[k] += 1
        type_month[k, t] += 1
        day_load[(c.day, k)] = day_load.get((c.day, k), 0) + 1
        day_type[(c.day, k, t)] = day_type.get((c.day, k, t), 0) + 1
        rotation[k, t] += 1
    return {"kind": "units", "method": "legacy", "delegations": delegations}
