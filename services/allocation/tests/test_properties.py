"""Свойства движка на случайных синтетических снимках (разные размеры, плотность допусков,
лимиты, освобождения): жёсткие ограничения не нарушаются, закрепления и ручные назначения
не трогаются, решение детерминировано, закрыто мест не больше строгой границы уровня 2."""

from typing import Any

import pytest
from helpers import FAST

from allocation.engine.config import make_config
from allocation.engine.solve import solve
from allocation.engine.verify import verify, verify_units
from allocation.synthetic import generate_snapshot

CASES = [
    {"people": 60, "clearance_share": 0.15, "seed": 1},  # дефицит людей
    {"people": 120, "clearance_share": 0.3, "limit_share": 0.6, "seed": 2},  # много лимитов
    {"people": 200, "exemption_share": 0.5, "seed": 3},  # много освобождений
    {"people": 300, "duty_types": 8, "seed": 4},
    {"people": 40, "children": 2, "clearance_share": 0.6, "seed": 5},
    {"people": 150, "delegate_share": 0.3, "seed": 6},  # часть ячеек уже передана
]


@pytest.mark.parametrize("params", CASES, ids=lambda p: f"seed{p['seed']}")
def test_people_hard_constraints(params: dict[str, Any]) -> None:
    snap = generate_snapshot(**params)
    config = make_config({}, defaults=FAST)
    sol = solve(snap, config, seed=params["seed"])
    assert verify(snap, sol) == []
    m = sol["metrics"]
    assert m["filled"] + m["shortage"] == m["places"]
    if m["upper_bound"] is not None:
        assert m["filled"] <= m["upper_bound"]
    assert solve(snap, config, seed=params["seed"])["solution_hash"] == sol["solution_hash"]


@pytest.mark.parametrize("params", CASES[:4], ids=lambda p: f"seed{p['seed']}")
def test_rebuild_keeps_manual_and_pinned(params: dict[str, Any]) -> None:
    """Первый прогон — «применён»: его назначения становятся автоматическими в снимке, часть
    закреплена, часть заменена ручными. Пересборка трогает только незакреплённые автоматические."""
    snap = generate_snapshot(**params)
    first = solve(snap, make_config({}, defaults=FAST), seed=1)
    cells = {c["id"]: i for i, c in enumerate(snap["cells"])}
    people = {p["id"]: i for i, p in enumerate(snap["people"])}
    roles = snap["roles"]
    for k, a in enumerate(first["assignments"]):
        cell = snap["cells"][cells[a["cell"]]]
        role = roles[cell["r"]]
        start = cell["d"] * 1440 + int(role["start_time"][:2]) * 60
        end = start + role["duration_minutes"]
        snap["assignments"].append(
            {
                "id": f"a{k}",
                "p": people[a["person"]],
                "cell": cells[a["cell"]],
                "d": cell["d"],
                "r": cell["r"],
                "dt": role["duty_type_id"],
                "t": [start, end],
                "rest": role["rest_hours"],
                "days": [cell["d"], (end - 1) // 1440],
                "load": ((end - 1) // 1440 - cell["d"] + 1) * role["load_weight"],
                "pinned": k % 5 == 0,
                "auto": k % 7 != 0,
                "override": False,
            }
        )
    rebuild = solve(snap, make_config({"mode": "rebuild"}, defaults=FAST), seed=2)
    assert verify(snap, rebuild) == []
    kept = {a["id"] for a in snap["assignments"] if a["pinned"] or not a["auto"]}
    assert not kept & set(rebuild["removed"])
    fill = solve(snap, make_config({}, defaults=FAST), seed=2)
    assert fill["removed"] == []
    assert fill["metrics"]["places"] == first["metrics"]["shortage"]


@pytest.mark.parametrize("params", CASES, ids=lambda p: f"seed{p['seed']}")
def test_units(params: dict[str, Any]) -> None:
    snap = generate_snapshot(**params)
    config = make_config({"kind": "units"}, defaults=FAST)
    sol = solve(snap, config, seed=3)
    assert verify_units(snap, sol) == []
    assert solve(snap, config, seed=3)["solution_hash"] == sol["solution_hash"]


def test_other_seed_same_constraints_maybe_other_choice() -> None:
    snap = generate_snapshot(people=100, seed=9)
    config = make_config({}, defaults=FAST)
    a, b = solve(snap, config, seed=1), solve(snap, config, seed=2)
    assert verify(snap, a) == verify(snap, b) == []


def test_verifier_catches_violations() -> None:
    """Проверка не пустая: испорченное решение она ловит."""
    snap = generate_snapshot(people=80, seed=11)
    sol = solve(snap, make_config({}, defaults=FAST), seed=1)
    a, b = sol["assignments"][0], sol["assignments"][1]
    cells = {c["id"]: c for c in snap["cells"]}
    # Тот же человек в соседней по времени ячейке — сутки пересекаются или нет отдыха
    same_day = next(
        c["id"] for c in snap["cells"] if c["d"] == cells[a["cell"]]["d"] and c["id"] != a["cell"]
    )
    broken = {**sol, "assignments": [*sol["assignments"], {**a, "cell": same_day}]}
    assert any("сутки" in e or "отдых" in e for e in verify(snap, broken))
    # Человек без допуска к роли
    no_clearance = next(
        p["id"] for p in snap["people"] if cells[b["cell"]]["r"] not in {c[0] for c in p["c"]}
    )
    broken = {**sol, "assignments": [{**b, "person": no_clearance}]}
    assert any("допуск" in e for e in verify(snap, broken))
    # Снятое ручное назначение
    snap["assignments"][0]["auto"] = False
    broken = {**sol, "removed": [snap["assignments"][0]["id"]]}
    assert any("ручное" in e for e in verify(snap, broken))


METHODS = ["greedy", "hungarian", "local_search", "cpsat"]


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("params", [CASES[0], CASES[1], CASES[4]], ids=lambda p: f"seed{p['seed']}")
def test_every_method_keeps_hard_constraints(method: str, params: dict[str, Any]) -> None:
    snap = generate_snapshot(**params)
    config = make_config({"method": method, "cpsat_window_pairs": 10**9}, defaults=FAST)
    sol = solve(snap, config, seed=5)
    assert sol["method"] == method
    assert verify(snap, sol) == []
    assert solve(snap, config, seed=5)["solution_hash"] == sol["solution_hash"]


def test_improving_methods_never_lose_places() -> None:
    """Локальный поиск не хуже своего старта (лучшего из жадного и венгерского), CP-SAT —
    не хуже подсказки локального поиска; при нехватке людей точные методы закрывают больше."""
    snap = generate_snapshot(people=60, clearance_share=0.15, limit_share=0.4, seed=1)
    filled = {}
    for method in METHODS:
        config = make_config({"method": method, "cpsat_window_pairs": 10**9}, defaults=FAST)
        filled[method] = solve(snap, config, seed=7)["metrics"]["filled"]
    assert filled["local_search"] >= max(filled["greedy"], filled["hungarian"])
    assert filled["cpsat"] >= filled["local_search"]
    assert filled["hungarian"] > filled["greedy"]


def test_local_search_improves_fairness() -> None:
    snap = generate_snapshot(people=150, seed=3)
    std = {}
    for method in ("greedy", "local_search"):
        sol = solve(snap, make_config({"method": method}, defaults=FAST), seed=7)
        std[method] = sol["metrics"]["fairness_decayed"]["std"]
    assert std["local_search"] < std["greedy"]


def test_auto_stops_when_coverage_proven() -> None:
    """Все места закрыты и совпали со строгой границей max-flow — покрытие доказано, CP-SAT
    не запускается."""
    snap = generate_snapshot(people=150, seed=3)
    sol = solve(snap, make_config({}, defaults=FAST), seed=7)
    assert sol["method"] == "local_search"
    assert sol["metrics"]["filled"] == sol["metrics"]["upper_bound"]
    assert sol["method_info"]["filled_optimal"] is True


@pytest.mark.parametrize("units_method", ["greedy", "flow"])
@pytest.mark.parametrize("apportionment", ["sainte_lague", "hamilton"])
def test_units_methods(units_method: str, apportionment: str) -> None:
    snap = generate_snapshot(people=200, children=5, seed=12)
    config = make_config(
        {"kind": "units", "units_method": units_method, "apportionment": apportionment},
        defaults=FAST,
    )
    sol = solve(snap, config, seed=3)
    assert verify_units(snap, sol) == []
    assert sol["method"] == units_method
    assert sol["metrics"]["filled"] == sol["metrics"]["places"]
