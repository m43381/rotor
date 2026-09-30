"""Метрики нагрузки и справедливости по read-model (фаза 6c, open-questions №56–57).

- Период — даты заступления; по умолчанию учитываются опубликованные и архивные графики
  (факт), с флагом — и черновики. Нагрузка — без затухания: это факт за период.
- Справедливость — по тем же формулам, что в движке и экспериментах (`allocation.engine.
  metrics`, `docs/experiments.md`): σ, коэффициент Джини, индекс Джайна, размах. Считается
  среди людей, у которых в периоде был хотя бы один наряд: допусков read-model не знает.
- Scope — поддерево, как у личного состава: общая политика и проекция подразделений.
- Разрезы (фаза 8, ADR-0020): группировка фактов по одному или двум измерениям средствами
  SQL — подразделение, наряд, роль, категория и звание человека, день недели, месяц,
  источник назначения, тип дня; распределение нагрузки на человека по группам (квартили);
  календарь по дням; кто в наряде в заданный день.
"""

import datetime as dt
import math
import uuid
from collections import defaultdict
from typing import Any, Literal

from sqlalchemy import Integer, Select, String, case, cast, func, null, select
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.models import CategoryDim, DutyFact, PersonDim
from dutyflow_common.context import Operator
from dutyflow_common.errors import NotFoundError, ValidationFailedError
from dutyflow_common.ltree import is_descendant_or_self
from dutyflow_common.policy import Policy, default_policy
from dutyflow_common.projections import RankProjection, UnitProjection, unit_path
from dutyflow_common.scope import in_scope

MAX_DAYS = 400
TOP = 10
ROSTER_LIMIT = 500

type Dimension = Literal[
    "unit", "duty_type", "role", "category", "rank", "weekday", "month", "source", "day_kind"
]
WEEKDAYS = ["", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
SOURCES = {"manual": "Вручную", "auto": "Автоматически"}


def _name(dim: str | None) -> Any:
    """Подпись группы из самих фактов — для наряда и роли; для остальных измерений пусто."""
    if dim == "duty_type":
        return func.max(DutyFact.duty_type_name)
    if dim == "role":
        return func.max(
            func.coalesce(DutyFact.duty_type_name, "")
            + " — "
            + func.coalesce(DutyFact.role_name, "")
        )
    return func.max(cast(null(), String))


def lorenz(values: list[float], points: int = 20) -> list[list[float]]:
    """Кривая Лоренца: доля людей (по возрастанию нагрузки) → доля всей нагрузки."""
    ordered = sorted(values)
    total = sum(ordered)
    n = len(ordered)
    if n == 0 or total <= 0:
        return [[0.0, 0.0], [1.0, 1.0]]
    result = [[0.0, 0.0]]
    for k in range(1, points + 1):
        m = round(n * k / points)
        result.append([round(k / points, 4), round(sum(ordered[:m]) / total, 4)])
    return result


def quantiles(values: list[float]) -> dict[str, float]:
    """Пять чисел для «ящика с усами» и среднее."""
    ordered = sorted(values)
    n = len(ordered)

    def q(p: float) -> float:
        pos = (n - 1) * p
        lo = math.floor(pos)
        hi = min(lo + 1, n - 1)
        return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)

    return {
        "min": round(ordered[0], 3),
        "q1": round(q(0.25), 3),
        "median": round(q(0.5), 3),
        "q3": round(q(0.75), 3),
        "max": round(ordered[-1], 3),
        "mean": round(sum(ordered) / n, 3),
    }


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
            "lorenz": lorenz(loads),
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

    # --- разрезы (фаза 8) --------------------------------------------------------------------

    def _dimension(self, dim: Dimension, unit: UnitProjection, path: Any) -> Any:
        """SQL-выражение ключа группы. Подразделение — ветка прямого дочернего (или само)."""
        match dim:
            case "unit":
                depth = unit.path.count(".") + 1
                return case(
                    (func.nlevel(path) > depth, cast(func.subpath(path, 0, depth + 1), String)),
                    else_=None,
                )
            case "duty_type":
                return DutyFact.duty_type_id
            case "role":
                return DutyFact.duty_role_id
            case "category":
                return PersonDim.category_id
            case "rank":
                return PersonDim.rank_id
            case "weekday":
                return cast(func.extract("isodow", DutyFact.date), Integer)
            case "month":
                return func.to_char(DutyFact.date, "YYYY-MM")
            case "source":
                return DutyFact.source
            case "day_kind":
                return DutyFact.holiday
        raise ValidationFailedError("Неизвестное измерение")  # pragma: no cover

    async def _labels(
        self, dim: Dimension, unit: UnitProjection, keys: set[Any]
    ) -> dict[Any, tuple[str, float]]:
        """Подпись и порядок сортировки каждого значения измерения."""
        labels: dict[Any, tuple[str, float]] = {}
        match dim:
            case "unit":
                children = {
                    c.path: c
                    for c in await self.session.scalars(
                        select(UnitProjection).where(UnitProjection.parent_id == unit.unit_id)
                    )
                }
                for k in keys:
                    if k is None:
                        labels[k] = (f"{unit.name} (само)", -1)
                    else:
                        labels[k] = (children[k].name if k in children else "?", 0)
            case "category":
                cats = {
                    c.category_id: c
                    for c in await self.session.scalars(
                        select(CategoryDim).where(
                            CategoryDim.category_id.in_([k for k in keys if k])
                        )
                    )
                }
                for k in keys:
                    c = cats.get(k)
                    labels[k] = (c.name, c.sort_order) if c else ("Не указана", 10_000)
            case "rank":
                ranks = {
                    r.rank_id: r
                    for r in await self.session.scalars(
                        select(RankProjection).where(
                            RankProjection.rank_id.in_([k for k in keys if k])
                        )
                    )
                }
                for k in keys:
                    r = ranks.get(k)
                    labels[k] = (r.name, -r.order) if r else ("Не указано", 10_000)
            case "weekday":
                labels = {k: (WEEKDAYS[k], k) for k in keys}
            case "month":
                labels = {k: (k, 0) for k in keys}
            case "source":
                labels = {k: (SOURCES.get(k, k), 0) for k in keys}
            case "day_kind":
                labels = {k: ("Выходные и праздники" if k else "Будни", int(bool(k))) for k in keys}
            case _:
                pass  # наряд и роль: подписи — из самих фактов
        return labels

    def _facts_people(
        self, unit: UnitProjection, date_from: dt.date, date_to: dt.date, drafts: bool
    ) -> Any:
        return self._facts(unit, date_from, date_to, drafts).outerjoin(
            PersonDim, PersonDim.person_id == DutyFact.person_id
        )

    async def breakdown(
        self,
        unit_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
        drafts: bool,
        dimension: Dimension,
        split: Dimension | None = None,
    ) -> dict[str, Any]:
        """Нагрузка в разрезе одного или двух измерений: наряды, нарядо-сутки, нагрузка, люди."""
        if split == dimension:
            split = None
        unit = await self._unit(unit_id)
        base = self._facts_people(unit, date_from, date_to, drafts)
        a = self._dimension(dimension, unit, UnitProjection.path).label("a")
        b = self._dimension(split, unit, UnitProjection.path).label("b") if split else None
        columns: list[Any] = [
            a,
            *([b] if b is not None else []),
            func.count().label("duties"),
            func.sum(DutyFact.occupied_days).label("duty_days"),
            func.sum(DutyFact.load).label("load"),
            func.count(func.distinct(DutyFact.person_id)).label("people"),
            func.sum(cast(DutyFact.holiday, Integer)).label("holidays"),
            _name(dimension).label("a_name"),
            _name(split).label("b_name"),
        ]
        group = [a, *([b] if b is not None else [])]
        rows = (await self.session.execute(base.with_only_columns(*columns).group_by(*group))).all()
        a_labels = await self._labels(dimension, unit, {r.a for r in rows})
        b_labels = await self._labels(split, unit, {r.b for r in rows}) if split else {}

        def label(dim: Dimension | None, key: Any, name: str | None, table: dict[Any, Any]) -> str:
            if dim in ("duty_type", "role"):
                return name or "?"
            return str(table.get(key, (key, 0))[0])

        items = [
            {
                "key": None if r.a is None else str(r.a),
                "label": label(dimension, r.a, r.a_name, a_labels),
                "order": a_labels.get(r.a, ("", 0))[1],
                "split_key": None if not split or r.b is None else str(r.b),
                "split_label": label(split, r.b, r.b_name, b_labels) if split else None,
                "split_order": b_labels.get(r.b, ("", 0))[1] if split else 0,
                "duties": r.duties,
                "duty_days": int(r.duty_days or 0),
                "load": round(float(r.load or 0), 2),
                "people": r.people,
                "holidays": int(r.holidays or 0),
                "load_per_person": round(float(r.load or 0) / r.people, 2) if r.people else 0.0,
            }
            for r in rows
        ]
        items.sort(key=lambda i: (i["order"], i["label"], i["split_order"], i["split_label"] or ""))
        return {"dimension": dimension, "split": split, "items": items}

    async def distribution(
        self,
        unit_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
        drafts: bool,
        dimension: Dimension,
    ) -> dict[str, Any]:
        """Нагрузка на человека внутри каждой группы: квартили, среднее, Джини."""
        unit = await self._unit(unit_id)
        a = self._dimension(dimension, unit, UnitProjection.path).label("a")
        rows = (
            await self.session.execute(
                self._facts_people(unit, date_from, date_to, drafts)
                .with_only_columns(
                    a,
                    DutyFact.person_id,
                    func.sum(DutyFact.load).label("load"),
                    _name(dimension).label("a_name"),
                )
                .group_by(a, DutyFact.person_id)
            )
        ).all()
        groups: dict[Any, list[float]] = defaultdict(list)
        group_names: dict[Any, str | None] = {}
        for r in rows:
            groups[r.a].append(float(r.load))
            group_names[r.a] = r.a_name
        labels = await self._labels(dimension, unit, set(groups))
        items = []
        for key, values in groups.items():
            name = (
                group_names.get(key) or "?"
                if dimension in ("duty_type", "role")
                else labels.get(key, (str(key), 0))[0]
            )
            items.append(
                {
                    "key": None if key is None else str(key),
                    "label": name,
                    "order": labels.get(key, ("", 0))[1],
                    "people": len(values),
                    **quantiles(values),
                    "gini": fairness(values)["gini"],
                }
            )
        items.sort(key=lambda i: (i["order"], i["label"]))
        return {"dimension": dimension, "items": items}

    async def calendar(
        self, unit_id: uuid.UUID, date_from: dt.date, date_to: dt.date, drafts: bool
    ) -> list[dict[str, Any]]:
        """По дням заступления: наряды, нагрузка, люди."""
        unit = await self._unit(unit_id)
        rows = (
            await self.session.execute(
                self._facts(unit, date_from, date_to, drafts)
                .with_only_columns(
                    DutyFact.date,
                    func.count().label("duties"),
                    func.sum(DutyFact.load).label("load"),
                    func.count(func.distinct(DutyFact.person_id)).label("people"),
                )
                .group_by(DutyFact.date)
                .order_by(DutyFact.date)
            )
        ).all()
        return [
            {
                "date": r.date,
                "duties": r.duties,
                "load": round(float(r.load), 2),
                "people": r.people,
            }
            for r in rows
        ]

    async def roster(self, unit_id: uuid.UUID, day: dt.date) -> list[dict[str, Any]]:
        """Кто в наряде в этот день (наряды, пересекающие сутки), включая черновики."""
        unit = await self._unit(unit_id)
        rows = (
            await self.session.execute(
                select(DutyFact, UnitProjection.name)
                .join(UnitProjection, UnitProjection.unit_id == DutyFact.unit_id)
                .where(
                    is_descendant_or_self(UnitProjection.path, unit.path),
                    DutyFact.date >= day - dt.timedelta(days=7),
                    DutyFact.date <= day,
                )
                .order_by(DutyFact.start_at, DutyFact.duty_type_name, DutyFact.role_name)
                .limit(ROSTER_LIMIT * 4)
            )
        ).all()
        result = []
        for f, unit_name in rows:
            # Сутки наряда: от даты заступления на число занятых суток
            if not (f.date <= day <= f.date + dt.timedelta(days=f.occupied_days - 1)):
                continue
            result.append(
                {
                    "person_id": f.person_id,
                    "person_name": f.person_name,
                    "unit_name": unit_name,
                    "duty_type_name": f.duty_type_name,
                    "role_name": f.role_name,
                    "date": f.date,
                    "start_at": f.start_at,
                    "end_at": f.end_at,
                    "schedule_status": f.schedule_status,
                }
            )
        return result[:ROSTER_LIMIT]
