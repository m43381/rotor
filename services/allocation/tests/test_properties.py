"""Свойства движка на случайных синтетических снимках (разные размеры, плотность допусков,
лимиты, освобождения): жёсткие ограничения не нарушаются, закрепления и ручные назначения
не трогаются, решение детерминировано, закрыто мест не больше строгой границы уровня 2."""

from typing import Any

import pytest

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
    config = make_config({}, defaults={})
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
    first = solve(snap, make_config({}, defaults={}), seed=1)
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
    rebuild = solve(snap, make_config({"mode": "rebuild"}, defaults={}), seed=2)
    assert verify(snap, rebuild) == []
    kept = {a["id"] for a in snap["assignments"] if a["pinned"] or not a["auto"]}
    assert not kept & set(rebuild["removed"])
    fill = solve(snap, make_config({}, defaults={}), seed=2)
    assert fill["removed"] == []
    assert fill["metrics"]["places"] == first["metrics"]["shortage"]


@pytest.mark.parametrize("params", CASES, ids=lambda p: f"seed{p['seed']}")
def test_units(params: dict[str, Any]) -> None:
    snap = generate_snapshot(**params)
    config = make_config({"kind": "units"}, defaults={})
    sol = solve(snap, config, seed=3)
    assert verify_units(snap, sol) == []
    assert solve(snap, config, seed=3)["solution_hash"] == sol["solution_hash"]


def test_other_seed_same_constraints_maybe_other_choice() -> None:
    snap = generate_snapshot(people=100, seed=9)
    config = make_config({}, defaults={})
    a, b = solve(snap, config, seed=1), solve(snap, config, seed=2)
    assert verify(snap, a) == verify(snap, b) == []


def test_verifier_catches_violations() -> None:
    """Проверка не пустая: испорченное решение она ловит."""
    snap = generate_snapshot(people=80, seed=11)
    sol = solve(snap, make_config({}, defaults={}), seed=1)
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
