"""Маленькие ручные снимки ADR-0013 для точечных сценариев движка."""

import datetime as dt
from typing import Any

MONTH = dt.date(2026, 11, 1)
HISTORY = 10  # дни горизонта до месяца
DAYS = [MONTH - dt.timedelta(days=HISTORY) + dt.timedelta(days=i) for i in range(HISTORY + 30)]
M = HISTORY  # номер первого дня месяца


def role(
    name: str = "Дежурный",
    *,
    start: str = "18:00:00",
    duration: int = 1440,
    rest: int = 48,
    headcount: int = 1,
    type_id: str = "t1",
) -> dict[str, Any]:
    return {
        "id": f"role-{name}",
        "duty_type_id": type_id,
        "duty_type": "Наряд",
        "name": name,
        "headcount": headcount,
        "start_time": start,
        "duration_minutes": duration,
        "rest_hours": rest,
        "load_weight": 1.0,
        "active": True,
    }


def person(
    pid: str,
    roles: list[int],
    *,
    unit: int = 0,
    exemptions: list[list[int]] | None = None,
    limit: list[int | None] | None = None,
    valid: tuple[int | None, int | None] = (None, None),
) -> dict[str, Any]:
    return {
        "id": pid,
        "u": unit,
        "c": [[r, valid[0], valid[1]] for r in roles],
        "x": exemptions or [],
        "limit": limit,
    }


def cell(
    cid: str, day: int, role_index: int = 0, *, executor: int = 0, pinned: bool = False
) -> dict[str, Any]:
    return {
        "id": cid,
        "d": day,
        "r": role_index,
        "s": 0,
        "e": executor,
        "origin": "own",
        "status": "none",
        "pinned": pinned,
        "parent": None,
    }


def existing(
    aid: str,
    person_index: int,
    day: int,
    *,
    cell_index: int | None = None,
    r: dict[str, Any] | None = None,
    auto: bool = False,
    pinned: bool = False,
) -> dict[str, Any]:
    r = r or role()
    start = day * 1440 + int(r["start_time"][:2]) * 60
    end = start + r["duration_minutes"]
    last = (end - 1) // 1440
    return {
        "id": aid,
        "p": person_index,
        "cell": cell_index,
        "d": day,
        "r": 0,
        "dt": r["duty_type_id"],
        "t": [start, end],
        "rest": r["rest_hours"],
        "days": [day, last],
        "load": (last - day + 1) * r["load_weight"],
        "pinned": pinned,
        "auto": auto,
        "override": False,
    }


def snapshot(
    *,
    roles: list[dict[str, Any]],
    people: list[dict[str, Any]],
    cells: list[dict[str, Any]],
    assignments: list[dict[str, Any]] | None = None,
    units: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "snapshot_version": 1,
        "hash": "test",
        "timezone": "Europe/Moscow",
        "schedule": {"id": "s", "unit": 0, "month": MONTH.isoformat(), "status": "draft"},
        "horizon": {"from": DAYS[0].isoformat(), "to": DAYS[-1].isoformat(), "month_start": M},
        "days": [[d.isoformat(), "weekend" if d.weekday() >= 5 else "workday"] for d in DAYS],
        "units": units or [{"id": "u0", "parent": None, "name": "Факультет"}],
        "roles": roles,
        "people": people,
        "cells": cells,
        "assignments": assignments or [],
    }
