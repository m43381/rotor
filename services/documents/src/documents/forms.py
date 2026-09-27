"""Модель данных печатных форм: из ответов `scheduling` (данные для печати) и реквизитов
подразделения — контекст шаблона. Один и тот же контекст идёт в HTML-шаблон (PDF) и в
генераторы XLSX и DOCX, поэтому форматы не расходятся по содержанию.

Формы (open-questions №15, №53):
- `schedule_month` — график нарядов на месяц;
- `daily_roster` — ведомость суточного наряда на дату;
- `daily_order` — приказ о назначении суточного наряда (данные — как у ведомости);
- `load_report` — отчёт по нагрузке за период (данные — у `analytics`, шаг 6c).
"""

import datetime as dt
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

COLUMNS_PER_PAGE = 8  # столбцов-ролей на лист графика: шире не помещается на A4 альбомом

MONTHS = (
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
)  # fmt: skip
MONTHS_GEN = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)  # fmt: skip
WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
WEEKDAYS_FULL = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
REQUISITES = (
    "approver_position",
    "approver_rank",
    "approver_name",
    "compiler_position",
    "compiler_rank",
    "compiler_name",
)


@dataclass(frozen=True, slots=True)
class Form:
    code: str
    title: str
    formats: tuple[str, ...]  # первый — PDF по HTML-шаблону
    variables: str  # описание контекста для страницы шаблонов


FORMS = {
    "schedule_month": Form(
        "schedule_month",
        "График нарядов на месяц",
        ("pdf", "xlsx"),
        "title, unit.name, month (дата), month_name, draft (черновик — печатается «ПРОЕКТ»), "
        "requisites.{approver_position, approver_rank, approver_name, compiler_position, "
        "compiler_rank, compiler_name}, pages[] — листы: groups[] {duty_type, start, span}, "
        "columns[] {duty_type, role, start, headcount}, rows[] {date, day, weekday, kind, "
        "cells[] — null или {lines[], missing, executor}}",
    ),
    "daily_roster": Form(
        "daily_roster",
        "Ведомость суточного наряда",
        ("pdf", "docx"),
        "unit.name, date, date_text («5 ноября 2026 г.»), weekday, day_kind, day_name, draft, "
        "requisites.{…}, duties[] {name, owner, executor, start, end, roles[] {name, headcount, "
        "missing, people[] {rank, full_name, short_name, unit}}}, people_count, missing_total",
    ),
    "daily_order": Form(
        "daily_order",
        "Приказ о назначении суточного наряда",
        ("pdf", "docx"),
        "те же данные, что у ведомости суточного наряда",
    ),
    "load_report": Form(
        "load_report",
        "Отчёт по нагрузке",
        ("pdf", "xlsx"),
        "unit.name, period («01.11.2026 — 30.11.2026»), drafts, totals.{people, duties, "
        "duty_days, holidays}, fairness[] {title, mean, std, min, max, range, gini, jain}, "
        "units[] {name, people, duties, load, per_person}, people[] {name, duties, duty_days, "
        "load, holidays, last_date}, requisites.{…}",
    ),
}


def date_text(d: dt.date) -> str:
    return f"{d.day} {MONTHS_GEN[d.month - 1]} {d.year} г."


def requisites(settings: dict[str, Any] | None) -> dict[str, str]:
    return {k: (settings or {}).get(k) or "" for k in REQUISITES}


def person_line(p: dict[str, Any]) -> str:
    rank = (p.get("rank_name") or "").lower()
    return f"{rank} {p['short_name']}".strip()


def schedule_context(data: dict[str, Any], req: dict[str, Any] | None) -> dict[str, Any]:
    schedule = data["schedule"]
    month = dt.date.fromisoformat(schedule["month"])
    rows = data["rows"]
    pages = []
    for start in range(0, max(1, len(rows)), COLUMNS_PER_PAGE):
        chunk = rows[start : start + COLUMNS_PER_PAGE]
        columns = [
            {
                "duty_type": r["duty_type_short_name"] or r["duty_type_name"],
                "role": r["role_name"],
                "start": r["start_time"][:5],
                "headcount": r["headcount"],
            }
            for r in chunk
        ]
        groups: list[dict[str, Any]] = []
        for c in columns:
            if groups and groups[-1]["duty_type"] == c["duty_type"]:
                groups[-1]["span"] += 1
            else:
                groups.append({"duty_type": c["duty_type"], "start": c["start"], "span": 1})
        page_rows = []
        for i, day in enumerate(data["days"]):
            d = dt.date.fromisoformat(day["date"])
            cells: list[dict[str, Any] | None] = []
            for r in chunk:
                cell = r["cells"][i]
                if cell is None:
                    cells.append(None)
                    continue
                cells.append(
                    {
                        "lines": [person_line(p) for p in cell["people"]],
                        "missing": cell["missing"],
                        "executor": cell["executor_unit_name"],
                    }
                )
            page_rows.append(
                {
                    "date": d,
                    "day": d.day,
                    "weekday": WEEKDAYS[d.weekday()],
                    "kind": day["kind"],
                    "cells": cells,
                }
            )
        pages.append({"groups": groups, "columns": columns, "rows": page_rows})
    return {
        "title": "График нарядов",
        "unit": {"name": schedule["unit_name"] or ""},
        "month": month,
        "month_name": f"{MONTHS[month.month - 1]} {month.year} г.",
        "status": schedule["status"],
        "draft": schedule["status"] == "draft",
        "requisites": requisites(req),
        "pages": pages,
    }


def daily_context(
    data: dict[str, Any], req: dict[str, Any] | None, tz: dt.tzinfo | None = None
) -> dict[str, Any]:
    d = dt.date.fromisoformat(data["date"])

    def local(value: str) -> str:
        moment = dt.datetime.fromisoformat(value)
        return (moment.astimezone(tz) if tz else moment).strftime("%H:%M %d.%m")

    duties = []
    people_count = missing_total = 0
    for duty in data["duties"]:
        roles = []
        for role in duty["roles"]:
            people = [
                {
                    "rank": p["rank_name"],
                    "full_name": " ".join(
                        x for x in (p["last_name"], p["first_name"], p["middle_name"]) if x
                    ),
                    "short_name": p["short_name"],
                    "unit": p["unit_name"],
                }
                for p in role["people"]
            ]
            people_count += len(people)
            missing_total += role["missing"]
            roles.append(
                {
                    "name": role["role_name"],
                    "headcount": role["headcount"],
                    "missing": role["missing"],
                    "people": people,
                }
            )
        duties.append(
            {
                "name": duty["duty_type_name"],
                "owner": duty["owner_unit_name"],
                "executor": duty["executor_unit_name"],
                "start": local(duty["start_at"]),
                "end": local(duty["end_at"]),
                "roles": roles,
            }
        )
    return {
        "unit": {"name": data["unit_name"]},
        "date": d,
        "date_text": date_text(d),
        "weekday": WEEKDAYS_FULL[d.weekday()],
        "day_kind": data["day_kind"],
        "day_name": data["day_name"],
        "draft": "draft" in data["statuses"],
        "requisites": requisites(req),
        "duties": duties,
        "people_count": people_count,
        "missing_total": missing_total,
    }


FAIRNESS_TITLES = {
    "load": "Нагрузка на человека",
    "count": "Нарядов на человека",
    "holiday": "Нарядов в выходные",
}


def _num(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def load_context(
    overview: dict[str, Any], people: list[dict[str, Any]], req: dict[str, Any] | None
) -> dict[str, Any]:
    d_from = dt.date.fromisoformat(overview["date_from"])
    d_to = dt.date.fromisoformat(overview["date_to"])
    return {
        "unit": {"name": overview["unit_name"]},
        "period": f"{d_from:%d.%m.%Y} — {d_to:%d.%m.%Y}",
        "date_from": d_from,
        "date_to": d_to,
        "drafts": overview["drafts"],
        "totals": {k: int(v) for k, v in overview["totals"].items() if k != "load"},
        "fairness": [
            {"title": title, **{k: _num(v) for k, v in overview["fairness"][key].items()}}
            for key, title in FAIRNESS_TITLES.items()
        ],
        "units": [
            {
                "name": u["unit_name"] + (" (само)" if u["own"] else ""),
                "people": u["people"],
                "duties": u["duties"],
                "load": _num(u["load"]),
                "per_person": _num(u["load_per_person"]),
            }
            for u in overview["units"]
        ],
        "people": [
            {
                "name": p["person_name"],
                "duties": p["duties"],
                "duty_days": p["duty_days"],
                "load": _num(p["load"]),
                "holidays": p["holidays"],
                "last_date": dt.date.fromisoformat(p["last_date"]).strftime("%d.%m.%Y"),
            }
            for p in people
        ],
        "requisites": requisites(req),
    }


# --- демо-данные для предпросмотра шаблонов -------------------------------------------------------

SAMPLE_REQUISITES = {
    "approver_position": "Начальник факультета",
    "approver_rank": "полковник",
    "approver_name": "И. И. Иванов",
    "compiler_position": "Заместитель начальника факультета",
    "compiler_rank": "подполковник",
    "compiler_name": "П. П. Петров",
}


def _sample_person(last: str, unit: str) -> dict[str, Any]:
    return {
        "rank_name": "Рядовой",
        "last_name": last,
        "first_name": "Иван",
        "middle_name": "Петрович",
        "short_name": f"{last} И. П.",
        "unit_name": unit,
    }


def sample_schedule() -> dict[str, Any]:
    month = dt.date(2026, 11, 1)
    days = [month + dt.timedelta(days=i) for i in range(30)]
    kinds = ["weekend" if d.weekday() >= 5 else "workday" for d in days]
    kinds[3] = "holiday"
    rows = []
    for role, count in (("Дежурный", 1), ("Дневальный", 2), ("Помощник", 1)):
        cells: list[dict[str, Any] | None] = []
        for i in range(len(days)):
            if role == "Помощник" and i % 3 == 0:
                cells.append({"executor_unit_name": "1 курс", "people": [], "missing": 0})
            else:
                people = [_sample_person(f"Курсантов{i}{k}", "Группа 111") for k in range(count)]
                cells.append({"executor_unit_name": None, "people": people, "missing": 0})
        rows.append(
            {
                "duty_type_name": "Наряд по факультету",
                "duty_type_short_name": None,
                "role_name": role,
                "start_time": "18:00:00",
                "headcount": count,
                "cells": cells,
            }
        )
    return {
        "schedule": {"unit_name": "Факультет 1", "month": month.isoformat(), "status": "published"},
        "days": [{"date": d.isoformat(), "kind": k} for d, k in zip(days, kinds, strict=True)],
        "rows": rows,
    }


def sample_daily() -> dict[str, Any]:
    d = dt.date(2026, 11, 5)
    return {
        "unit_name": "Факультет 1",
        "date": d.isoformat(),
        "day_kind": "workday",
        "day_name": None,
        "statuses": ["published"],
        "duties": [
            {
                "duty_type_name": "Наряд по факультету",
                "owner_unit_name": "Факультет 1",
                "executor_unit_name": "1 курс",
                "start_at": "2026-11-05T15:00:00+00:00",
                "end_at": "2026-11-06T15:00:00+00:00",
                "roles": [
                    {
                        "role_name": "Дежурный",
                        "headcount": 1,
                        "missing": 0,
                        "people": [_sample_person("Алексеев", "Группа 111")],
                    },
                    {
                        "role_name": "Дневальный",
                        "headcount": 2,
                        "missing": 1,
                        "people": [_sample_person("Борисов", "Группа 112")],
                    },
                ],
            }
        ],
    }


def sample_load() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    stats = {"people": 3, "mean": 2.0, "std": 0.8165, "gini": 0.2222, "jain": 0.8571,
             "range": 2.0, "min": 1.0, "max": 3.0}  # fmt: skip
    overview = {
        "unit_name": "Факультет 1",
        "date_from": "2026-11-01",
        "date_to": "2026-11-30",
        "drafts": False,
        "totals": {"people": 3, "duties": 6, "duty_days": 8, "load": 9.0, "holidays": 2},
        "fairness": {"load": stats, "count": stats, "holiday": stats},
        "units": [
            {
                "unit_name": "1 курс",
                "own": False,
                "people": 2,
                "duties": 4,
                "load": 6.0,
                "load_per_person": 3.0,
            },
            {
                "unit_name": "2 курс",
                "own": False,
                "people": 1,
                "duties": 2,
                "load": 3.0,
                "load_per_person": 3.0,
            },
        ],
    }
    people = [
        {"person_name": f"Курсантов{i} И. П.", "duties": 3 - i, "duty_days": 4 - i,
         "load": 4.5 - i, "holidays": i % 2, "last_date": "2026-11-2" + str(i)}
        for i in range(3)
    ]  # fmt: skip
    return overview, people


def sample_context(form: str) -> dict[str, Any]:
    if form == "schedule_month":
        return schedule_context(sample_schedule(), SAMPLE_REQUISITES)
    if form == "load_report":
        return load_context(*sample_load(), SAMPLE_REQUISITES)
    return daily_context(sample_daily(), SAMPLE_REQUISITES, ZoneInfo("Europe/Moscow"))
