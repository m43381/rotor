"""Синтетическая организация для экспериментального стенда: глубокое дерево подразделений,
наряды на разных уровнях, личный состав в листьях, история нарядов — и снимки ADR-0013 для
любого узла и месяца.

Профиль (open-questions №4): 7 уровней (академия → … → группа), тысячи узлов, неравные по
размеру ветви. Наряды есть у узлов уровней 0…PEOPLE_LEVEL: ячейки вышестоящих спускаются
по дереву делегированием до уровня PEOPLE_LEVEL («курс»), где назначаются люди его поддерева.
Число мест в день у узла пропорционально числу людей в его поддереве (`LOAD` нарядов на
человека в месяц в сумме по уровням).

Всё детерминировано по seed. Идентификаторы читаемые (`u12`, `r7`, `p305`), а не UUID:
движку важна только их уникальность.
"""

import calendar
import datetime as dt
import math
import random
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

DAY = 1440
DEPTH = 6  # уровни 0…6
PEOPLE_LEVEL = 4  # узлы этого уровня назначают людей; выше — только делегирование
LEAF_PEOPLE = 25  # людей в листе в среднем
HISTORY_DAYS = 90
# Доля мест по уровням владельца наряда (сумма — 1) и нарядов на человека в месяц всего
LEVEL_SHARE = (0.10, 0.15, 0.15, 0.20, 0.40)
LOAD = 1.3
LEVEL_NAMES = ("Академия", "Факультет", "Отделение", "Курс-блок", "Курс", "Взвод", "Группа")
# Шаблоны ролей: начало, длительность (мин), отдых (ч), вес нагрузки
TEMPLATES = (
    ("08:00:00", 1440, 48, 1.0),
    ("18:00:00", 1440, 48, 1.0),
    ("20:00:00", 360, 24, 1.0),
    ("09:00:00", 4320, 72, 1.5),
)
HOLIDAYS = {
    (1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8),
    (2, 23), (3, 8), (5, 1), (5, 9), (6, 12), (11, 4),
}  # fmt: skip


@dataclass(slots=True)
class Unit:
    parent: int | None
    level: int
    name: str
    children: list[int] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RoleDef:
    type_index: int
    owner: int
    name: str
    headcount: int
    start: str
    duration: int
    rest: int
    weight: float

    @property
    def start_min(self) -> int:
        t = dt.time.fromisoformat(self.start)
        return t.hour * 60 + t.minute


@dataclass(slots=True)
class PersonDef:
    unit: int
    clearances: dict[int, tuple[dt.date | None, dt.date | None]]
    exemptions: list[tuple[dt.date, dt.date]]
    limit: tuple[int | None, int | None] | None


@dataclass(frozen=True, slots=True)
class Duty:
    """Наряд человека: история или результат прогона."""

    person: int
    role: int
    date: dt.date


@dataclass
class Org:
    units: list[Unit]
    roles: list[RoleDef]
    type_names: list[str]
    people: list[PersonDef]
    subtree_people: list[list[int]] = field(default_factory=list)  # по узлам

    def descendants(self, node: int) -> list[int]:
        result, stack = [], [node]
        while stack:
            u = stack.pop()
            result.append(u)
            stack.extend(reversed(self.units[u].children))
        return result

    def at_level(self, level: int) -> list[int]:
        return [i for i, u in enumerate(self.units) if u.level == level]

    def roles_of(self, node: int) -> list[int]:
        return [r for r, role in enumerate(self.roles) if role.owner == node]


def month_days(month: dt.date) -> list[dt.date]:
    n = calendar.monthrange(month.year, month.month)[1]
    return [month.replace(day=d) for d in range(1, n + 1)]


def day_kind(d: dt.date) -> str:
    if (d.month, d.day) in HOLIDAYS:
        return "holiday"
    return "weekend" if d.weekday() >= 5 else "workday"


def generate_org(people: int, seed: int, month: dt.date, load: float = LOAD) -> Org:
    rng = random.Random(seed)
    leaves_target = max(1, round(people / LEAF_PEOPLE))
    branching = max(1.6, leaves_target ** (1 / DEPTH))
    units = [Unit(parent=None, level=0, name=LEVEL_NAMES[0])]
    frontier = [0]
    for level in range(1, DEPTH + 1):
        nxt = []
        for parent in frontier:
            # Неравные ветви: от 1 до ~2 × среднего
            k = max(1, round(rng.uniform(0.4, 1.6) * branching))
            for j in range(k):
                units.append(
                    Unit(
                        parent=parent,
                        level=level,
                        name=f"{LEVEL_NAMES[level]} {units[parent].name.split()[-1]}.{j + 1}"
                        if level > 1
                        else f"{LEVEL_NAMES[level]} {j + 1}",
                    )
                )
                units[parent].children.append(len(units) - 1)
                nxt.append(len(units) - 1)
        frontier = nxt
    leaves = frontier
    # Люди по листьям — неравномерно (веса листьев случайны)
    weights = [rng.uniform(0.5, 1.5) for _ in leaves]
    total = sum(weights)
    counts = [math.floor(people * w / total) for w in weights]
    for i in rng.sample(range(len(leaves)), people - sum(counts)):
        counts[i] += 1
    person_unit = [leaf for leaf, c in zip(leaves, counts, strict=True) for _ in range(c)]

    org = Org(units=units, roles=[], type_names=[], people=[])
    org.subtree_people = [[] for _ in units]
    for p, leaf in enumerate(person_unit):
        node: int | None = leaf
        while node is not None:
            org.subtree_people[node].append(p)
            node = units[node].parent

    # --- наряды: у узлов уровней 0…PEOPLE_LEVEL, мест в день ∝ людям поддерева ------------
    days_in_month = len(month_days(month))
    for level in range(PEOPLE_LEVEL + 1):
        for node in org.at_level(level):
            per_day = load * LEVEL_SHARE[level] * len(org.subtree_people[node]) / days_in_month
            if per_day < 0.3:
                continue
            max_head = 3 if level < PEOPLE_LEVEL else 2
            roles_count = max(1, round(per_day / ((1 + max_head) / 2)))
            types = max(1, math.ceil(roles_count / 2))
            first_type = len(org.type_names)
            for t in range(types):
                org.type_names.append(f"Наряд {units[node].name} №{t + 1}")
            for k in range(roles_count):
                start, duration, rest, weight = TEMPLATES[rng.randrange(len(TEMPLATES))]
                org.roles.append(
                    RoleDef(
                        type_index=first_type + k % types,
                        owner=node,
                        name=f"Роль {k + 1}",
                        headcount=rng.randint(1, max_head),
                        start=start,
                        duration=duration,
                        rest=rest,
                        weight=weight,
                    )
                )

    # --- люди: допуски к нарядам своей цепочки узлов, освобождения, лимиты ------------------
    first = month - dt.timedelta(days=HISTORY_DAYS)
    last = month_days(month)[-1]
    by_owner: dict[int, list[int]] = {}
    for r, role in enumerate(org.roles):
        by_owner.setdefault(role.owner, []).append(r)
    for leaf in person_unit:
        chain = []
        node_: int | None = leaf
        while node_ is not None:
            chain.append(node_)
            node_ = units[node_].parent
        clearances: dict[int, tuple[dt.date | None, dt.date | None]] = {}
        for owner in chain:
            own = by_owner.get(owner, [])
            share = min(0.6, 3 / max(1, len(own)))
            for r in own:
                if rng.random() < share:
                    valid_from = None if rng.random() < 0.95 else month + dt.timedelta(10)
                    clearances[r] = (valid_from, None)
        exemptions = []
        if rng.random() < 0.12:
            a = first + dt.timedelta(days=rng.randint(0, (last - first).days - 2))
            exemptions.append((a, min(last, a + dt.timedelta(days=rng.randint(2, 14)))))
        limit = None
        if rng.random() < 0.1:
            limit = (rng.randint(3, 6), rng.choice([None, 1, 2]))
        org.people.append(PersonDef(leaf, clearances, exemptions, limit))
    return org


def cleared_by_role(org: Org) -> list[list[int]]:
    result: list[list[int]] = [[] for _ in org.roles]
    for p, person in enumerate(org.people):
        for r in person.clearances:
            result[r].append(p)
    return result


def random_history(org: Org, month: dt.date, seed: int, fill: float = 0.6) -> list[Duty]:
    """Фон нагрузки: наряды прошлых 90 дней без проверки правил (как в `allocation.synthetic`)."""
    rng = random.Random(seed + 7)
    cleared = cleared_by_role(org)
    history = []
    for r, role in enumerate(org.roles):
        pool = cleared[r]
        if not pool:
            continue
        for back in range(HISTORY_DAYS, 0, -1):
            date = month - dt.timedelta(days=back)
            if rng.random() > fill:
                continue
            for p in rng.sample(pool, min(len(pool), role.headcount)):
                history.append(Duty(p, r, date))
    return history


def by_person(duties: Iterable[Duty]) -> dict[int, list[Duty]]:
    result: dict[int, list[Duty]] = {}
    for d in duties:
        result.setdefault(d.person, []).append(d)
    return result


def month_cells(org: Org, node: int, month: dt.date) -> list[tuple[dt.date, int]]:
    return [(d, r) for d in month_days(month) for r in org.roles_of(node)]


def cell_id(date: dt.date, role: int) -> str:
    return f"c{role}:{date.isoformat()}"


def snapshot(
    org: Org,
    node: int,
    month: dt.date,
    cells: Iterable[tuple[dt.date, int]],
    history: dict[int, list[Duty]],
) -> dict[str, Any]:
    """Снимок ADR-0013 для узла `node`: его поддерево, ячейки месяца, которые он закрывает
    сам (свои и принятые), и история нарядов людей поддерева за 90 дней."""
    days = [
        month - dt.timedelta(days=HISTORY_DAYS) + dt.timedelta(days=i)
        for i in range(HISTORY_DAYS + len(month_days(month)))
    ]
    day_index = {d: i for i, d in enumerate(days)}
    first, last = days[0], days[-1]

    subtree = org.descendants(node)
    unit_index = {u: i for i, u in enumerate(subtree)}
    units = [
        {
            "id": f"u{u}",
            "parent": None if u == node else unit_index[org.units[u].parent],  # type: ignore[index]
            "name": org.units[u].name,
        }
        for u in subtree
    ]

    cell_list = sorted(set(cells))
    role_ids = sorted({r for _, r in cell_list})
    role_index = {r: i for i, r in enumerate(role_ids)}
    roles = [_role(org, r) for r in role_ids]
    other = len(roles)  # «прочие наряды» — история по ролям вне снимка
    roles.append(
        {
            "id": "r-other",
            "duty_type_id": "t-other",
            "duty_type": "Прочие наряды",
            "name": "—",
            "headcount": 1,
            "start_time": "08:00:00",
            "duration_minutes": DAY,
            "rest_hours": 0,
            "load_weight": 1.0,
            "active": False,
        }
    )

    person_ids = org.subtree_people[node]
    person_index = {p: i for i, p in enumerate(person_ids)}
    people = []
    for p in person_ids:
        person = org.people[p]
        c = []
        for r, (valid_from, valid_to) in person.clearances.items():
            if r in role_index:
                c.append(
                    [
                        role_index[r],
                        None if valid_from is None else day_index.get(valid_from, 0),
                        None if valid_to is None else day_index.get(valid_to, len(days) - 1),
                    ]
                )
        x = [
            [day_index[max(a, first)], day_index[min(b, last)]]
            for a, b in person.exemptions
            if a <= last and b >= first
        ]
        people.append(
            {
                "id": f"p{p}",
                "u": unit_index[person.unit],
                "c": sorted(c),
                "x": x,
                "limit": list(person.limit) if person.limit else None,
            }
        )

    snap_cells = [
        {
            "id": cell_id(d, r),
            "d": day_index[d],
            "r": role_index[r],
            "s": 0,
            "e": 0,
            "origin": "own" if org.roles[r].owner == node else "incoming",
            "status": "none" if org.roles[r].owner == node else "accepted",
            "pinned": False,
            "parent": None,
        }
        for d, r in cell_list
    ]

    assignments = []
    duties = [d for p in person_ids for d in history.get(p, ())]
    for n, duty in enumerate(duties):
        if not first <= duty.date <= last:
            continue
        role = org.roles[duty.role]
        d = day_index[duty.date]
        begin = d * DAY + role.start_min
        finish = begin + role.duration
        occupied = (finish - 1) // DAY - d + 1
        assignments.append(
            {
                "id": f"a{n}",
                "p": person_index[duty.person],
                "cell": None,
                "d": d,
                "r": role_index.get(duty.role, other),
                "dt": f"t{role.type_index}",
                "t": [begin, finish],
                "rest": role.rest,
                "days": [d, d + occupied - 1],
                "load": occupied * role.weight,
                "pinned": False,
                "auto": True,
                "override": False,
            }
        )
    return {
        "snapshot_version": 1,
        "hash": f"exp:{node}:{month.isoformat()}",
        "created_at": "experiment",
        "timezone": "Europe/Moscow",
        "schedule": {"id": f"s{node}", "unit": 0, "month": month.isoformat(), "status": "draft"},
        "horizon": {
            "from": first.isoformat(),
            "to": last.isoformat(),
            "month_start": HISTORY_DAYS,
        },
        "days": [[d.isoformat(), day_kind(d)] for d in days],
        "units": units,
        "roles": roles,
        "people": people,
        "cells": snap_cells,
        "assignments": assignments,
    }


def _role(org: Org, r: int) -> dict[str, Any]:
    role = org.roles[r]
    return {
        "id": f"r{r}",
        "duty_type_id": f"t{role.type_index}",
        "duty_type": org.type_names[role.type_index],
        "name": role.name,
        "headcount": role.headcount,
        "start_time": role.start,
        "duration_minutes": role.duration,
        "rest_hours": role.rest,
        "load_weight": role.weight,
        "active": True,
    }


def parse_cell(cell: str) -> tuple[dt.date, int]:
    role, date = cell[1:].split(":")
    return dt.date.fromisoformat(date), int(role)
