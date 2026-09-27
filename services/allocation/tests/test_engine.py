"""Точечные сценарии движка на ручных снимках: жёсткие ограничения, MRV, пересборка,
дефициты, объяснимость, распределение по подразделениям."""

from typing import Any

from helpers import M, cell, existing, person, role, snapshot

from allocation.engine.config import make_config
from allocation.engine.solve import solve
from allocation.engine.verify import verify, verify_units


def run(snap: dict[str, Any], **config: Any) -> dict[str, Any]:
    solution = solve(snap, make_config(config, defaults={}), seed=1)
    check = (
        verify_units(snap, solution) if config.get("kind") == "units" else verify(snap, solution)
    )
    assert check == [], check
    return solution


def who(solution: dict[str, Any]) -> dict[str, str]:
    return {a["cell"]: a["person"] for a in solution["assignments"]}


def test_simple_fill_and_explanation() -> None:
    snap = snapshot(
        roles=[role()],
        people=[person("a", [0]), person("b", [0]), person("c", [])],
        cells=[cell("x", M + 2)],
    )
    sol = run(snap)
    [a] = sol["assignments"]
    assert a["person"] in {"a", "b"}
    assert a["candidates"] == 2
    assert len(a["alternatives"]) == 1
    assert a["rejected"]["no_clearance"] == 1
    assert set(a["features"]) == {"load", "same_type", "holiday", "recency"}
    assert sol["metrics"]["filled"] == sol["metrics"]["upper_bound"] == 1


def test_rest_and_one_per_day() -> None:
    # Один человек, наряды 18:00 + 24 ч: соседний день занят, через день — нет отдыха 48 ч
    snap = snapshot(
        roles=[role()],
        people=[person("a", [0])],
        cells=[cell("d2", M + 2), cell("d3", M + 3), cell("d4", M + 4), cell("d6", M + 6)],
    )
    sol = run(snap)
    taken = sorted(who(sol))
    # d2 и d6 (между концом d2 в d3 18:00 и d6 18:00 — 72 ч); d3 и d4 — нельзя
    assert len(taken) == 2
    reasons = {u["cell"]: u["rejected"] for u in sol["unfilled"]}
    assert set(reasons) == set({"d2", "d3", "d4", "d6"} - set(taken))
    assert any(r["busy"] or r["rest"] for r in reasons.values())


def test_mrv_fills_scarce_cell_first() -> None:
    # «x» может закрыть только a, «y» — a или b. Порядок по дате поставил бы a в «y»
    # (он раньше и первым по жребию) и оставил «x» пустой; MRV заполняет «x» первой.
    snap = snapshot(
        roles=[role("A"), role("B", type_id="t2")],
        people=[person("a", [0, 1]), person("b", [1])],
        cells=[cell("y", M + 3, 1), cell("x", M + 3, 0)],
    )
    sol = run(snap)
    assert who(sol) == {"x": "a", "y": "b"}


def test_exemption_clearance_window_and_limits() -> None:
    snap = snapshot(
        roles=[role(rest=0, duration=360, start="08:00:00")],
        people=[
            person("sick", [0], exemptions=[[M + 5, M + 6]]),
            person("late", [0], valid=(M + 10, None)),
            person("limited", [0], limit=[1, None]),
        ],
        cells=[cell("c5", M + 5), cell("c8", M + 8), cell("c12", M + 12)],
    )
    sol = run(snap)
    got = who(sol)
    # 5-го «sick» освобождён, у «late» допуск ещё не начался — остаётся «limited»
    assert got["c5"] == "limited"
    # «limited» — не больше одного наряда в месяц
    assert list(got.values()).count("limited") <= 1


def test_fairness_spreads_load() -> None:
    snap = snapshot(
        roles=[role(rest=0, duration=360, start="08:00:00")],
        people=[person("a", [0]), person("b", [0])],
        cells=[cell(f"c{i}", M + 1 + 2 * i) for i in range(6)],
    )
    sol = run(snap)
    counts = list(who(sol).values())
    assert sorted((counts.count("a"), counts.count("b"))) == [3, 3]
    # Воскресный наряд тяжелее (×1,5, №43) — разница нагрузки не больше этой добавки
    assert sol["metrics"]["fairness"]["range"] <= 0.5


def test_history_load_counts() -> None:
    # У «busy» свежий наряд в истории — при прочих равных выбирают «fresh»
    r = role(rest=0, duration=360, start="08:00:00")
    snap = snapshot(
        roles=[r],
        people=[person("busy", [0]), person("fresh", [0])],
        cells=[cell("c", M + 3)],
        assignments=[existing("h", 0, M - 2, r=r)],
    )
    assert who(run(snap)) == {"c": "fresh"}


def test_rebuild_touches_only_own_unpinned() -> None:
    r = role(headcount=3)
    snap = snapshot(
        roles=[r],
        people=[person(p, [0]) for p in ("manual", "pinned", "auto", "other")],
        cells=[cell("c", M + 3)],
        assignments=[
            existing("m", 0, M + 3, cell_index=0),
            existing("p", 1, M + 3, cell_index=0, auto=True, pinned=True),
            existing("x", 2, M + 3, cell_index=0, auto=True),
        ],
    )
    fill = run(snap)
    assert fill["assignments"] == []  # мест нет
    assert fill["removed"] == []
    rebuild = run(snap, mode="rebuild")
    assert rebuild["removed"] == ["x"]
    assert len(rebuild["assignments"]) == 1


def test_deficit_explained_before_solving() -> None:
    snap = snapshot(
        roles=[role(headcount=2)],
        people=[person("a", [0]), person("b", [], unit=0)],
        cells=[cell("c", M + 4)],
    )
    sol = run(snap)
    [d] = sol["deficits"]
    assert (d["need"], d["capacity"]) == (2, 1)
    assert "нужно 2, допустимых 1" in d["message"]
    assert "нет допуска: 1" in d["message"]
    assert sol["metrics"]["shortage"] == 1
    assert sol["metrics"]["upper_bound"] == 1


def test_scope_by_cells_and_pinned_cells_for_units() -> None:
    snap = snapshot(
        roles=[role()],
        people=[person("a", [0]), person("b", [0])],
        cells=[cell("c1", M + 2), cell("c2", M + 6)],
    )
    sol = run(snap, cell_ids=["c2"])
    assert set(who(sol)) == {"c2"}


def test_determinism_and_seed() -> None:
    snap = snapshot(
        roles=[role()],
        people=[person(p, [0]) for p in "abcdef"],
        cells=[cell("c", M + 2)],
    )
    config = make_config({}, defaults={})
    first = solve(snap, config, seed=1)
    assert solve(snap, config, seed=1)["solution_hash"] == first["solution_hash"]
    # Все равны — выбор решает жребий по seed
    chosen = {solve(snap, config, seed=s)["assignments"][0]["person"] for s in range(12)}
    assert len(chosen) > 1


def units_snapshot(big: int, small: int) -> dict[str, Any]:
    units = [
        {"id": "fac", "parent": None, "name": "Факультет"},
        {"id": "big", "parent": 0, "name": "Большой курс"},
        {"id": "small", "parent": 0, "name": "Малый курс"},
        {"id": "g", "parent": 1, "name": "Группа"},
    ]
    people = [person(f"b{i}", [0], unit=3) for i in range(big)] + [
        person(f"s{i}", [0], unit=2) for i in range(small)
    ]
    return snapshot(
        roles=[role(rest=0, duration=360, start="08:00:00")],
        people=people,
        cells=[cell(f"c{d}", M + d) for d in range(28)],
        units=units,
    )


def test_units_quota_proportional_to_capacity() -> None:
    sol = run(units_snapshot(30, 10), kind="units")
    given = [d["unit"] for d in sol["delegations"]]
    assert len(given) == 28
    assert (given.count("big"), given.count("small")) == (21, 7)
    assert sol["metrics"]["quota"]["role-Дежурный"] == {"big": 21, "small": 7}
    d = sol["delegations"][0]
    assert d["capacity"] == {"big": 30, "small": 10}
    assert d["keep"] is False


def test_units_skip_occupied_and_pinned_cells() -> None:
    snap = units_snapshot(3, 3)
    snap["cells"][0]["pinned"] = True
    snap["assignments"] = [existing("a", 0, M + 1, cell_index=1, r=snap["roles"][0])]
    sol = run(snap, kind="units")
    cells = {d["cell"] for d in sol["delegations"]}
    assert "c0" not in cells
    assert "c1" not in cells
    assert len(cells) == 26
