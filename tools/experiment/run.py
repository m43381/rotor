"""Экспериментальный стенд фазы 5: расчёт экспериментов и отчёт `docs/experiments.md`.

    just experiment                      # всё: расчёт (десятки минут) и отчёт
    uv run --group experiment python -m tools.experiment.run --only e4
    uv run --group experiment python -m tools.experiment.run --report   # только отчёт

Эксперименты (методика — в отчёте):
- E1/E2 — вся организация сверху вниз, 1k / 5k / 20k / 50k человек, несколько seed:
  методы распределения людей (legacy, жадный, венгерский, локальный поиск, CP-SAT, auto)
  на одном и том же делегировании и способы распределения по подразделениям (legacy,
  Гамильтон + жадный, Сент-Лагю + min-cost flow) при одном методе для людей;
- E3 — подбор полупериода затухания: 6 месяцев подряд, итог месяца — история следующего;
- E4 — методы и их пределы на отдельных подзадачах: основа для порогов режима auto.

Сырые результаты — `docs/experiments/*.json` (детерминированы по seed, кроме замеров
времени и памяти), графики — `docs/experiments/*.png`.
"""

import argparse
import datetime as dt
import json
import random
import sys
import time
from concurrent.futures import Executor, ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from allocation.engine.config import make_config
from allocation.engine.metrics import fairness
from allocation.engine.solve import solve
from allocation.synthetic import generate_snapshot
from tools.experiment.org import Org, by_person, generate_org, month_days, random_history
from tools.experiment.pipeline import (
    UNIT_STRATEGIES,
    Result,
    assign,
    delegate,
    person_loads,
    run_pipeline,
    warmup,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "experiments"
MONTH = dt.date(2026, 11, 1)
WORKERS = 8
SCENARIOS = {"norm": 1.3, "deficit": 5.0}
# Размер организации → (seed, сценарии, методы людей)
E12_PLAN: dict[int, tuple[tuple[int, ...], tuple[str, ...], tuple[str, ...]]] = {
    1_000: ((1, 2, 3), ("norm", "deficit"), ("greedy", "hungarian", "local_search", "cpsat")),
    5_000: ((1, 2, 3), ("norm", "deficit"), ("greedy", "hungarian", "local_search", "cpsat")),
    20_000: ((1, 2), ("norm",), ("greedy", "hungarian", "local_search")),
    50_000: ((1,), ("norm",), ("greedy", "hungarian", "local_search")),
}
E3_HALF_LIVES: tuple[float | None, ...] = (14, 30, 60, 90, None)
E3_MONTHS = 6
E3_SIZE = 1_000
E3_LOAD = 3.0
E3_SEEDS = (1, 2)
E4_VARIANTS: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("greedy", "greedy", {}),
    ("hungarian", "hungarian", {}),
    ("ls_5k", "local_search", {"ls_iterations": 5_000}),
    ("ls_20k", "local_search", {"ls_iterations": 20_000}),
    ("ls_50k", "local_search", {"ls_iterations": 50_000}),
    ("ls_100k", "local_search", {"ls_iterations": 100_000}),
    ("cpsat_10s", "cpsat", {"cpsat_time_limit_s": 10, "cpsat_deterministic_time": 20}),
    ("cpsat_60s", "cpsat", {"cpsat_time_limit_s": 60, "cpsat_deterministic_time": 120}),
)


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def summary(result: Result, **extra: Any) -> dict[str, Any]:
    share = fairness(np.array(result.course_share)) if result.course_share else {}
    return {
        **extra,
        "units": result.units,
        "people": result.people,
        "places": result.places,
        "lost": result.lost_places,
        "filled": result.filled,
        "bound": result.bound,
        "violations": result.violations,
        "units_ms_sum": sum(result.units_ms),
        "units_ms_max": max(result.units_ms, default=0.0),
        "people_ms_sum": sum(result.people_ms),
        "people_ms_max": max(result.people_ms, default=0.0),
        "peak_mb": result.peak_mb,
        "fairness": result.fairness,
        "share_gini": share.get("gini"),
        "subproblems": result.subproblems,
    }


# --- E1/E2: вся организация ------------------------------------------------------------------


def e12(pool: Executor, plan: dict[int, Any]) -> list[dict[str, Any]]:
    rows = []
    for size, (seeds, scenarios, methods) in plan.items():
        for scenario in scenarios:
            for n, seed in enumerate(seeds):
                org = generate_org(size, seed, MONTH, SCENARIOS[scenario])
                hist = by_person(random_history(org, MONTH, seed))
                memory = n == 0
                kw: dict[str, Any] = {"seed": seed, "pool": pool, "memory": memory}
                tag = {"size": size, "scenario": scenario, "seed": seed, "nodes": len(org.units)}
                delegations = {}
                for units in UNIT_STRATEGIES:
                    t0 = time.perf_counter()
                    delegations[units] = delegate(org, MONTH, hist, units=units, **kw)
                    log(f"{size} {scenario} s{seed}: {units} {time.perf_counter() - t0:.0f} с")
                runs = [("sainte_lague_flow", m) for m in (*methods, "auto")]
                runs += [("legacy", "legacy"), ("legacy", "legacy_incremental")]
                runs += [("legacy", "local_search"), ("hamilton_greedy", "local_search")]
                for units, people in runs:
                    t0 = time.perf_counter()
                    result = assign(org, MONTH, delegations[units], people=people, **kw)
                    rows.append(summary(result, **tag))
                    log(
                        f"{size} {scenario} s{seed}: {units}/{people} "
                        f"{result.filled}/{result.places} за {time.perf_counter() - t0:.0f} с"
                    )
    return rows


# --- E3: затухание нагрузки -------------------------------------------------------------------


def add_months(month: dt.date, n: int) -> dt.date:
    k = month.month - 1 + n
    return dt.date(month.year + k // 12, k % 12 + 1, 1)


def reroll_exemptions(org: Org, month: dt.date, seed: int) -> None:
    """Освобождения месяца: короткие (болезнь, 2–14 дней) у 12 %, на весь месяц
    (командировка, отпуск) у 4 % — это и создаёт перекосы, которые выравнивает затухание."""
    rng = random.Random(seed * 1_000 + month.month * 13 + month.year)
    days = month_days(month)
    for person in org.people:
        person.exemptions = []
        x = rng.random()
        if x < 0.04:
            person.exemptions.append((days[0], days[-1]))
        elif x < 0.16:
            a = rng.randrange(len(days) - 2)
            person.exemptions.append((days[a], days[min(len(days) - 1, a + rng.randint(2, 14))]))


def e3(pool: Executor) -> list[dict[str, Any]]:
    rows = []
    for seed in E3_SEEDS:
        for half_life in E3_HALF_LIVES:
            org = generate_org(E3_SIZE, seed, MONTH, E3_LOAD)
            eligible = np.array([bool(p.clearances) for p in org.people])
            history = random_history(org, MONTH, seed)
            config = {"half_life_days": half_life or 1e6}
            monthly: list[dict[str, Any]] = []
            duties = []
            for m in range(E3_MONTHS):
                month = add_months(MONTH, m)
                reroll_exemptions(org, month, seed)
                result = run_pipeline(
                    org,
                    month,
                    history,
                    units="sainte_lague_flow",
                    people="auto",
                    seed=seed,
                    pool=pool,
                    config=config,
                )
                history += result.duties
                duties += result.duties
                _, load, _ = person_loads(org, duties)
                month_count, month_load, _ = person_loads(org, result.duties)
                monthly.append(
                    {
                        "month": month.isoformat(),
                        "filled": result.filled,
                        "places": result.places,
                        "month_load": fairness(month_load[eligible]),
                        "month_count": fairness(month_count[eligible]),
                        "cumulative": fairness(load[eligible]),
                    }
                )
            count, load, holiday = person_loads(org, duties)
            cumulative = fairness(load[eligible])
            rows.append(
                {
                    "seed": seed,
                    "half_life": half_life,
                    "months": monthly,
                    "cumulative": cumulative,
                    "cumulative_count": fairness(count[eligible]),
                    "cumulative_holiday": fairness(holiday[eligible]),
                }
            )
            log(f"E3 s{seed} T½={half_life}: σ за 6 мес. {cumulative['std']}")
    return rows


# --- E4: методы на подзадачах -----------------------------------------------------------------


def method_task(snap: dict[str, Any], method: str, extra: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    sol = solve(snap, make_config({"method": method, **extra}), 1)
    ms = (time.perf_counter() - t0) * 1000
    m = sol["metrics"]
    return {
        "places": m["places"],
        "filled": m["filled"],
        "bound": m["upper_bound"],
        "pairs": m["pairs"],
        "people": len(snap["people"]),
        "ms": ms,
        "std": m["fairness_decayed"]["std"],
        "status": sol["method_info"].get("status"),
    }


def e4(pool: Executor) -> list[dict[str, Any]]:
    problems: list[tuple[str, dict[str, Any]]] = []
    for people in (60, 150, 300):
        for seed in (1, 2):
            snap = generate_snapshot(people=people, duty_types=6, seed=seed)
            problems.append((f"синтетика {people}", snap))
    for size in (1_000, 5_000):
        org = generate_org(size, 1, MONTH, SCENARIOS["deficit"])
        hist = by_person(random_history(org, MONTH, 1))
        d = delegate(org, MONTH, hist, units="sainte_lague_flow", seed=1, pool=pool)
        problems += [(f"курс, оргструктура {size}", s) for s in d.snapshots]
    futures = [
        (source, index, name, pool.submit(method_task, snap, method, extra))
        for index, (source, snap) in enumerate(problems)
        for name, method, extra in E4_VARIANTS
    ]
    rows = []
    for source, index, name, fut in futures:
        rows.append({"source": source, "problem": index, "variant": name, **fut.result()})
    log(f"E4: {len(problems)} подзадач × {len(E4_VARIANTS)} вариантов")
    return rows


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", default="e4,e12,e3", help="какие эксперименты считать")
    parser.add_argument("--report", action="store_true", help="только отчёт по готовым данным")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if not args.report:
        with ProcessPoolExecutor(WORKERS, initializer=warmup) as pool:
            for name in args.only.split(","):
                t0 = time.perf_counter()
                data: list[dict[str, Any]]
                if name == "e12":
                    data = e12(pool, E12_PLAN)
                elif name == "e3":
                    data = e3(pool)
                elif name == "e4":
                    data = e4(pool)
                else:
                    raise SystemExit(f"Неизвестный эксперимент: {name}")
                (OUT / f"{name}.json").write_text(
                    json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
                )
                log(f"{name}: {time.perf_counter() - t0:.0f} с")
    from tools.experiment.report import render

    render(OUT, ROOT / "docs" / "experiments.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
