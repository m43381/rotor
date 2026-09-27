"""Бенчмарк движка распределения (фаза 4): время по уровням воронки, память, недокомплект,
справедливость на синтетических снимках 1k / 5k / 20k / 50k человек.

Движок — чистая функция, поэтому замер без сервисов и БД: снимок строится генератором
`allocation.synthetic`, решение проверяется независимой проверкой `allocation.engine.verify`.

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


def run(people: int, kind: str) -> dict[str, Any]:
    children = max(4, people // 1_000)
    snap = generate_snapshot(
        people=people, children=children, duty_types=DUTY_TYPES, clearance_share=0.25, seed=SEED
    )
    config = make_config({"kind": kind})
    tracemalloc.start()
    t0 = time.perf_counter()
    sol = solve(snap, config, seed=SEED)
    total = (time.perf_counter() - t0) * 1000
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    errors = verify(snap, sol) if kind == "people" else verify_units(snap, sol)
    if errors:
        raise SystemExit(f"{people} {kind}: нарушения {errors[:3]}")
    m = sol["metrics"]
    return {
        "people": people,
        "kind": kind,
        "cells": m["cells"],
        "places": m["places"],
        "filled": m["filled"],
        "shortage": m["shortage"],
        "bound": m["upper_bound"],
        "total_ms": total,
        "levels": m["timings_ms"],
        "peak_mb": peak / 2**20,
        "fair": m["fairness"],
        "max_duties": m["fairness_count"]["max"] if kind == "people" else 0,
        "deficits": len(sol["deficits"]),
    }


def render(rows: list[dict[str, Any]]) -> str:
    def num(x: int) -> str:
        return f"{x:,}".replace(",", " ")

    lines = [
        "# Бенчмарк движка распределения (фаза 4)",
        "",
        "> Сгенерировано `just bench-allocation` (tools/bench/engine.py). "
        f"{platform.system()} {platform.machine()}, Python {platform.python_version()}, "
        f"numpy {np.__version__}. Синтетические снимки `allocation.synthetic`: "
        f"{DUTY_TYPES} нарядов (20 ролей, 6 ч — 3 суток), допуски к 25 % ролей, освобождения "
        f"у 12 %, лимиты у 20 %, история 90 дней. Метод уровня 4 — жадный в порядке MRV. "
        f"Каждое решение проверено независимой проверкой ограничений: нарушений нет. Seed {SEED}.",
        "",
        "## Люди по ячейкам",
        "",
        "| Людей | Ячеек | Мест | Закрыто | Граница (max-flow) | Всего, мс | Ур. 1, мс | "
        "Ур. 2, мс | Ур. 3–4, мс | Пик памяти, МБ | Мест на допущенного | Нарядов у человека, "
        "макс. | Джини (нагрузка) | Джайн (нагрузка) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in (x for x in rows if x["kind"] == "people"):
        lv = r["levels"]
        bound = "—" if r["bound"] is None else num(r["bound"])
        lines.append(
            f"| {num(r['people'])} | {num(r['cells'])} | {num(r['places'])} | {num(r['filled'])} | "
            f"{bound} | {r['total_ms']:.0f} | {lv['level1']:.0f} | {lv['level2']:.0f} | "
            f"{lv['level4']:.0f} | {r['peak_mb']:.0f} | "
            f"{r['places'] / max(1, r['fair']['people']):.2f} | "
            f"{r['max_duties']:.0f} | {r['fair']['gini']} | "
            f"{r['fair']['jain']} |"
        )
    lines += [
        "",
        "## Ячейки по подразделениям",
        "",
        "| Людей | Подразделений | Ячеек | Распределено | Всего, мс | Пик памяти, МБ | "
        "Джини долей к ёмкости |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in (x for x in rows if x["kind"] == "units"):
        lines.append(
            f"| {num(r['people'])} | {max(4, r['people'] // 1_000)} | {num(r['cells'])} | "
            f"{num(r['filled'])} | {r['total_ms']:.0f} | {r['peak_mb']:.0f} | {r['fair']['gini']} |"
        )
    lines += [
        "",
        "Время замерено под `tracemalloc` (он замедляет выполнение); без него решение быстрее.",
        "",
        "Нагрузка — нарядо-сутки × вес наряда, в выходной × 1,5. При 1 000 человек мест меньше, "
        "чем людей, и у человека не больше двух нарядов за месяц (двое — там, где к роли "
        "допущено мало людей). Джини по нагрузке около 0,48 здесь — из-за четверти людей без "
        "нарядов в этом месяце и разного веса нарядов (6 ч против трёх суток), а не из-за "
        "перекоса выбора: при допуске всех ко всем ролям каждый получает не больше одного наряда.",
        "",
        "Справедливость считается по всем людям, допущенным хотя бы к одной роли области. Число "
        "ячеек в снимках одинаковое, поэтому на 20–50 тыс. человек мест на допущенного меньше "
        "0,1: большинство без нарядов, и Джини закономерно близок к 1. Показатель осмыслен, когда "
        "мест в месяц сопоставимо с числом людей — как в реальной подзадаче подразделения "
        "(1 000 человек здесь). Крупные размеры показывают, как время и память растут с числом "
        "людей: после декомпозиции по дереву (уровень 0) такие подзадачи на практике не "
        "возникают.",
        "Граница — строгий максимум закрываемых мест по потоку без учёта отдыха и лимитов: "
        "разница «граница − закрыто» — материал для сравнения с точными методами фазы 5.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rows = []
    for n in SIZES:
        for kind in ("people", "units"):
            rows.append(run(n, kind))
            r = rows[-1]
            print(
                f"  {n} {kind}: {r['total_ms']:.0f} мс, закрыто {r['filled']}/{r['places']}",
                flush=True,
            )
    OUT.write_text(render(rows), encoding="utf-8", newline="\n")
    print(f"Результаты: {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
