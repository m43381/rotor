"""Сводный журнал аудита (фаза 7b): поиск с фильтрами и выгрузка в xlsx."""

import datetime as dt
import uuid
from typing import Annotated, Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.journal import JournalService
from analytics.settings import AnalyticsSettings
from dutyflow_common.auth import get_operator
from dutyflow_common.context import Operator
from dutyflow_common.db import get_session

router = APIRouter(tags=["journal"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def journal_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    operator: Annotated[Operator, Depends(get_operator)],
) -> JournalService:
    settings: AnalyticsSettings = request.app.state.settings
    return JournalService(session, operator, ZoneInfo(settings.timezone))


ServiceDep = Annotated[JournalService, Depends(journal_service)]


class Filters(BaseModel):
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    unit_id: uuid.UUID | None = None
    actor: str | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    action: str | None = None
    service: str | None = None


def filters(
    date_from: Annotated[dt.date | None, Query()] = None,
    date_to: Annotated[dt.date | None, Query()] = None,
    unit_id: Annotated[uuid.UUID | None, Query(description="С поддеревом")] = None,
    actor: Annotated[str | None, Query(description="ФИО или id оператора")] = None,
    entity_type: Annotated[str | None, Query()] = None,
    entity_id: Annotated[uuid.UUID | None, Query()] = None,
    action: Annotated[str | None, Query(description="Действие или его начало: person.")] = None,
    service: Annotated[str | None, Query()] = None,
) -> Filters:
    return Filters(
        date_from=date_from,
        date_to=date_to,
        unit_id=unit_id,
        actor=actor,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        service=service,
    )


FiltersDep = Annotated[Filters, Depends(filters)]


class JournalEntry(BaseModel):
    id: uuid.UUID
    service: str
    occurred_at: dt.datetime
    actor_id: str
    actor_name: str
    action: str
    entity_type: str
    entity_id: uuid.UUID
    unit_id: uuid.UUID | None
    unit_name: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    comment: str | None


class JournalPage(BaseModel):
    items: list[JournalEntry]
    total: int
    limit: int
    offset: int


class Facets(BaseModel):
    entity_type: list[str]
    action: list[str]
    service: list[str]


@router.get("/audit", response_model=JournalPage, summary="Сводный журнал аудита всех сервисов")
async def journal(
    svc: ServiceDep,
    f: FiltersDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return await svc.list_entries(limit=limit, offset=offset, **f.model_dump())


@router.get("/audit/facets", response_model=Facets, summary="Значения для фильтров журнала")
async def facets(svc: ServiceDep) -> dict[str, list[str]]:
    return await svc.facets()


@router.get(
    "/audit/export",
    response_class=Response,
    responses={200: {"content": {XLSX: {}}}},
    summary="Журнал по фильтрам в xlsx (до 50 000 записей)",
)
async def export(svc: ServiceDep, f: FiltersDep) -> Response:
    name = f"Журнал аудита {dt.date.today():%d.%m.%Y}.xlsx"
    return Response(
        await svc.export(**f.model_dump()),
        media_type=XLSX,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
    )
