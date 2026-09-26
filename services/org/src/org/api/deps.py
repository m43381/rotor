"""Общие зависимости роутеров org."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dutyflow_common.auth import get_operator
from dutyflow_common.context import Operator
from dutyflow_common.db import get_session
from org.units import UnitService

SessionDep = Annotated[AsyncSession, Depends(get_session)]
OperatorDep = Annotated[Operator, Depends(get_operator)]


def unit_service(session: SessionDep, operator: OperatorDep) -> UnitService:
    return UnitService(session, operator)


UnitServiceDep = Annotated[UnitService, Depends(unit_service)]
