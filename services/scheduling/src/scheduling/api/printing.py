"""Данные для печатных форм (фаза 6b): их запрашивает `documents` от имени оператора."""

import datetime as dt
import uuid
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request

from scheduling.api.deps import OperatorDep, SessionDep
from scheduling.printing import PrintService
from scheduling.schemas import DailyRosterOut, PrintScheduleOut

router = APIRouter(tags=["printing"])


def print_service(request: Request, session: SessionDep, operator: OperatorDep) -> PrintService:
    tz = ZoneInfo(request.app.state.settings.timezone)
    return PrintService(session, operator, request.app.state.people_loader, tz)


PrintServiceDep = Annotated[PrintService, Depends(print_service)]


@router.get(
    "/schedules/{schedule_id}/print",
    response_model=PrintScheduleOut,
    summary="График на месяц для печати: люди со званиями или подразделение-исполнитель",
)
async def schedule_print(schedule_id: uuid.UUID, svc: PrintServiceDep) -> PrintScheduleOut:
    return await svc.schedule_print(schedule_id)


@router.get(
    "/rosters/daily",
    response_model=DailyRosterOut,
    summary="Суточный наряд подразделения и его поддерева на дату",
)
async def daily_roster(
    svc: PrintServiceDep,
    unit_id: Annotated[uuid.UUID, Query()],
    date: Annotated[dt.date, Query()],
) -> DailyRosterOut:
    return await svc.daily_roster(unit_id, date)
