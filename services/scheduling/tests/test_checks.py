"""Чистые проверки назначения: интервал наряда, занятые сутки, отдых, лимиты (ADR-0008)."""

import datetime as dt
import uuid
from zoneinfo import ZoneInfo

from scheduling.checks import Busy, LimitRule, PersonInfo, Slot, evaluate, interval, resolve_limit

TZ = ZoneInfo("Europe/Moscow")
ROLE = uuid.uuid4()
UNIT = uuid.uuid4()


def test_interval_and_occupied_days() -> None:
    iv = interval(dt.date(2026, 11, 5), dt.time(18, 0), 24 * 60, TZ)
    assert (iv.first_day, iv.last_day) == (dt.date(2026, 11, 5), dt.date(2026, 11, 6))
    assert iv.start_at == dt.datetime(2026, 11, 5, 15, 0, tzinfo=dt.UTC)  # UTC+3
    short = interval(dt.date(2026, 11, 5), dt.time(8, 0), 6 * 60, TZ)
    assert short.first_day == short.last_day
    # Ровно до полуночи — следующие сутки не заняты
    evening = interval(dt.date(2026, 11, 5), dt.time(18, 0), 6 * 60, TZ)
    assert evening.last_day == dt.date(2026, 11, 5)
    three = interval(dt.date(2026, 11, 5), dt.time(8, 0), 72 * 60, TZ)
    assert three.last_day == dt.date(2026, 11, 8)


def person(**kw: object) -> PersonInfo:
    base: dict[str, object] = {
        "id": uuid.uuid4(),
        "unit_id": UNIT,
        "is_active": True,
        "last_name": "Иванов",
        "first_name": "Пётр",
        "middle_name": "Ильич",
        "clearances": ((ROLE, None, None),),
    }
    return PersonInfo(**(base | kw))  # type: ignore[arg-type]


def slot(day: int, *, holiday: bool = False) -> Slot:
    return Slot(
        duty_role_id=ROLE,
        date=dt.date(2026, 11, day),
        interval=interval(dt.date(2026, 11, day), dt.time(18, 0), 24 * 60, TZ),
        rest_hours=48,
        is_holiday=holiday,
        executor_path="1.2",
        unit_paths={UNIT: "1.2.3"},
    )


def busy(day: int, *, hours: int = 24, holiday: bool = False) -> Busy:
    return Busy(
        uuid.uuid4(),
        interval(dt.date(2026, 11, day), dt.time(18, 0), hours * 60, TZ),
        48,
        "Наряд",
        holiday,
    )


def kinds(p: PersonInfo, s: Slot, b: list[Busy], limit: LimitRule | None = None) -> list[str]:
    return [v.kind for v in evaluate(p, s, b, limit)]


def test_short_name() -> None:
    assert person().short_name == "Иванов П. И."


def test_hard_checks() -> None:
    assert kinds(person(), slot(10), []) == []
    assert kinds(person(is_active=False), slot(10), []) == ["inactive"]
    assert kinds(person(unit_id=uuid.uuid4()), slot(10), []) == ["unit"]
    assert kinds(person(clearances=()), slot(10), []) == ["clearance"]
    expired = ((ROLE, None, dt.date(2026, 11, 9)),)
    assert kinds(person(clearances=expired), slot(10), []) == ["clearance"]
    # Освобождение с 11-го задевает вторые сутки наряда, начатого 10-го
    exempt = ((dt.date(2026, 11, 11), dt.date(2026, 11, 12)),)
    assert kinds(person(exemptions=exempt), slot(10), []) == ["exemption"]


def test_one_duty_per_day_and_rest() -> None:
    # Наряд 9-го занимает 9-е и 10-е — это пересечение, а не отдых
    assert kinds(person(), slot(10), [busy(9)]) == ["busy"]
    # 8-е (до 9-го 18:00) → старт 10-го 18:00: отдых 24 ч < 48 ч
    assert kinds(person(), slot(10), [busy(8)]) == ["rest"]
    assert kinds(person(), slot(10), [busy(7)]) == []
    # Следующий наряд 12-го: после окончания 11-го 18:00 прошло 24 ч < 48
    assert kinds(person(), slot(10), [busy(12)]) == ["rest"]


def test_limits() -> None:
    rule = LimitRule(uuid.uuid4(), "1", uuid.uuid4(), True, None, None, 2, 1)
    assert kinds(person(), slot(20), [busy(1), busy(5)], rule) == ["limit"]
    assert kinds(person(), slot(20), [busy(1)], rule) == []
    # Наряд прошлого месяца не считается
    old = Busy(uuid.uuid4(), interval(dt.date(2026, 10, 1), dt.time(8), 60, TZ), 0, "Н", True)
    assert kinds(person(), slot(20, holiday=True), [old], rule) == []
    assert kinds(person(), slot(20, holiday=True), [busy(1, holiday=True)], rule) == [
        "holiday_limit"
    ]


def test_most_specific_limit() -> None:
    rank = uuid.uuid4()
    academy = LimitRule(uuid.uuid4(), "1", uuid.uuid4(), True, None, None, 8, None)
    faculty = LimitRule(uuid.uuid4(), "1.2", uuid.uuid4(), True, None, None, 6, None)
    faculty_rank = LimitRule(uuid.uuid4(), "1.2", uuid.uuid4(), True, rank, None, 4, None)
    only_self = LimitRule(uuid.uuid4(), "1.2.3", uuid.uuid4(), False, None, None, 1, None)
    other = LimitRule(uuid.uuid4(), "1.5", uuid.uuid4(), True, None, None, 1, None)
    rules = [academy, faculty, faculty_rank, only_self, other]
    p = person(rank_id=rank)
    assert resolve_limit(rules, UNIT, "1.2.3", p) is faculty_rank
    assert resolve_limit(rules, UNIT, "1.2.3", person()) is faculty
    # Правило «только это подразделение» действует на людей самого подразделения
    assert resolve_limit(rules, only_self.unit_id, "1.2.3", person()) is only_self
    assert resolve_limit([other], UNIT, "1.2.3", p) is None
