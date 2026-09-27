"""MRV + локальный поиск с имитацией отжига (`docs/allocation-design.md`, «Большие подзадачи»).

Старт — жадное решение. Затем фиксированное число итераций (детерминированно по seed):
- **дозаполнение** незакрытого места допустимым человеком (закрытые места — главная цель);
- **перенос** места на другого допустимого человека;
- **обмен** людьми между двумя назначениями.

Цель — сумма квадратов нагрузки людей с учётом прошлых нарядов (сглаживает перекосы сильнее
линейной суммы, open-questions №49). Ухудшение принимается с вероятностью exp(−Δ/T),
температура линейно падает до нуля — поиск выбирается из локальных минимумов жадного метода.
Проверка допустимости хода — по спискам нарядов человека (их единицы, а не тысячи).
"""

import math
from dataclasses import dataclass

import numpy as np

from allocation.engine.methods import greedy, hungarian
from allocation.engine.people import Pick, Prepared


@dataclass(frozen=True, slots=True)
class Duty:
    start: int
    end: int
    rest: int
    first: int
    last: int
    in_month: bool
    holiday: bool
    cell: int | None  # None — фиксированный наряд (история, ручной, закреплённый)


class Book:
    """Наряды каждого человека и проверка «можно ли дать ему ячейку»."""

    def __init__(self, prep: Prepared) -> None:
        self.prep = prep
        p = prep.problem
        self.duties: dict[int, list[Duty]] = {}
        for e in p.existing:
            if e.id in prep.replaced:
                continue
            self.duties.setdefault(e.person, []).append(
                Duty(
                    e.start,
                    e.end,
                    e.rest,
                    e.first_day,
                    e.last_day,
                    p.month_start <= e.day <= p.month_end,
                    p.is_holiday(e.day),
                    None,
                )
            )
        self.cell_duty: dict[int, Duty] = {}
        for c in prep.need:
            cell = p.cells[c]
            self.cell_duty[c] = Duty(
                cell.start,
                cell.end,
                p.roles[cell.role].rest,
                cell.day,
                cell.last_day,
                True,
                p.is_holiday(cell.day),
                c,
            )

    def can_take(self, person: int, c: int, without: int | None = None) -> bool:
        new = self.cell_duty[c]
        p = self.prep.problem
        total = holiday = 0
        for d in self.duties.get(person, ()):
            if d.cell is not None and d.cell == without:
                continue
            if d.first <= new.last and new.first <= d.last:
                return False
            if d.end <= new.start:
                if new.start - d.end < d.rest:
                    return False
            elif d.start >= new.end:
                if d.start - new.end < new.rest:
                    return False
            else:
                return False
            total += d.in_month
            holiday += d.in_month and d.holiday
        limit = int(p.limit_total[person])
        if limit >= 0 and total + 1 > limit:
            return False
        hol_limit = int(p.limit_holiday[person])
        return not (new.holiday and hol_limit >= 0 and holiday + 1 > hol_limit)

    def add(self, person: int, c: int) -> None:
        self.duties.setdefault(person, []).append(self.cell_duty[c])

    def remove(self, person: int, c: int) -> None:
        items = self.duties[person]
        items.remove(self.cell_duty[c])


def solve(prep: Prepared) -> list[Pick]:
    config = prep.config
    rng = np.random.default_rng(prep.seed)
    # Старт — лучшее по числу закрытых мест из жадного и венгерского по дням: при нехватке
    # людей венгерский закрывает заметно больше, а локальный поиск число мест не уменьшает
    start = greedy.run(prep, prep.base.copy(), prep.need)
    by_day = hungarian.solve(prep)
    if len(by_day) >= len(start):
        start = by_day
    book = Book(prep)
    for c, person in start:
        book.add(person, c)

    # Нагрузка до месяца с затуханием к его середине + нагрузка новых нарядов
    mid = round(prep.base.mid)
    base_load = prep.base.load @ prep.base.kernel(mid)
    load: dict[int, float] = {}
    # Нагрузка наряда с затуханием к середине месяца — как в метрике и цели CP-SAT
    unit = {
        c: prep.unit_load(c) * prep.base.decay ** abs(prep.problem.cells[c].day - mid)
        for c in prep.need
    }

    def current(p: int) -> float:
        return load.get(p, float(base_load[p]))

    for c, person in start:
        load[person] = current(person) + unit[c]

    assigned: list[Pick] = list(start)
    in_cell: dict[int, set[int]] = {}
    for c, person in assigned:
        in_cell.setdefault(c, set()).add(person)
    open_places: list[int] = [
        c for c in sorted(prep.need) for _ in range(prep.need[c] - len(in_cell.get(c, ())))
    ]

    pools: dict[int, frozenset[int]] = {}

    def pool_set(c: int) -> frozenset[int]:
        if c not in pools:
            pools[c] = frozenset(int(p) for p in prep.initial[c])
        return pools[c]

    def delta(p: int, change: float) -> float:
        before = current(p)
        return (before + change) ** 2 - before**2

    iterations = config.ls_iterations
    t0 = config.ls_temperature * (float(np.mean(list(unit.values()))) ** 2 if unit else 1.0)
    accepted = improved_fill = 0
    for it in range(iterations):
        temperature = t0 * (1 - it / iterations)
        roll = rng.random()
        if open_places and roll < 0.2:
            k = int(rng.integers(len(open_places)))
            c = open_places[k]
            pool = prep.initial[c]
            if len(pool) == 0:
                continue
            for q in rng.permutation(pool)[:30]:
                q = int(q)
                if q not in in_cell.get(c, set()) and book.can_take(q, c):
                    book.add(q, c)
                    load[q] = current(q) + unit[c]
                    in_cell.setdefault(c, set()).add(q)
                    assigned.append((c, q))
                    open_places.pop(k)
                    improved_fill += 1
                    break
            continue
        if not assigned:
            break
        if roll < 0.6:
            i = int(rng.integers(len(assigned)))
            c, p = assigned[i]
            pool = prep.initial[c]
            for q in rng.permutation(pool)[:10]:
                q = int(q)
                if q == p or q in in_cell[c] or not book.can_take(q, c):
                    continue
                d = delta(q, unit[c]) + delta(p, -unit[c])
                if d < 0 or (temperature > 0 and rng.random() < math.exp(-d / temperature)):
                    book.remove(p, c)
                    book.add(q, c)
                    load[p] = current(p) - unit[c]
                    load[q] = current(q) + unit[c]
                    in_cell[c].discard(p)
                    in_cell[c].add(q)
                    assigned[i] = (c, q)
                    accepted += 1
                break
        elif len(assigned) > 1:
            i, j = (int(x) for x in rng.choice(len(assigned), 2, replace=False))
            (c1, p1), (c2, p2) = assigned[i], assigned[j]
            if p1 == p2 or c1 == c2 or p2 in in_cell[c1] or p1 in in_cell[c2]:
                continue
            if p2 not in pool_set(c1) or p1 not in pool_set(c2):
                continue
            change = unit[c2] - unit[c1]
            d = delta(p1, change) + delta(p2, -change)
            if not (d < 0 or (temperature > 0 and rng.random() < math.exp(-d / temperature))):
                continue
            book.remove(p1, c1)
            book.remove(p2, c2)
            if book.can_take(p2, c1) and book.can_take(p1, c2):
                book.add(p2, c1)
                book.add(p1, c2)
                load[p1] = current(p1) + change
                load[p2] = current(p2) - change
                in_cell[c1].discard(p1)
                in_cell[c1].add(p2)
                in_cell[c2].discard(p2)
                in_cell[c2].add(p1)
                assigned[i], assigned[j] = (c1, p2), (c2, p1)
                accepted += 1
            else:
                book.add(p1, c1)
                book.add(p2, c2)

    people = set(load)
    prep.info = {
        "optimal": False,
        "iterations": iterations,
        "accepted_moves": accepted,
        "filled_by_search": improved_fill,
        "objective": round(sum(current(p) ** 2 for p in people), 4),
    }
    return assigned
