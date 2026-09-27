"""Общие зависимости роутеров personnel."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dutyflow_common.auth import get_operator
from dutyflow_common.context import Operator
from dutyflow_common.db import get_session
from personnel.clearances import ClearanceService
from personnel.people import PeopleService

SessionDep = Annotated[AsyncSession, Depends(get_session)]
OperatorDep = Annotated[Operator, Depends(get_operator)]


def people_service(session: SessionDep, operator: OperatorDep) -> PeopleService:
    return PeopleService(session, operator)


PeopleServiceDep = Annotated[PeopleService, Depends(people_service)]


def clearance_service(session: SessionDep, operator: OperatorDep) -> ClearanceService:
    return ClearanceService(session, operator)


ClearanceServiceDep = Annotated[ClearanceService, Depends(clearance_service)]
