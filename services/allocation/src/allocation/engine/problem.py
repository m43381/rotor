"""Задача распределения: снимок ADR-0013 в массивах numpy.

Время — минуты местного времени от полуночи первого дня горизонта (как в снимке), день —
номер в горизонте. К горизонту добавлен «хвост» после конца месяца: наряд, начатый 30-го,
занимает и первые числа следующего месяца (ADR-0008).
"""

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt

DAY = 1440
OPEN_FROM = -(10**6)
OPEN_TO = 10**6
TAIL_DAYS = 8  # наряд до 7 суток (ADR-0008) + запас

type BoolArray = npt.NDArray[np.bool_]
type IntArray = npt.NDArray[np.int32]
type FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class Role:
    id: str
    name: str
    duty_type: str
    type_index: int
    headcount: int
    start_min: int  # начало от полуночи
    duration: int
    rest: int  # минуты отдыха после наряда
    weight: float
    active: bool


@dataclass(slots=True)
class Cell:
    index: int
    id: str
    day: int
    role: int
    schedule_unit: int
    executor: int | None
    origin: str
    status: str
    pinned: bool
    start: int = 0
    end: int = 0
    last_day: int = 0


@dataclass(frozen=True, slots=True)
class Existing:
    """Уже стоящий наряд человека (история или текущий месяц)."""

    id: str
    person: int
    cell: int | None
    day: int
    type_index: int
    start: int
    end: int
    rest: int
    first_day: int
    last_day: int
    load: float
    pinned: bool
    auto: bool
    override: bool


@dataclass(slots=True)
class Problem:
    snapshot_hash: str
    days: list[dt.date]
    day_kinds: list[str]
    month_start: int
    month_end: int  # последний день месяца (номер)
    width: int  # число дней в массивах: горизонт + хвост
    holiday: BoolArray  # по дням: выходной или праздник
    unit_ids: list[str]
    unit_names: list[str]
    unit_parent: list[int | None]
    schedule_unit: int
    roles: list[Role]
    type_ids: list[str]
    people_ids: list[str]
    person_unit: IntArray  # -1 — вне поддерева
    clearance: BoolArray  # [P, K]
    valid_from: IntArray  # [P, K], номер дня
    valid_to: IntArray
    available: BoolArray  # [P, width]: не освобождён
    limit_total: IntArray  # -1 — без лимита
    limit_holiday: IntArray
    cells: list[Cell]
    existing: list[Existing]
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def people(self) -> int:
        return len(self.people_ids)

    def cell_interval(self, role: int, day: int) -> tuple[int, int, int]:
        r = self.roles[role]
        start = day * DAY + r.start_min
        end = start + r.duration
        return start, end, (end - 1) // DAY

    def is_holiday(self, day: int) -> bool:
        return bool(self.holiday[day]) if 0 <= day < self.width else False


def _minutes(value: str) -> int:
    t = dt.time.fromisoformat(value)
    return t.hour * 60 + t.minute


def load_problem(snapshot: dict[str, Any]) -> Problem:
    if snapshot.get("snapshot_version") != 1:
        raise ValueError(f"Неподдерживаемая версия снимка: {snapshot.get('snapshot_version')}")
    days = [dt.date.fromisoformat(d) for d, _ in snapshot["days"]]
    kinds = [k for _, k in snapshot["days"]]
    width = len(days) + TAIL_DAYS
    holiday = np.zeros(width, dtype=np.bool_)
    holiday[: len(days)] = [k in ("weekend", "holiday") for k in kinds]
    # Хвост после горизонта: выходные вычисляются по дню недели
    for i in range(len(days), width):
        holiday[i] = (days[-1] + dt.timedelta(days=i - len(days) + 1)).weekday() >= 5

    type_ids: list[str] = []
    type_index: dict[str, int] = {}

    def type_of(type_id: str) -> int:
        if type_id not in type_index:
            type_index[type_id] = len(type_ids)
            type_ids.append(type_id)
        return type_index[type_id]

    roles = [
        Role(
            id=str(r["id"]),
            name=str(r["name"]),
            duty_type=str(r["duty_type"]),
            type_index=type_of(str(r["duty_type_id"])),
            headcount=int(r["headcount"]),
            start_min=_minutes(r["start_time"]),
            duration=int(r["duration_minutes"]),
            rest=int(r["rest_hours"]) * 60,
            weight=float(r["load_weight"]),
            active=bool(r["active"]),
        )
        for r in snapshot["roles"]
    ]

    people = snapshot["people"]
    n, k = len(people), len(roles)
    clearance = np.zeros((n, k), dtype=np.bool_)
    valid_from = np.full((n, k), OPEN_FROM, dtype=np.int32)
    valid_to = np.full((n, k), OPEN_TO, dtype=np.int32)
    available = np.ones((n, width), dtype=np.bool_)
    person_unit = np.full(n, -1, dtype=np.int32)
    limit_total = np.full(n, -1, dtype=np.int32)
    limit_holiday = np.full(n, -1, dtype=np.int32)
    for i, p in enumerate(people):
        if p.get("u") is not None:
            person_unit[i] = p["u"]
        for role, start, end in p["c"]:
            clearance[i, role] = True
            valid_from[i, role] = OPEN_FROM if start is None else start
            valid_to[i, role] = OPEN_TO if end is None else end
        for start, end in p["x"]:
            available[i, start : end + 1] = False
        if p.get("limit"):
            total, hol = p["limit"]
            limit_total[i] = -1 if total is None else total
            limit_holiday[i] = -1 if hol is None else hol

    units = snapshot["units"]
    problem = Problem(
        snapshot_hash=str(snapshot.get("hash", "")),
        days=days,
        day_kinds=kinds,
        month_start=int(snapshot["horizon"]["month_start"]),
        month_end=len(days) - 1,
        width=width,
        holiday=holiday,
        unit_ids=[str(u["id"]) for u in units],
        unit_names=[str(u["name"]) for u in units],
        unit_parent=[u["parent"] for u in units],
        schedule_unit=int(snapshot["schedule"]["unit"]),
        roles=roles,
        type_ids=type_ids,
        people_ids=[str(p["id"]) for p in people],
        person_unit=person_unit,
        clearance=clearance,
        valid_from=valid_from,
        valid_to=valid_to,
        available=available,
        limit_total=limit_total,
        limit_holiday=limit_holiday,
        cells=[],
        existing=[],
    )
    for i, c in enumerate(snapshot["cells"]):
        cell = Cell(
            index=i,
            id=str(c["id"]),
            day=int(c["d"]),
            role=int(c["r"]),
            schedule_unit=int(c["s"]),
            executor=c["e"],
            origin=str(c["origin"]),
            status=str(c["status"]),
            pinned=bool(c["pinned"]),
        )
        cell.start, cell.end, cell.last_day = problem.cell_interval(cell.role, cell.day)
        problem.cells.append(cell)
    for a in snapshot["assignments"]:
        start, end = a["t"]
        problem.existing.append(
            Existing(
                id=str(a["id"]),
                person=int(a["p"]),
                cell=a["cell"],
                day=int(a["d"]),
                type_index=type_of(str(a["dt"])),
                start=int(start),
                end=int(end),
                rest=int(a["rest"]) * 60,
                first_day=int(a["days"][0]),
                last_day=int(a["days"][1]),
                load=float(a["load"]),
                pinned=bool(a["pinned"]),
                auto=bool(a["auto"]),
                override=bool(a["override"]),
            )
        )
    return problem
