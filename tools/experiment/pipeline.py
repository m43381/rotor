"""Иерархический прогон сверху вниз — декомпозиция уровня 0 на всей организации.

Уровни 0…PEOPLE_LEVEL−1: каждый узел распределяет ячейки, которые держит (свои и полученные
сверху), по прямым дочерним. Уровень PEOPLE_LEVEL: каждый узел назначает людей своего
поддерева. Подзадачи одного уровня независимы (разные поддеревья) и решаются параллельно
в процессах — как их решали бы операторы разных подразделений.

Каждая подзадача — чистая функция «снимок → решение»; замеры (время, пик памяти под
`tracemalloc`) делаются внутри процесса-исполнителя.
"""

import datetime as dt
import time
import tracemalloc
from collections import defaultdict
from concurrent.futures import Executor
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from allocation.engine.config import make_config
from allocation.engine.metrics import fairness
from allocation.engine.people import prepare
from allocation.engine.problem import load_problem
from allocation.engine.solve import solve
from allocation.engine.verify import verify
from tools.experiment import legacy
from tools.experiment.org import (
    PEOPLE_LEVEL,
    Duty,
    Org,
    by_person,
    day_kind,
    month_cells,
    parse_cell,
    snapshot,
)

UNIT_STRATEGIES = {
    "legacy": None,
    "hamilton_greedy": {"apportionment": "hamilton", "units_method": "greedy"},
    "sainte_lague_flow": {"apportionment": "sainte_lague", "units_method": "flow"},
}
PEOPLE_METHODS = (
    "legacy",
    "legacy_incremental",
    "greedy",
    "hungarian",
    "local_search",
    "cpsat",
    "auto",
)
VIOLATIONS = {
    "два наряда в одни сутки": "same_day",
    "не соблюдён отдых": "rest",
    "лимит": "limit",
    "освобождён": "exempt",
    "допуск": "clearance",
}


def _measure(fn: Any, memory: bool) -> tuple[Any, float, float]:
    """Время — без `tracemalloc` (он замедляет numpy-код сильнее, чем чистый Python legacy,
    и исказил бы сравнение); пик памяти — отдельным повтором под `tracemalloc`."""
    t0 = time.perf_counter()
    result = fn()
    ms = (time.perf_counter() - t0) * 1000
    peak = 0
    if memory:
        tracemalloc.start()
        fn()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    return result, ms, peak / 2**20


def warmup() -> None:
    """Инициализатор процесса: импорт scipy и OR-Tools и первый вызов каждого метода — вне
    замеров."""
    from allocation.synthetic import generate_snapshot

    snap = generate_snapshot(people=40, children=2, groups_per_child=1, duty_types=2, seed=1)
    for method in ("greedy", "hungarian", "local_search", "cpsat"):
        solve(snap, make_config({"method": method, "ls_iterations": 100}), 1)
    for kind in ("hamilton_greedy", "sainte_lague_flow"):
        solve(snap, make_config({"kind": "units", **(UNIT_STRATEGIES[kind] or {})}), 1)


def units_task(
    snap: dict[str, Any], strategy: str, config: dict[str, Any], seed: int, memory: bool
) -> Any:
    def run() -> list[dict[str, Any]]:
        if strategy == "legacy":
            solution = legacy.units(snap)
        else:
            cfg = make_config({**config, **(UNIT_STRATEGIES[strategy] or {}), "kind": "units"})
            solution = solve(snap, cfg, seed)
        delegations: list[dict[str, Any]] = solution["delegations"]
        return delegations

    delegations, ms, peak = _measure(run, memory)
    return [(d["cell"], d["unit"]) for d in delegations], ms, peak


def people_task(
    snap: dict[str, Any], method: str, config: dict[str, Any], seed: int, memory: bool
) -> Any:
    def run() -> dict[str, Any]:
        if method in ("legacy", "legacy_incremental"):
            return legacy.people(snap, incremental=method == "legacy_incremental")
        return solve(snap, make_config({**config, "kind": "people", "method": method}), seed)

    solution, ms, peak = _measure(run, memory)
    violations: dict[str, int] = defaultdict(int)
    for error in verify(snap, solution):
        key = next((v for k, v in VIOLATIONS.items() if k in error), "other")
        violations[key] += 1
    if "metrics" in solution:
        m = solution["metrics"]
        places, bound, pairs = m["places"], m["upper_bound"], m["pairs"]
    else:  # legacy: граница и размер — той же подготовкой, что у движка (вне замера)
        prep = prepare(load_problem(snap), make_config({**config, "kind": "people"}), seed)
        places, bound, pairs = sum(prep.need.values()), prep.bound, prep.pairs
    return {
        "picks": [(a["cell"], a["person"]) for a in solution["assignments"]],
        "used": solution.get("method", method),
        "proved": (solution.get("method_info") or {}).get("filled_optimal", False),
        "places": places,
        "bound": bound,
        "pairs": pairs,
        "violations": dict(violations),
        "ms": ms,
        "peak_mb": peak,
        "people": len(snap["people"]),
    }


@dataclass
class Delegation:
    """Итог уровней делегирования: что досталось узлам уровня PEOPLE_LEVEL."""

    units: str
    places: int = 0
    lost_places: int = 0  # ячейки, которые не удалось передать ни одному дочернему
    lost_by_level: dict[int, int] = field(default_factory=dict)
    units_ms: list[float] = field(default_factory=list)
    peak_mb: float = 0.0
    nodes: list[int] = field(default_factory=list)
    snapshots: list[dict[str, Any]] = field(default_factory=list)  # задачи людей по узлам


@dataclass
class Result:
    units: str
    people: str
    places: int = 0
    lost_places: int = 0
    lost_by_level: dict[int, int] = field(default_factory=dict)
    filled: int = 0
    bound: int = 0
    violations: dict[str, int] = field(default_factory=dict)
    units_ms: list[float] = field(default_factory=list)
    people_ms: list[float] = field(default_factory=list)
    peak_mb: float = 0.0
    subproblems: list[dict[str, Any]] = field(default_factory=list)
    duties: list[Duty] = field(default_factory=list)
    course_share: list[float] = field(default_factory=list)  # мест на допущенного по курсам
    fairness: dict[str, dict[str, float]] = field(default_factory=dict)


def delegate(
    org: Org,
    month: dt.date,
    history: dict[int, list[Duty]],
    *,
    units: str,
    seed: int,
    pool: Executor,
    config: dict[str, Any] | None = None,
    memory: bool = False,
) -> Delegation:
    config = config or {}
    result = Delegation(units=units)
    at_node: dict[int, list[tuple[dt.date, int]]] = defaultdict(list)
    for level in range(PEOPLE_LEVEL + 1):
        for node in org.at_level(level):
            at_node[node].extend(month_cells(org, node, month))
    result.places = sum(org.roles[r].headcount for cells in at_node.values() for _, r in cells)

    for level in range(PEOPLE_LEVEL):
        nodes = [n for n in org.at_level(level) if at_node[n] and org.units[n].children]
        snaps = [snapshot(org, n, month, at_node[n], history) for n in nodes]
        futures = [pool.submit(units_task, s, units, config, seed, memory) for s in snaps]
        for node, fut in zip(nodes, futures, strict=True):
            delegations, ms, peak = fut.result()
            result.units_ms.append(ms)
            result.peak_mb = max(result.peak_mb, peak)
            given = set()
            for cell, unit in delegations:
                at_node[int(unit[1:])].append(parse_cell(cell))
                given.add(cell)
            lost = sum(
                org.roles[r].headcount
                for d, r in at_node[node]
                if f"c{r}:{d.isoformat()}" not in given
            )
            result.lost_places += lost
            result.lost_by_level[level] = result.lost_by_level.get(level, 0) + lost
            at_node[node] = []

    result.nodes = [n for n in org.at_level(PEOPLE_LEVEL) if at_node[n]]
    result.snapshots = [snapshot(org, n, month, at_node[n], history) for n in result.nodes]
    return result


def assign(
    org: Org,
    month: dt.date,
    delegation: Delegation,
    *,
    people: str,
    seed: int,
    pool: Executor,
    config: dict[str, Any] | None = None,
    memory: bool = False,
) -> Result:
    config = config or {}
    result = Result(
        units=delegation.units,
        people=people,
        places=delegation.places,
        lost_places=delegation.lost_places,
        lost_by_level=delegation.lost_by_level,
        units_ms=delegation.units_ms,
        peak_mb=delegation.peak_mb,
    )
    futures = [
        pool.submit(people_task, s, people, config, seed, memory) for s in delegation.snapshots
    ]
    for node, fut in zip(delegation.nodes, futures, strict=True):
        out = fut.result()
        result.people_ms.append(out["ms"])
        result.peak_mb = max(result.peak_mb, out["peak_mb"])
        result.filled += len(out["picks"])
        result.bound += out["bound"] or 0
        for k, v in out["violations"].items():
            result.violations[k] = result.violations.get(k, 0) + v
        result.subproblems.append(
            {k: out[k] for k in ("used", "proved", "places", "bound", "pairs", "ms", "people")}
            | {"filled": len(out["picks"])}
        )
        for cell, person in out["picks"]:
            date, role = parse_cell(cell)
            result.duties.append(Duty(int(person[1:]), role, date))
        eligible = sum(1 for p in org.subtree_people[node] if org.people[p].clearances)
        result.course_share.append(out["places"] / max(1, eligible))
    result.fairness = month_fairness(org, month, result.duties)
    return result


def run_pipeline(
    org: Org,
    month: dt.date,
    history: list[Duty],
    *,
    units: str,
    people: str,
    seed: int,
    pool: Executor,
    config: dict[str, Any] | None = None,
    memory: bool = False,
) -> Result:
    hist = by_person(history)
    kw: dict[str, Any] = {"seed": seed, "pool": pool, "config": config, "memory": memory}
    return assign(org, month, delegate(org, month, hist, units=units, **kw), people=people, **kw)


def person_loads(
    org: Org, duties: list[Duty], months: set[tuple[int, int]] | None = None
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """По людям: число нарядов, нагрузка (нарядо-сутки × вес), нарядов в выходные."""
    n = len(org.people)
    count, load, holiday = np.zeros(n), np.zeros(n), np.zeros(n)
    for d in duties:
        if months is not None and (d.date.year, d.date.month) not in months:
            continue
        role = org.roles[d.role]
        occupied = (role.start_min + role.duration - 1) // 1440 + 1
        count[d.person] += 1
        load[d.person] += occupied * role.weight
        holiday[d.person] += day_kind(d.date) != "workday"
    return count, load, holiday


def month_fairness(org: Org, month: dt.date, duties: list[Duty]) -> dict[str, dict[str, float]]:
    eligible = np.array([bool(p.clearances) for p in org.people])
    count, load, holiday = person_loads(org, duties, {(month.year, month.month)})
    return {
        "count": fairness(count[eligible]),
        "load": fairness(load[eligible]),
        "holiday": fairness(holiday[eligible]),
    }
