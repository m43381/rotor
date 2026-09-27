"""Отчёт экспериментального стенда: `docs/experiments.md` и графики PNG по данным
`docs/experiments/*.json` (их пишет `tools.experiment.run`).

Числа в таблицах — средние по seed; время и память — замеры конкретной машины, остальное
детерминировано. Выводы в отчёте пишутся по данным, а не заранее: формулировки собираются
из тех же средних, что и таблицы.
"""

import json
import platform
from collections import defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import numpy as np

METHOD_NAMES = {
    "legacy": "legacy (как в старой системе)",
    "legacy_incremental": "legacy со счётчиками по ходу",
    "greedy": "жадный MRV",
    "hungarian": "венгерский по дням",
    "local_search": "локальный поиск",
    "cpsat": "CP-SAT",
    "auto": "auto",
}
UNIT_NAMES = {
    "legacy": "legacy (ротация)",
    "hamilton_greedy": "Гамильтон + жадный",
    "sainte_lague_flow": "Сент-Лагю + min-cost flow",
}
SCENARIO_NAMES = {"norm": "обычная нагрузка", "deficit": "дефицит людей"}
VIOLATION_NAMES = {
    "same_day": "два наряда в сутки",
    "rest": "без отдыха",
    "limit": "сверх лимита",
    "exempt": "освобождённые",
    "clearance": "без допуска",
    "other": "прочие",
}
E4_NAMES = {
    "greedy": "жадный",
    "hungarian": "венгерский",
    "ls_5k": "лок. поиск 5 тыс.",
    "ls_20k": "лок. поиск 20 тыс.",
    "ls_50k": "лок. поиск 50 тыс.",
    "ls_100k": "лок. поиск 100 тыс.",
    "cpsat_10s": "CP-SAT 10 с",
    "cpsat_60s": "CP-SAT 60 с",
}


def num(x: float | None, digits: int = 0) -> str:
    if x is None:
        return "—"
    text = f"{x:,.{digits}f}".replace(",", " ")
    return text.replace(".", ",")


def mean(values: Iterable[float | None]) -> float | None:
    items = [v for v in values if v is not None]
    return float(np.mean(items)) if items else None


def group(rows: list[dict[str, Any]], *keys: str) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    result: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        result[tuple(row[k] for k in keys)].append(row)
    return result


def load(data_dir: Path, name: str) -> list[dict[str, Any]] | None:
    path = data_dir / f"{name}.json"
    if not path.exists():
        return None
    data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _plt() -> Any:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"figure.dpi": 120, "font.size": 9, "axes.grid": True, "grid.alpha": 0.3})
    return plt


def _save(fig: Any, path: Path) -> None:
    fig.tight_layout()
    # Без метаданных с датой — PNG меняется, только если меняются данные
    fig.savefig(path, metadata={"Software": None})
    fig.clf()


# --- E1/E2 ----------------------------------------------------------------------------------


def _e12_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def avg(fn: Callable[[dict[str, Any]], float | None]) -> float | None:
        return mean(fn(r) for r in rows)

    violations: dict[str, float] = defaultdict(float)
    for r in rows:
        for k, v in r["violations"].items():
            violations[k] += v / len(rows)
    return {
        "places": avg(lambda r: r["places"]),
        "lost": avg(lambda r: r["lost"]),
        "filled": avg(lambda r: r["filled"]),
        "bound": avg(lambda r: r["bound"]),
        "coverage": avg(lambda r: 100 * r["filled"] / r["places"]),
        "violations": dict(violations),
        "violations_total": sum(violations.values()),
        "std": avg(lambda r: r["fairness"]["load"]["std"]),
        "gini": avg(lambda r: r["fairness"]["load"]["gini"]),
        "jain": avg(lambda r: r["fairness"]["load"]["jain"]),
        "range": avg(lambda r: r["fairness"]["count"]["range"]),
        "holiday_std": avg(lambda r: r["fairness"]["holiday"]["std"]),
        "holiday_range": avg(lambda r: r["fairness"]["holiday"]["range"]),
        "share_gini": avg(lambda r: r["share_gini"]),
        "units_sum": avg(lambda r: r["units_ms_sum"] / 1000),
        "units_max": avg(lambda r: r["units_ms_max"] / 1000),
        "people_sum": avg(lambda r: r["people_ms_sum"] / 1000),
        "people_max": avg(lambda r: r["people_ms_max"] / 1000),
        "peak": max((r["peak_mb"] for r in rows if r["peak_mb"]), default=None),
        "nodes": avg(lambda r: r["nodes"]),
        "courses": avg(lambda r: len(r["subproblems"])),
        "proved": avg(lambda r: sum(s["proved"] for s in r["subproblems"])),
        "used": sorted({s["used"] for r in rows for s in r["subproblems"]}),
    }


def _violations_text(v: dict[str, float]) -> str:
    if not v:
        return "0"
    parts = [f"{VIOLATION_NAMES.get(k, k)} {num(x)}" for k, x in sorted(v.items()) if x]
    return f"{num(sum(v.values()))} ({', '.join(parts)})"


PEOPLE_ORDER = ("legacy", "legacy_incremental", "greedy", "hungarian", "local_search", "cpsat")


def e12_sections(rows: list[dict[str, Any]], data_dir: Path) -> tuple[list[str], dict[str, Any]]:
    plt = _plt()
    agg = {k: _e12_row(v) for k, v in group(rows, "size", "scenario", "units", "people").items()}
    sizes = sorted({r["size"] for r in rows})
    scenarios = [s for s in SCENARIO_NAMES if any(r["scenario"] == s for r in rows)]
    facts: dict[str, Any] = {"agg": agg, "sizes": sizes}
    out = [
        "## E1. Методы распределения людей",
        "",
        "Делегирование одно и то же (Сент-Лагю + min-cost flow), меняется только метод "
        "распределения людей в курсах. Отдельно — legacy целиком: его распределение по "
        "подразделениям и его же распределение людей. «Граница» — сумма строгих границ "
        "max-flow по курсам: больше закрыть нельзя, но граница не учитывает отдых и лимиты "
        "и поэтому может быть недостижима. Справедливость — по нагрузке за месяц "
        "(нарядо-сутки × вес) среди людей, допущенных хотя бы к одному наряду; размах — "
        "в числе нарядов. Время — сумма по подзадачам (процессорное) и самая долгая "
        "подзадача (столько ждёт оператор одного курса).",
        "",
    ]
    for size in sizes:
        for scenario in scenarios:
            keys = [
                ("sainte_lague_flow", p)
                for p in (*PEOPLE_ORDER[2:], "auto")
                if (size, scenario, "sainte_lague_flow", p) in agg
            ]
            keys = [("legacy", "legacy"), ("legacy", "legacy_incremental"), *keys]
            keys = [k for k in keys if (size, scenario, *k) in agg]
            if not keys:
                continue
            first = agg[(size, scenario, *keys[0])]
            seeds = len(group([r for r in rows if r["size"] == size], "seed"))
            out += [
                f"### {num(size)} человек, {SCENARIO_NAMES[scenario]}",
                "",
                f"{num(first['nodes'])} подразделений, {num(first['courses'])} курсов, "
                f"мест в месяц {num(first['places'])}; seed: {seeds}.",
                "",
                "| Распределение по подразделениям / людей | Закрыто | % | Граница | "
                "Нарушения | σ нагрузки | Джини | Джайн | Размах | σ выходных | "
                "Время Σ, с | Макс. подзадача, с | Память, МБ |",
                "|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
            for units, people in keys:
                a = agg[(size, scenario, units, people)]
                label = (
                    f"legacy / {METHOD_NAMES[people]}"
                    if units == "legacy"
                    else METHOD_NAMES[people]
                    + (f" ({', '.join(a['used'])})" if people == "auto" else "")
                )
                out.append(
                    f"| {label} | {num(a['filled'])} | {num(a['coverage'], 1)} | "
                    f"{num(a['bound'])} | {_violations_text(a['violations'])} | "
                    f"{num(a['std'], 2)} | {num(a['gini'], 3)} | {num(a['jain'], 3)} | "
                    f"{num(a['range'], 1)} | {num(a['holiday_std'], 2)} | "
                    f"{num(a['people_sum'], 1)} | {num(a['people_max'], 2)} | "
                    f"{num(a['peak'])} |"
                )
            out.append("")

    # График: самая долгая подзадача по размеру организации
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
    for people in ("legacy_incremental", "greedy", "hungarian", "local_search", "cpsat", "auto"):
        units = "legacy" if people.startswith("legacy") else "sainte_lague_flow"
        xs = [s for s in sizes if (s, "norm", units, people) in agg]
        if not xs:
            continue
        ax[0].plot(
            xs,
            [agg[(s, "norm", units, people)]["people_max"] for s in xs],
            marker="o",
            label=METHOD_NAMES[people],
        )
        ax[1].plot(
            xs,
            [agg[(s, "norm", units, people)]["std"] for s in xs],
            marker="o",
            label=METHOD_NAMES[people],
        )
    ax[0].set(
        xscale="log",
        yscale="log",
        xlabel="людей в организации",
        ylabel="самая долгая подзадача, с",
        title="Время распределения людей",
    )
    ax[1].set(
        xscale="log",
        xlabel="людей в организации",
        ylabel="σ нагрузки за месяц",
        title="Справедливость (обычная нагрузка)",
    )
    ax[1].legend(fontsize=7)
    _save(fig, data_dir / "e1_methods.png")
    out += ["![Время и справедливость методов](experiments/e1_methods.png)", ""]

    deficit = [
        s for s in sizes if any((s, "deficit", "sainte_lague_flow", p) in agg for p in PEOPLE_ORDER)
    ]
    if deficit:
        size = max(deficit)
        labels, cover, bad = [], [], []
        for units, people in [
            ("legacy", "legacy"),
            ("legacy", "legacy_incremental"),
            *[("sainte_lague_flow", p) for p in (*PEOPLE_ORDER[2:], "auto")],
        ]:
            d = agg.get((size, "deficit", units, people))
            if d is None:
                continue
            labels.append(METHOD_NAMES[people])
            cover.append(d["coverage"])
            bad.append(d["violations_total"])
        fig, ax = plt.subplots(figsize=(8, 3.4))
        bars = ax.barh(labels, cover, color=["#c0504d" if b else "#4f81bd" for b in bad])
        for bar, b in zip(bars, bad, strict=True):
            if b:
                ax.text(
                    bar.get_width(),
                    bar.get_y() + bar.get_height() / 2,
                    f"  нарушений {num(b)}",
                    va="center",
                    fontsize=7,
                )
        ax.set(
            xlabel="закрыто мест, %",
            xlim=(min(cover) - 3, 101),
            title=f"Дефицит людей, {num(size)} человек",
        )
        ax.invert_yaxis()
        _save(fig, data_dir / "e1_deficit.png")
        out += ["![Покрытие при дефиците](experiments/e1_deficit.png)", ""]

    # --- E2 --------------------------------------------------------------------------------
    out += [
        "## E2. Распределение по подразделениям",
        "",
        "Метод распределения людей в курсах один — локальный поиск, меняется только то, как "
        "ячейки спускаются по дереву. «Потеряно» — места в ячейках, которые не удалось передать "
        "ни одному дочернему (ни у кого нет столько свободных допущенных людей). «Джини долей» — "
        "неравномерность числа мест на допущенного человека между курсами: 0 — нагрузка "
        "разложена пропорционально людям. Время — этапа делегирования.",
        "",
        "| Людей | Сценарий | Распределение по подразделениям | Потеряно | Закрыто | % | "
        "Джини долей | σ нагрузки | Время Σ, с | Макс. подзадача, с | Память, МБ |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for size in sizes:
        for scenario in scenarios:
            for units in UNIT_NAMES:
                u = agg.get((size, scenario, units, "local_search"))
                if u is None:
                    continue
                a = u
                out.append(
                    f"| {num(size)} | {SCENARIO_NAMES[scenario]} | {UNIT_NAMES[units]} | "
                    f"{num(a['lost'])} | {num(a['filled'])} | {num(a['coverage'], 1)} | "
                    f"{num(a['share_gini'], 3)} | {num(a['std'], 2)} | "
                    f"{num(a['units_sum'], 1)} | {num(a['units_max'], 2)} | {num(a['peak'])} |"
                )
    out.append("")
    fig, ax = plt.subplots(figsize=(7, 3.2))
    width = 0.8 / len(UNIT_NAMES)
    for k, units in enumerate(UNIT_NAMES):
        vals = [
            (agg.get((s, "norm", units, "local_search")) or {}).get("share_gini") or 0
            for s in sizes
        ]
        ax.bar(np.arange(len(sizes)) + k * width, vals, width, label=UNIT_NAMES[units])
    ax.set_xticks(np.arange(len(sizes)) + width, [num(s) for s in sizes])
    ax.set(
        xlabel="людей в организации",
        ylabel="Джини мест на допущенного",
        title="Пропорциональность делегирования (обычная нагрузка)",
    )
    ax.legend(fontsize=7)
    _save(fig, data_dir / "e2_units.png")
    out += ["![Пропорциональность делегирования](experiments/e2_units.png)", ""]
    return out, facts


# --- E3 --------------------------------------------------------------------------------------


def e3_section(rows: list[dict[str, Any]], data_dir: Path) -> tuple[list[str], dict[str, Any]]:
    plt = _plt()
    by_hl = group(rows, "half_life")

    def label(hl: float | None) -> str:
        return "без затухания" if hl is None else f"{num(hl)} дн."

    out = [
        "## E3. Подбор затухания нагрузки",
        "",
        "Одна организация, 6 месяцев подряд: назначения месяца становятся историей "
        "следующего (в снимок попадают последние 90 дней, ADR-0013). Каждый месяц заново "
        "разыгрываются освобождения: короткие (2–14 дней) у 12 % людей и на весь месяц "
        "у 4 % — это и создаёт перекосы, которые должно выравнивать затухание. Весь конвейер "
        "(делегирование и люди, режим auto) считается с одним полупериодом. Итог — "
        "неравномерность суммарной нагрузки за полгода и перекосы внутри отдельных месяцев.",
        "",
        "| Полупериод | σ за 6 мес. | Джини за 6 мес. | Размах за 6 мес., нарядов | "
        "Средняя σ месяца | Худший размах месяца, нарядов | σ выходных за 6 мес. |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    table: dict[Any, dict[str, float | None]] = {}
    for hl, items in by_hl.items():
        table[hl[0]] = {
            "std": mean(r["cumulative"]["std"] for r in items),
            "gini": mean(r["cumulative"]["gini"] for r in items),
            "range": mean(r["cumulative_count"]["range"] for r in items),
            "month_std": mean(m["month_load"]["std"] for r in items for m in r["months"]),
            "month_range": mean(max(m["month_count"]["range"] for m in r["months"]) for r in items),
            "holiday": mean(r["cumulative_holiday"]["std"] for r in items),
        }
        t = table[hl[0]]
        out.append(
            f"| {label(hl[0])} | {num(t['std'], 2)} | {num(t['gini'], 3)} | "
            f"{num(t['range'], 1)} | {num(t['month_std'], 2)} | {num(t['month_range'], 1)} | "
            f"{num(t['holiday'], 2)} |"
        )
    out.append("")
    fig, ax = plt.subplots(figsize=(7, 3.4))
    for hl, items in by_hl.items():
        months = len(items[0]["months"])
        ys = [mean(r["months"][m]["cumulative"]["std"] for r in items) for m in range(months)]
        ax.plot(range(1, months + 1), ys, marker="o", label=label(hl[0]))
    ax.set(
        xlabel="месяц",
        ylabel="σ суммарной нагрузки",
        title="Накопленная неравномерность по месяцам",
    )
    ax.legend(fontsize=7)
    _save(fig, data_dir / "e3_decay.png")
    out += ["![Затухание нагрузки](experiments/e3_decay.png)", ""]
    return out, {"table": table}


# --- E4 --------------------------------------------------------------------------------------


def e4_section(rows: list[dict[str, Any]], data_dir: Path) -> tuple[list[str], dict[str, Any]]:
    plt = _plt()
    sources = list(dict.fromkeys(r["source"] for r in rows))
    variants = list(dict.fromkeys(r["variant"] for r in rows))
    out = [
        "## E4. Методы на отдельных подзадачах и пороги режима auto",
        "",
        "Подзадачи — курсы из оргструктур 1 000 и 5 000 человек при дефиците людей (как их "
        "получает конвейер E1) и малые синтетические снимки фазы 4. Каждый метод решает одну "
        "и ту же подзадачу; «+ к лок. поиску» — сколько мест метод закрыл сверх локального "
        "поиска с 20 тыс. итераций (по умолчанию), σ — нагрузки с затуханием, включая "
        "прошлые наряды (её и выравнивают методы). Время — одна подзадача, один поток.",
        "",
        "| Подзадачи | Пар «человек × место» | Метод | Закрыто из мест | + к лок. поиску | "
        "Граница | σ | Время, с (сред. / макс.) |",
        "|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    base = {(r["problem"]): r for r in rows if r["variant"] == "ls_20k"}
    facts: dict[str, Any] = {"gain": {}, "time": {}, "std": {}}
    for source in sources:
        items = [r for r in rows if r["source"] == source]
        pairs = mean(r["pairs"] for r in items if r["variant"] == "greedy")
        for variant in variants:
            vs = [r for r in items if r["variant"] == variant]
            gain = sum(r["filled"] - base[r["problem"]]["filled"] for r in vs)
            facts["gain"][(source, variant)] = gain
            facts["time"][(source, variant)] = max(r["ms"] for r in vs) / 1000
            facts["std"][(source, variant)] = mean(r["std"] for r in vs)
            out.append(
                f"| {source} ({len(vs)}) | {num(pairs)} | {E4_NAMES.get(variant, variant)} | "
                f"{num(sum(r['filled'] for r in vs))} из {num(sum(r['places'] for r in vs))} | "
                f"{'+' if gain > 0 else ''}{num(gain)} | "
                f"{num(sum(r['bound'] or 0 for r in vs))} | "
                f"{num(mean(r['std'] for r in vs), 3)} | "
                f"{num(mean(r['ms'] for r in vs) / 1000, 2)} / "  # type: ignore[operator]
                f"{num(max(r['ms'] for r in vs) / 1000, 1)} |"
            )
    out.append("")
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
    for variant in variants:
        vs = [r for r in rows if r["variant"] == variant]
        ax[0].scatter(
            [r["pairs"] for r in vs],
            [r["ms"] / 1000 for r in vs],
            s=10,
            label=E4_NAMES.get(variant, variant),
        )
    ax[0].set(
        xscale="log",
        yscale="log",
        xlabel="пар «человек × место»",
        ylabel="время, с",
        title="Время метода по размеру подзадачи",
    )
    ax[0].legend(fontsize=6)
    ls = [v for v in variants if v.startswith("ls_")]
    for source in sources:
        xs = [
            mean(r["ms"] / 1000 for r in rows if r["source"] == source and r["variant"] == v)
            for v in ls
        ]
        ys = [facts["std"][(source, v)] for v in ls]
        ax[1].plot(xs, ys, marker="o", label=source)
    ax[1].set(
        xlabel="среднее время, с",
        ylabel="σ нагрузки",
        title="Локальный поиск: 5 → 100 тыс. итераций",
    )
    ax[1].legend(fontsize=6)
    _save(fig, data_dir / "e4_methods.png")
    out += ["![Методы на подзадачах](experiments/e4_methods.png)", ""]
    return out, facts


def render(data_dir: Path, out: Path) -> None:
    from importlib.metadata import version

    lines = [
        "# Экспериментальная часть: методы распределения и сравнение с legacy",
        "",
        "> Сгенерировано `just experiment` (`tools/experiment`). "
        f"{platform.system()} {platform.machine()}, Python {platform.python_version()}, "
        f"numpy {version('numpy')}, scipy {version('scipy')}, OR-Tools {version('ortools')}. "
        "Подзадачи решаются параллельно в 8 процессах, время каждой замеряется отдельно. "
        "Сырые данные — `docs/experiments/*.json`. Методика, выводы и принятые по итогам "
        "решения — в разделах ниже; исходная постановка — `docs/allocation-design.md`, "
        "«Экспериментальная часть», план — `docs/plans/phase-5.md`, шаг 5c.",
        "",
    ]
    methodology = Path(__file__).with_name("methodology.md")
    if methodology.exists():
        lines += [methodology.read_text(encoding="utf-8").strip(), ""]
    facts: dict[str, Any] = {}
    for name, fn in (("e12", e12_sections), ("e4", e4_section), ("e3", e3_section)):
        rows = load(data_dir, name)
        if rows:
            section, facts[name] = fn(rows, data_dir)
            lines += section
    conclusions = Path(__file__).with_name("conclusions.md")
    if conclusions.exists():
        lines += [conclusions.read_text(encoding="utf-8").strip(), ""]
    out.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"Отчёт: {out}")
