"""Метрики нагрузки и справедливости по read-model (фаза 6c, open-questions №56–57).

- Период — даты заступления; по умолчанию учитываются опубликованные и архивные графики
  (факт), с флагом — и черновики. Нагрузка — без затухания: это факт за период.
- Справедливость — по тем же формулам, что в движке и экспериментах (`allocation.engine.
  metrics`, `docs/experiments.md`): σ, коэффициент Джини, индекс Джайна, размах. Считается
  среди людей, у которых в периоде был хотя бы один наряд: допусков read-model не знает.
- Scope — поддерево, как у личного состава: общая политика и проекция подразделений.
"""

import datetime as dt
import math
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import Integer, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.models import DutyFact
from dutyflow_common.context import Operator
from dutyflow_common.errors import NotFoundError, ValidationFailedError
from dutyflow_common.ltree import is_descendant_or_self
from dutyflow_common.policy import Policy, default_policy
from dutyflow_common.projections import UnitProjection, unit_path
from dutyflow_common.scope import in_scope

MAX_DAYS = 400
TOP = 10


def fairness(values: list[float]) -> dict[str, float]:
    n = len(values)
    if n == 0:
        return {"people": 0, "mean": 0.0, "std": 0.0, "gini": 0.0, "jain": 1.0, "range": 0.0,
                "min": 0.0, "max": 0.0}  # fmt: skip
    total = sum(values)
    mean = total / n
    std = math.sqrt(sum((x - mean) ** 2 for x in values) / n)
    ordered = sorted(values)
    gini = (
        sum((2 * (i + 1) - n - 1) * x for i, x in enumerate(ordered)) / (n * total)
        if total > 0
        else 0.0
    )
    square = sum(x * x for x in values)
    jain = total**2 / (n * square) if square > 0 else 1.0
    return {
        "people": n,
        "mean": round(mean, 4),
        "std": round(std, 4),
        "gini": round(gini, 4),
        "jain": round(jain, 4),
        "range": round(ordered[-1] - ordered[0], 4),
        "min": round(ordered[0], 4),
        "max": round(ordered[-1], 4),
    }


class MetricsService:
    def __init__(
        self, session: AsyncSession, operator: Operator, policy: Policy = default_policy
    ) -> None:
        self.session = session
        self.operator = operator
        self.policy = policy

    async def _unit(self, unit_id: uuid.UUID) -> UnitProjection:
        unit = await self.session.get(UnitProjection, unit_id)
        scope = self.policy.scope_for(self.operator.roles, "analytics", "read")
        if unit is None or not in_scope(
            unit.path, await unit_path(self.session, self.operator.unit_id), scope
        ):
            raise NotFoundError("Подразделение не найдено")
        return unit

    def _facts(
        self, unit: UnitProjection, date_from: dt.date, date_to: dt.date, drafts: bool
    ) -> Select[DutyFact, str]:
        if date_to < date_from:
            raise ValidationFailedError("Конец периода раньше начала")
        if (date_to - date_from).days > MAX_DAYS:
            raise ValidationFailedError(f"Период не длиннее {MAX_DAYS} дней")
        statuses = ("published", "archived", "draft") if drafts else ("published", "archived")
        return (
            select(DutyFact, UnitProjection.path)
            .join(UnitProjection, UnitProjection.unit_id == DutyFact.unit_id)
            .where(
                is_descendant_or_self(UnitProjection.path, unit.path),
                DutyFact.date >= date_from,
                DutyFact.date <= date_to,
                DutyFact.schedule_status.in_(statuses),
            )
        )

    async def overview(
        self, unit_id: uuid.UUID, date_from: dt.date, date_to: dt.date, drafts: bool
    ) -> dict[str, Any]:
        unit = await self._unit(unit_id)
        rows = (await self.session.execute(self._facts(unit, date_from, date_to, drafts))).all()
        children = {
            c.path: c
            for c in await self.session.scalars(
                select(UnitProjection).where(UnitProjection.parent_id == unit.unit_id)
            )
        }
        depth = unit.path.count(".") + 1
        people: dict[uuid.UUID, dict[str, Any]] = {}
        by_child: dict[str | None, dict[str, Any]] = defaultdict(
            lambda: {"duties": 0, "load": 0.0, "people": set()}
        )
        months: dict[str, dict[uuid.UUID, float]] = defaultdict(lambda: defaultdict(float))
        for f, path in rows:
            p = people.setdefault(
                f.person_id,
                {
                    "person_id": f.person_id,
                    "person_name": f.person_name,
                    "duties": 0,
                    "duty_days": 0,
                    "load": 0.0,
                    "holidays": 0,
                },
            )
            p["duties"] += 1
            p["duty_days"] += f.occupied_days
            p["load"] += f.load
            p["holidays"] += int(f.holiday)
            parts = path.split(".")
            child = ".".join(parts[: depth + 1]) if len(parts) > depth else None
            group = by_child[child]
            group["duties"] += 1
            group["load"] += f.load
            group["people"].add(f.person_id)
            months[f.date.strftime("%Y-%m")][f.person_id] += f.load

        loads = [p["load"] for p in people.values()]
        ranked = sorted(people.values(), key=lambda p: (-p["load"], p["person_name"]))
        for p in ranked:
            p["load"] = round(p["load"], 2)
        counts = [p["duties"] for p in people.values()]
        histogram: dict[int, int] = defaultdict(int)
        for c in counts:
            histogram[c] += 1
        units = []
        for child_path, group in sorted(
            by_child.items(),
            key=lambda kv: (kv[0] is not None, children[kv[0]].name if kv[0] in children else ""),
        ):
            name = (
                unit.name
                if child_path is None
                else children[child_path].name
                if child_path in children
                else "?"
            )
            n = len(group["people"])
            units.append(
                {
                    "unit_id": unit.unit_id
                    if child_path is None
                    else (children[child_path].unit_id if child_path in children else None),
                    "unit_name": name,
                    "own": child_path is None,
                    "people": n,
                    "duties": group["duties"],
                    "load": round(group["load"], 2),
                    "load_per_person": round(group["load"] / n, 2) if n else 0.0,
                }
            )
        return {
            "unit_id": unit.unit_id,
            "unit_name": unit.name,
            "date_from": date_from,
            "date_to": date_to,
            "drafts": drafts,
            "totals": {
                "people": len(people),
                "duties": len(rows),
                "duty_days": sum(p["duty_days"] for p in people.values()),
                "load": round(sum(loads), 2),
                "holidays": sum(p["holidays"] for p in people.values()),
            },
            "fairness": {
                "count": fairness([float(c) for c in counts]),
                "load": fairness(loads),
                "holiday": fairness([float(p["holidays"]) for p in people.values()]),
            },
            "histogram": [{"duties": k, "people": v} for k, v in sorted(histogram.items())],
            "units": units,
            "trend": [
                {
                    "month": month,
                    "people": len(values),
                    "load": round(sum(values.values()), 2),
                    "gini": fairness(list(values.values()))["gini"],
                }
                for month, values in sorted(months.items())
            ],
            "top": ranked[:TOP],
            "bottom": ranked[::-1][:TOP],
        }

    async def people(
        self,
        unit_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
        drafts: bool,
        *,
        limit: int,
        offset: int,
        ascending: bool,
    ) -> dict[str, Any]:
        """Нагрузка по людям — для таблицы и отчёта по нагрузке."""
        unit = await self._unit(unit_id)
        facts = self._facts(unit, date_from, date_to, drafts).subquery()
        load = func.sum(facts.c.load)
        stmt = select(
            facts.c.person_id,
            func.max(facts.c.person_name).label("person_name"),
            func.count().label("duties"),
            func.sum(facts.c.occupied_days).label("duty_days"),
            load.label("load"),
            func.sum(func.cast(facts.c.holiday, Integer)).label("holidays"),
            func.max(facts.c.date).label("last_date"),
        ).group_by(facts.c.person_id)
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        order = (load.asc() if ascending else load.desc(), func.max(facts.c.person_name))
        rows = (await self.session.execute(stmt.order_by(*order).limit(limit).offset(offset))).all()
        return {
            "items": [
                {
                    "person_id": r.person_id,
                    "person_name": r.person_name,
                    "duties": r.duties,
                    "duty_days": int(r.duty_days),
                    "load": round(float(r.load), 2),
                    "holidays": int(r.holidays),
                    "last_date": r.last_date,
                }
                for r in rows
            ],
            "total": total or 0,
            "limit": limit,
            "offset": offset,
        }
