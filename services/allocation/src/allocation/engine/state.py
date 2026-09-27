"""Изменяемое состояние людей во время решения — массивы [люди × дни] для векторных проверок.

Проверки уровня 1 для множества кандидатов сразу, без цикла по людям:
- `busy[p, day]` — сутки заняты нарядом («≤ 1 наряда в сутки», ADR-0008);
- `rest_until[p, day]` — наибольшее «конец + отдых» среди нарядов, закончившихся в этот день:
  новый наряд со стартом `s` нарушает отдых, если в окне 31 суток до `s` есть значение > `s`;
- `starts[p, day]` — самое раннее начало наряда в этот день: новый наряд `[s, e)` с отдыхом
  `rest` нарушает его, если в окне после `e` есть начало раньше `e + rest`;
- `load[p, day]` — нагрузка нарядов по дню начала: для нагрузки с затуханием и близости.
"""

import numpy as np

from allocation.engine.problem import DAY, FloatArray, IntArray, Problem

NO_REST = np.iinfo(np.int64).min
NO_START = np.iinfo(np.int64).max
REST_WINDOW_DAYS = 31  # отдых не больше 720 ч (30 суток)


class PeopleState:
    def __init__(self, problem: Problem, half_life_days: float, holiday_weight: float) -> None:
        n, w = problem.people, problem.width
        self.problem = problem
        self.holiday_weight = holiday_weight
        self.decay = 0.5 ** (1.0 / half_life_days)
        self.busy = np.zeros((n, w), dtype=np.bool_)
        self.rest_until = np.full((n, w), NO_REST, dtype=np.int64)
        self.starts = np.full((n, w), NO_START, dtype=np.int64)
        self.load = np.zeros((n, w), dtype=np.float64)
        self.type_load = np.zeros((n, max(1, len(problem.type_ids))), dtype=np.float64)
        self.holiday_load = np.zeros(n, dtype=np.float64)
        self.month_total = np.zeros(n, dtype=np.int32)
        self.month_holiday = np.zeros(n, dtype=np.int32)
        # Опорная точка затухания для счётчиков по типам и праздникам — середина месяца
        self.mid = (problem.month_start + problem.month_end) / 2
        self._kernels: dict[int, FloatArray] = {}
        # Окно проверки отдыха «до»: наряд, закончившийся раньше, чем за самый длинный отдых
        # задачи, помешать не может — окно короче 31 суток ускоряет проверку в разы
        longest = max(
            [r.rest for r in problem.roles] + [e.rest for e in problem.existing], default=0
        )
        self.rest_window = min(REST_WINDOW_DAYS, longest // DAY + 1)

    def copy(self) -> "PeopleState":
        """Независимая копия массивов — методы экспериментируют, не портя исходное состояние."""
        other = PeopleState.__new__(PeopleState)
        other.problem = self.problem
        other.holiday_weight = self.holiday_weight
        other.decay = self.decay
        other.mid = self.mid
        other.rest_window = self.rest_window
        other._kernels = self._kernels
        for name in (
            "busy",
            "rest_until",
            "starts",
            "load",
            "type_load",
            "holiday_load",
            "month_total",
            "month_holiday",
        ):
            setattr(other, name, getattr(self, name).copy())
        return other

    def kernel(self, day: int) -> FloatArray:
        """Веса затухания по дням относительно дня ячейки: decay^|day − i|."""
        k = self._kernels.get(day)
        if k is None:
            k = self.decay ** np.abs(np.arange(self.problem.width) - day).astype(np.float64)
            self._kernels[day] = k
        return k

    def unit_load(self, load: float, day: int) -> float:
        """Нагрузка наряда: нарядо-сутки × вес, в выходной — × holiday_weight (№43)."""
        return load * (self.holiday_weight if self.problem.is_holiday(day) else 1.0)

    def add(
        self,
        person: int,
        *,
        day: int,
        start: int,
        end: int,
        rest: int,
        first_day: int,
        last_day: int,
        type_index: int,
        load: float,
    ) -> None:
        w = self.problem.width
        lo, hi = max(0, first_day), min(w - 1, last_day)
        if lo <= hi:
            self.busy[person, lo : hi + 1] = True
        end_day = (end - 1) // DAY
        if 0 <= end_day < w:
            self.rest_until[person, end_day] = max(self.rest_until[person, end_day], end + rest)
        start_day = start // DAY
        if 0 <= start_day < w:
            self.starts[person, start_day] = min(self.starts[person, start_day], start)
        holiday = self.problem.is_holiday(day)
        units = self.unit_load(load, day)
        if 0 <= day < w:
            self.load[person, day] += units
        factor = self.decay ** abs(day - self.mid)
        self.type_load[person, type_index] += units * factor
        if holiday:
            self.holiday_load[person] += factor
        if self.problem.month_start <= day <= self.problem.month_end:
            self.month_total[person] += 1
            if holiday:
                self.month_holiday[person] += 1

    # --- векторные проверки для множества кандидатов -------------------------------------

    def free(self, people: IntArray, first_day: int, last_day: int) -> np.ndarray:
        hi = min(self.problem.width - 1, last_day)
        window: np.ndarray = self.busy[np.ix_(people, np.arange(first_day, hi + 1))]
        return np.logical_not(window.any(axis=1))

    def rested(self, people: IntArray, start: int, end: int, rest: int) -> np.ndarray:
        w = self.problem.width
        day = start // DAY
        lo = max(0, day - self.rest_window)
        before_ok = self.rest_until[people, lo : day + 1].max(axis=1) <= start
        end_day = min(w - 1, (end - 1) // DAY)
        hi = min(w - 1, (end + rest - 1) // DAY) if rest > 0 else end_day
        after = self.starts[people, end_day : hi + 1].min(axis=1)
        # Начало раньше `end` в тот же день — это пересечение, его отсекает `free`
        after_ok = (after >= end + rest) | (after < end)
        return before_ok & after_ok

    def within_limits(self, people: IntArray, day: int) -> np.ndarray:
        p = self.problem
        if not p.month_start <= day <= p.month_end:
            return np.ones(len(people), dtype=np.bool_)
        total = p.limit_total[people]
        ok = (total < 0) | (self.month_total[people] < total)
        if p.is_holiday(day):
            hol = p.limit_holiday[people]
            ok &= (hol < 0) | (self.month_holiday[people] < hol)
        return ok

    def features(self, people: IntArray, day: int, type_index: int) -> dict[str, FloatArray]:
        """Признаки уровня 3 для кандидатов (все — «больше = хуже»)."""
        w = self.problem.width
        load = self.load[people] @ self.kernel(day)
        lo, hi = max(0, day - 7), min(w, day + 8)
        window = self.load[people, lo:hi] > 0
        dist = np.abs(np.arange(lo, hi) - day)
        nearest = np.where(window, dist, 99).min(axis=1) if hi > lo else np.full(len(people), 99)
        recency = np.where(nearest <= 7, np.exp(-nearest / 3.0), 0.0)
        holiday = (
            self.holiday_load[people]
            if self.problem.is_holiday(day)
            else np.zeros(len(people), dtype=np.float64)
        )
        return {
            "load": load,
            "same_type": self.type_load[people, type_index],
            "holiday": holiday,
            "recency": recency,
        }

    def month_load(self) -> FloatArray:
        p = self.problem
        return self.load[:, p.month_start : p.month_end + 1].sum(axis=1)
