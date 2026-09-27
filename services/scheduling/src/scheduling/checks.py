"""Проверки ручного назначения человека в ячейку — чистые функции без БД (фаза 3b).

- интервал экземпляра `[дата + начало, + длительность)` в местном времени и занятые сутки
  (ADR-0008);
- жёсткие проверки: человек в списках и в поддереве исполнителя (open-questions №37),
  действующий допуск к роли (ADR-0009), нет освобождения в занятые сутки, не больше одного
  наряда в сутки;
- проверки, которые оператор может нарушить с комментарием: отдых (ADR-0008) и месячный
  лимит нарядов (open-questions №38).

Тот же код даёт список кандидатов с причинами непригодности — ручной прообраз уровней 1–2
движка распределения (`docs/allocation-design.md`).
"""

import datetime as dt
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal
from zoneinfo import ZoneInfo

type ViolationKind = Literal[
    "inactive", "unit", "clearance", "exemption", "busy", "rest", "limit", "holiday_limit"
]
OVERRIDABLE: frozenset[str] = frozenset({"rest", "limit", "holiday_limit"})


@dataclass(frozen=True, slots=True)
class Interval:
    start_at: dt.datetime  # в UTC
    end_at: dt.datetime
    first_day: dt.date  # занятые сутки, включительно (местные даты)
    last_day: dt.date


def interval(day: dt.date, start: dt.time, duration_minutes: int, tz: ZoneInfo) -> Interval:
    """Экземпляр наряда, начатого в `day`. Сутки — все местные даты, которые пересекает
    `[start, end)`: наряд 18:00 + 24 ч, начатый 5-го, занимает 5-е и 6-е."""
    local_start = dt.datetime.combine(day, start, tzinfo=tz)
    local_end = local_start + dt.timedelta(minutes=duration_minutes)
    last = (local_end - dt.timedelta(microseconds=1)).date()
    return Interval(
        local_start.astimezone(dt.UTC), local_end.astimezone(dt.UTC), local_start.date(), last
    )


@dataclass(frozen=True, slots=True)
class PersonInfo:
    """Человек из снимка personnel — только то, что нужно для проверок."""

    id: uuid.UUID
    unit_id: uuid.UUID
    is_active: bool
    rank_id: uuid.UUID | None = None
    position_id: uuid.UUID | None = None
    last_name: str = ""
    first_name: str = ""
    middle_name: str | None = None
    rank_name: str | None = None
    # (роль, с, по); None — без границы
    clearances: tuple[tuple[uuid.UUID, dt.date | None, dt.date | None], ...] = ()
    exemptions: tuple[tuple[dt.date, dt.date], ...] = ()

    @property
    def short_name(self) -> str:
        initials = "".join(f" {n[0]}." for n in (self.first_name, self.middle_name) if n)
        return f"{self.last_name}{initials}"


@dataclass(frozen=True, slots=True)
class Busy:
    """Другой наряд человека (уже назначенный)."""

    day_plan_id: uuid.UUID
    interval: Interval
    rest_hours: int
    duty_name: str
    is_holiday: bool


@dataclass(frozen=True, slots=True)
class LimitRule:
    id: uuid.UUID
    unit_path: str
    unit_id: uuid.UUID
    applies_to_subtree: bool
    rank_id: uuid.UUID | None
    position_id: uuid.UUID | None
    max_duties: int | None
    max_holiday_duties: int | None


def resolve_limit(
    rules: Iterable[LimitRule], unit_id: uuid.UUID, unit_path: str, person: PersonInfo
) -> LimitRule | None:
    """Самое специфичное правило: ближайшее по дереву подразделение, затем правило
    с уточнением по званию и должности (`docs/data-model.md` §5)."""
    own = unit_path.split(".")
    best: tuple[int, int, str] | None = None
    chosen: LimitRule | None = None
    for r in rules:
        path = r.unit_path.split(".")
        if own[: len(path)] != path:
            continue  # правило не вышестоящего подразделения
        if r.unit_id != unit_id and not r.applies_to_subtree:
            continue
        if r.rank_id is not None and r.rank_id != person.rank_id:
            continue
        if r.position_id is not None and r.position_id != person.position_id:
            continue
        key = (len(path), (r.rank_id is not None) + (r.position_id is not None), str(r.id))
        if best is None or key > best:
            best, chosen = key, r
    return chosen


@dataclass(frozen=True, slots=True)
class Violation:
    kind: ViolationKind
    message: str

    @property
    def overridable(self) -> bool:
        return self.kind in OVERRIDABLE


@dataclass(slots=True)
class Slot:
    """Ячейка, в которую ставят человека."""

    duty_role_id: uuid.UUID
    date: dt.date
    interval: Interval
    rest_hours: int
    is_holiday: bool
    executor_path: str
    # Пути подразделений людей — чтобы проверить «в поддереве исполнителя»
    unit_paths: dict[uuid.UUID, str] = field(default_factory=dict)


def _d(day: dt.date) -> str:
    return day.strftime("%d.%m.%Y")


def _hours(delta: dt.timedelta) -> str:
    return f"{delta.total_seconds() / 3600:g} ч"


def evaluate(
    person: PersonInfo,
    slot: Slot,
    busy: Sequence[Busy],
    limit: LimitRule | None,
) -> list[Violation]:
    """Все нарушения для пары «человек × ячейка». `busy` — другие наряды человека рядом
    с ячейкой и за её месяц (без самой ячейки)."""
    result: list[Violation] = []
    if not person.is_active:
        result.append(Violation("inactive", "Исключён из списков личного состава"))
    path = slot.unit_paths.get(person.unit_id, "")
    own = slot.executor_path.split(".")
    if path.split(".")[: len(own)] != own:
        result.append(Violation("unit", "Не входит в подразделение-исполнитель"))
    if not any(
        role == slot.duty_role_id
        and (start is None or start <= slot.date)
        and (end is None or end >= slot.date)
        for role, start, end in person.clearances
    ):
        result.append(Violation("clearance", "Нет действующего допуска к роли"))
    for start, end in person.exemptions:
        if start <= slot.interval.last_day and end >= slot.interval.first_day:
            result.append(Violation("exemption", f"Освобождён с {_d(start)} по {_d(end)}"))
            break

    iv = slot.interval
    for b in busy:
        if b.interval.first_day <= iv.last_day and b.interval.last_day >= iv.first_day:
            result.append(
                Violation(
                    "busy", f"В эти сутки уже в наряде: {b.duty_name}, {_d(b.interval.first_day)}"
                )
            )
            continue
        if b.interval.end_at <= iv.start_at:
            gap = iv.start_at - b.interval.end_at
            need = dt.timedelta(hours=b.rest_hours)
            if gap < need:
                result.append(
                    Violation(
                        "rest",
                        f"Отдых после наряда «{b.duty_name}» {_d(b.interval.first_day)} — "
                        f"{_hours(gap)}, нужно {_hours(need)}",
                    )
                )
        elif b.interval.start_at >= iv.end_at:
            gap = b.interval.start_at - iv.end_at
            need = dt.timedelta(hours=slot.rest_hours)
            if gap < need:
                result.append(
                    Violation(
                        "rest",
                        f"До следующего наряда «{b.duty_name}» {_d(b.interval.first_day)} — "
                        f"{_hours(gap)} отдыха, нужно {_hours(need)}",
                    )
                )

    if limit is not None:
        month = [
            b
            for b in busy
            if (b.interval.first_day.year, b.interval.first_day.month)
            == (slot.date.year, slot.date.month)
        ]
        if limit.max_duties is not None and len(month) + 1 > limit.max_duties:
            result.append(
                Violation("limit", f"Превышен лимит: не больше {limit.max_duties} нарядов в месяц")
            )
        holidays = sum(b.is_holiday for b in month)
        if (
            slot.is_holiday
            and limit.max_holiday_duties is not None
            and holidays + 1 > limit.max_holiday_duties
        ):
            result.append(
                Violation(
                    "holiday_limit",
                    f"Превышен лимит: не больше {limit.max_holiday_duties} нарядов "
                    "в выходные и праздники в месяц",
                )
            )
    return result
