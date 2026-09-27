"""Точка входа движка: `solve(снимок, конфигурация, seed) → решение` — чистая функция.

Решение содержит `solution_hash` — SHA-256 всего, кроме замеров времени: одинаковый вход
и seed дают одинаковый hash (требование детерминизма, CLAUDE.md №6).
"""

import hashlib
from typing import Any

from pydantic_core import to_json

from allocation.engine.config import EngineConfig
from allocation.engine.people import solve_people
from allocation.engine.problem import load_problem
from allocation.engine.units import solve_units

ENGINE_VERSION = "4a"
SOLVER = "greedy-mrv"


def solution_hash(solution: dict[str, Any]) -> str:
    content = {k: v for k, v in solution.items() if k != "solution_hash"}
    metrics = {k: v for k, v in content.get("metrics", {}).items() if k != "timings_ms"}
    return hashlib.sha256(to_json({**content, "metrics": metrics})).hexdigest()


def solve(snapshot: dict[str, Any], config: EngineConfig, seed: int = 0) -> dict[str, Any]:
    problem = load_problem(snapshot)
    result = (
        solve_people(problem, config, seed)
        if config.kind == "people"
        else solve_units(problem, config, seed)
    )
    solution: dict[str, Any] = {
        "engine_version": ENGINE_VERSION,
        "solver": SOLVER,
        "snapshot_hash": problem.snapshot_hash,
        "seed": seed,
        "config": config.model_dump(mode="json"),
        **result,
    }
    solution["solution_hash"] = solution_hash(solution)
    return solution
