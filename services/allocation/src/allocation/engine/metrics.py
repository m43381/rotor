"""Метрики справедливости распределения нагрузки (`docs/allocation-design.md`, эксперимент)."""

import numpy as np

from allocation.engine.problem import FloatArray


def fairness(loads: FloatArray) -> dict[str, float]:
    """Стандартное отклонение, коэффициент Джини, индекс Джайна, размах, среднее.

    Джини: 0 — всем поровну, → 1 — всё у одного. Джайн: 1 — всем поровну, 1/n — всё у одного.
    """
    x = np.asarray(loads, dtype=np.float64)
    n = len(x)
    if n == 0:
        return {
            "people": 0,
            "mean": 0.0,
            "std": 0.0,
            "gini": 0.0,
            "jain": 1.0,
            "range": 0.0,
            "min": 0.0,
            "max": 0.0,
        }
    total = float(x.sum())
    sorted_x = np.sort(x)
    gini = float((2 * np.arange(1, n + 1) - n - 1) @ sorted_x / (n * total)) if total > 0 else 0.0
    square = float((x**2).sum())
    jain = total**2 / (n * square) if square > 0 else 1.0
    return {
        "people": n,
        "mean": round(float(x.mean()), 4),
        "std": round(float(x.std()), 4),
        "gini": round(gini, 4),
        "jain": round(jain, 4),
        "range": round(float(x.max() - x.min()), 4),
        "min": round(float(x.min()), 4),
        "max": round(float(x.max()), 4),
    }
