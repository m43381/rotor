"""Экспериментальный стенд фазы 5 (`docs/experiments.md`, `just experiment`)."""

import os

# Подзадачи решаются параллельно в процессах: многопоточный BLAS в каждом из них только
# мешает (и на Windows упирается в память). Задаётся до первого импорта numpy.
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")
