"""Общие зависимости роутеров scheduling."""

from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dutyflow_common.auth import get_operator
from dutyflow_common.context import Operator
from dutyflow_common.db import get_session
from scheduling.assignments import AssignmentService
from scheduling.duty_types import DutyTypeService
from scheduling.limits import LimitService
from scheduling.schedules import ScheduleService

SessionDep = Annotated[AsyncSession, Depends(get_session)]
OperatorDep = Annotated[Operator, Depends(get_operator)]


def duty_type_service(
    request: Request, session: SessionDep, operator: OperatorDep
) -> DutyTypeService:
    return DutyTypeService(session, operator, request.app.state.refs_loader)


DutyTypeServiceDep = Annotated[DutyTypeService, Depends(duty_type_service)]


def schedule_service(session: SessionDep, operator: OperatorDep) -> ScheduleService:
    return ScheduleService(session, operator)


ScheduleServiceDep = Annotated[ScheduleService, Depends(schedule_service)]


def assignment_service(
    request: Request, session: SessionDep, operator: OperatorDep
) -> AssignmentService:
    tz = ZoneInfo(request.app.state.settings.timezone)
    return AssignmentService(session, operator, request.app.state.people_loader, tz)


AssignmentServiceDep = Annotated[AssignmentService, Depends(assignment_service)]


def limit_service(request: Request, session: SessionDep, operator: OperatorDep) -> LimitService:
    return LimitService(session, operator, request.app.state.refs_loader)


LimitServiceDep = Annotated[LimitService, Depends(limit_service)]
