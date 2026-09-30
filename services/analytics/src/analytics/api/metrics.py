"""API дашборда и отчёта по нагрузке (фаза 6c)."""

import datetime as dt
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.metrics import Dimension, MetricsService
from dutyflow_common.auth import get_operator
from dutyflow_common.context import Operator
from dutyflow_common.db import get_session

router = APIRouter(tags=["metrics"])


def metrics_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    operator: Annotated[Operator, Depends(get_operator)],
) -> MetricsService:
    return MetricsService(session, operator)


ServiceDep = Annotated[MetricsService, Depends(metrics_service)]
UnitQ = Annotated[uuid.UUID, Query(description="Подразделение; учитывается всё поддерево")]
FromQ = Annotated[dt.date, Query(description="Первая дата заступления")]
ToQ = Annotated[dt.date, Query(description="Последняя дата заступления")]
DraftsQ = Annotated[bool, Query(description="Учитывать черновики графиков (№57)")]


class Fairness(BaseModel):
    people: int
    mean: float
    std: float
    gini: float
    jain: float
    range: float
    min: float
    max: float


class PersonLoad(BaseModel):
    person_id: uuid.UUID
    person_name: str
    duties: int
    duty_days: int
    load: float
    holidays: int


class UnitLoad(BaseModel):
    unit_id: uuid.UUID | None
    unit_name: str
    own: bool
    people: int
    duties: int
    load: float
    load_per_person: float


class Overview(BaseModel):
    unit_id: uuid.UUID
    unit_name: str
    date_from: dt.date
    date_to: dt.date
    drafts: bool
    totals: dict[str, float]
    fairness: dict[str, Fairness]
    histogram: list[dict[str, int]]
    units: list[UnitLoad]
    trend: list[dict[str, Any]]
    top: list[PersonLoad]
    bottom: list[PersonLoad]
    # Кривая Лоренца: [доля людей, доля нагрузки] — наглядный вид коэффициента Джини
    lorenz: list[list[float]]


class PersonRow(PersonLoad):
    last_date: dt.date


class PeoplePage(BaseModel):
    items: list[PersonRow]
    total: int
    limit: int
    offset: int


@router.get(
    "/metrics/overview",
    response_model=Overview,
    summary="Нагрузка и справедливость по поддереву за период: сводка для дашборда",
)
async def overview(
    svc: ServiceDep, unit_id: UnitQ, date_from: FromQ, date_to: ToQ, drafts: DraftsQ = False
) -> dict[str, Any]:
    return await svc.overview(unit_id, date_from, date_to, drafts)


@router.get("/metrics/people", response_model=PeoplePage, summary="Нагрузка по людям")
async def people(
    svc: ServiceDep,
    unit_id: UnitQ,
    date_from: FromQ,
    date_to: ToQ,
    drafts: DraftsQ = False,
    limit: Annotated[int, Query(ge=1, le=5_000)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    ascending: Annotated[bool, Query(description="Сначала наименее загруженные")] = False,
) -> dict[str, Any]:
    return await svc.people(
        unit_id, date_from, date_to, drafts, limit=limit, offset=offset, ascending=ascending
    )


# --- разрезы (фаза 8, ADR-0020) -------------------------------------------------------------

DimensionQ = Annotated[Dimension, Query(description="Измерение группировки")]


class BreakdownItem(BaseModel):
    key: str | None
    label: str
    order: float
    split_key: str | None
    split_label: str | None
    split_order: float
    duties: int
    duty_days: int
    load: float
    people: int
    holidays: int
    load_per_person: float


class Breakdown(BaseModel):
    dimension: Dimension
    split: Dimension | None
    items: list[BreakdownItem]


class DistributionItem(BaseModel):
    key: str | None
    label: str
    order: float
    people: int
    min: float
    q1: float
    median: float
    q3: float
    max: float
    mean: float
    gini: float


class Distribution(BaseModel):
    dimension: Dimension
    items: list[DistributionItem]


class CalendarDay(BaseModel):
    date: dt.date
    duties: int
    load: float
    people: int


class RosterItem(BaseModel):
    person_id: uuid.UUID
    person_name: str
    unit_name: str
    duty_type_name: str | None
    role_name: str | None
    date: dt.date
    start_at: dt.datetime
    end_at: dt.datetime
    schedule_status: str


@router.get(
    "/metrics/breakdown",
    response_model=Breakdown,
    summary="Нагрузка в разрезе одного или двух измерений",
)
async def breakdown(
    svc: ServiceDep,
    unit_id: UnitQ,
    date_from: FromQ,
    date_to: ToQ,
    dimension: DimensionQ,
    split: Annotated[Dimension | None, Query(description="Второе измерение")] = None,
    drafts: DraftsQ = False,
) -> dict[str, Any]:
    return await svc.breakdown(unit_id, date_from, date_to, drafts, dimension, split)


@router.get(
    "/metrics/distribution",
    response_model=Distribution,
    summary="Распределение нагрузки на человека по группам (квартили)",
)
async def distribution(
    svc: ServiceDep,
    unit_id: UnitQ,
    date_from: FromQ,
    date_to: ToQ,
    dimension: DimensionQ,
    drafts: DraftsQ = False,
) -> dict[str, Any]:
    return await svc.distribution(unit_id, date_from, date_to, drafts, dimension)


@router.get("/metrics/calendar", response_model=list[CalendarDay], summary="Нагрузка по дням")
async def calendar(
    svc: ServiceDep, unit_id: UnitQ, date_from: FromQ, date_to: ToQ, drafts: DraftsQ = False
) -> list[dict[str, Any]]:
    return await svc.calendar(unit_id, date_from, date_to, drafts)


@router.get(
    "/metrics/roster",
    response_model=list[RosterItem],
    summary="Кто в наряде в этот день (включая черновики)",
)
async def roster(
    svc: ServiceDep, unit_id: UnitQ, day: Annotated[dt.date, Query(description="Дата")]
) -> list[dict[str, Any]]:
    return await svc.roster(unit_id, day)
