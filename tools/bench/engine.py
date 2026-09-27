"""Бенчмарк движка распределения (фазы 4–5): методы уровня 4 на синтетических снимках
1k / 5k / 20k / 50k человек — время, память, закрытые места, справедливость.

Движок — чистая функция, поэтому замер без сервисов и БД: снимок строится генератором
`allocation.synthetic`, каждое решение проверяется независимой проверкой `engine.verify`.
Полное сравнение с legacy и на глубоком дереве — экспериментальный стенд (`just experiment`).

    just bench-allocation        # → docs/benchmarks/allocation.md
"""

import platform
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

import numpy as np

from allocation.engine.config import make_config
from allocation.engine.solve import solve
from allocation.engine.verify import verify, verify_units
from allocation.synthetic import generate_snapshot

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "benchmarks" / "allocation.md"
SIZES = (1_000, 5_000, 20_000, 50_000)
DUTY_TYPES = 10  # 20 ролей: ≈ 600 ячеек в месяц
SEED = 20260927
PEOPLE_METHODS = ("greedy", "hungarian", "local_search", "auto")
UNIT_METHODS = ("greedy", "flow")
NOTE = (
    "Мест в снимках одинаково (750), поэтому от 5 000 человек мест на допущенного меньше "
    "одного: у каждого не больше одного наряда, и справедливость у всех методов совпадает. "
    "Методы различаются, когда людей примерно столько же, сколько мест (строка 1 000): там "
    "венгерский и локальный поиск выравнивают нагрузку лучше жадного. Полное сравнение на "
    "реалистичных подзадачах, с legacy и на глубоком дереве — экспериментальный стенд "
    "(`docs/experiments.md`). Время первой строки включает загрузку scipy и OR-Tools."
)


def snapshot(people: int) -> dict[str, Any]:
    return generate_snapshot(
        people=people,
        children=max(4, people // 1_000),
        duty_types=DUTY_TYPES,
        clearance_share=0.25,
        seed=SEED,
    )


def run(snap: dict[str, Any], people: int, kind: str, method: str) -> dict[str, Any]:
    override: dict[str, Any] = {"kind": kind}
    if kind == "people":
        override["method"] = method
    else:
        override["units_method"] = method
    config = make_config(override)
    tracemalloc.start()
    t0 = time.perf_counter()
    sol = solve(snap, config, seed=SEED)
    total = (time.perf_counter() - t0) * 1000
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    errors = verify(snap, sol) if kind == "people" else verify_units(snap, sol)
    if errors:
        raise SystemExit(f"{people} {kind} {method}: нарушения {errors[:3]}")
    m = sol["metrics"]
    return {
        "people": people,
        "kind": kind,
        "method": method,
        "used": sol["method"],
        "places": m["places"],
        "filled": m["filled"],
        "bound": m["upper_bound"],
        "pairs": m.get("pairs"),
        "total_ms": total,
        "peak_mb": peak / 2**20,
        "fair": m.get("fairness_decayed", m["fairness"]),
        "proved": sol["method_info"].get("filled_optimal"),
    }


def render(rows: list[dict[str, Any]]) -> str:
    def num(x: int | None) -> str:
        return "—" if x is None else f"{x:,}".replace(",", " ")

    lines = [
        "# Бенчмарк движка распределения",
        "",
        "> Сгенерировано `just bench-allocation` (tools/bench/engine.py). "
        f"{platform.system()} {platform.machine()}, Python {platform.python_version()}, "
        f"numpy {np.__version__}. Синтетические снимки `allocation.synthetic`: "
        f"{DUTY_TYPES} нарядов (20 ролей, 6 ч — 3 суток, 750 мест в месяц), допуски к 25 % "
        "ролей, освобождения у 12 %, лимиты у 20 %, история 90 дней. Настройки по умолчанию "
        "(`allocation/config/default.yaml`). Каждое решение проверено независимой проверкой "
        f"ограничений: нарушений нет. Время — под `tracemalloc`. Seed {SEED}.",
        "",
        "## Люди по ячейкам",
        "",
        "Справедливость — по нагрузке с затуханием, включая прошлые наряды (то, что "
        "выравнивают локальный поиск и CP-SAT), по людям, допущенным хотя бы к одной роли.",
        "",
        "| Людей | Метод | Выбран | Пар «человек × место» | Закрыто | Граница | Время, мс | "
        "Память, МБ | σ нагрузки | Джини | Джайн |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in (x for x in rows if x["kind"] == "people"):
        f = r["fair"]
        lines.append(
            f"| {num(r['people'])} | {r['method']} | {r['used']} | {num(r['pairs'])} | "
            f"{num(r['filled'])} из {num(r['places'])} | {num(r['bound'])} | "
            f"{r['total_ms']:.0f} | {r['peak_mb']:.0f} | {f['std']} | {f['gini']} | {f['jain']} |"
        )
    lines += [
        "",
        "## Ячейки по подразделениям",
        "",
        "| Людей | Подразделений | Метод | Ячеек | Распределено | Время, мс | Память, МБ | "
        "Джини долей к ёмкости |",
        "|---:|---:|---|---:|---:|---:|---:|---:|",
    ]
    for r in (x for x in rows if x["kind"] == "units"):
        lines.append(
            f"| {num(r['people'])} | {max(4, r['people'] // 1_000)} | {r['method']} | "
            f"{num(r['places'])} | {num(r['filled'])} | {r['total_ms']:.0f} | "
            f"{r['peak_mb']:.0f} | {r['fair']['gini']} |"
        )
    lines += [
        "",
        "`auto` (open-questions №46): локальный поиск со стартом из лучшего из жадного и "
        "венгерского; если закрыто столько мест, сколько даёт строгая граница max-flow, покрытие "
        "доказано максимальным и расчёт заканчивается, иначе на небольшой задаче подключается "
        "CP-SAT. На очень больших задачах — жадный метод.",
        "",
        NOTE,
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rows = []
    for n in SIZES:
        snap = snapshot(n)
        for method in PEOPLE_METHODS:
            rows.append(run(snap, n, "people", method))
            r = rows[-1]
            print(
                f"  {n} {method}: {r['total_ms']:.0f} мс, {r['filled']}/{r['places']}", flush=True
            )
        for method in UNIT_METHODS:
            rows.append(run(snap, n, "units", method))
    OUT.write_text(render(rows), encoding="utf-8", newline="\n")
    print(f"Результаты: {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
