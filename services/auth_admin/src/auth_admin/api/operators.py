"""Операторы системы: список в scope, создание, изменение, блокировка, сброс пароля."""

import datetime as dt
import re
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from auth_admin.operators import OperatorService
from dutyflow_common.auth import get_operator
from dutyflow_common.context import Operator
from dutyflow_common.db import get_session
from dutyflow_common.errors import UnauthorizedError

router = APIRouter(tags=["operators"])
_bearer = HTTPBearer(auto_error=False)
Role = Literal["superadmin", "unit_admin", "operator", "viewer"]
USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,49}$")


def operator_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    operator: Annotated[Operator, Depends(get_operator)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> OperatorService:
    if credentials is None:  # pragma: no cover — get_operator уже проверил
        raise UnauthorizedError("Требуется вход в систему")
    return OperatorService(
        session,
        operator,
        credentials.credentials,
        request.app.state.keycloak,
        request.app.state.org,
    )


ServiceDep = Annotated[OperatorService, Depends(operator_service)]


class OperatorOut(BaseModel):
    id: str
    username: str
    last_name: str
    first_name: str
    full_name: str
    role: Role | None
    role_name: str
    unit_id: str | None
    unit_name: str | None
    enabled: bool
    created_at: dt.datetime | None
    self: bool
    can_edit: bool


class OperatorWithPassword(OperatorOut):
    # Временный пароль показывается один раз; при первом входе его нужно сменить (№61)
    temporary_password: str


class OperatorsPage(BaseModel):
    items: list[OperatorOut]
    total: int
    limit: int
    offset: int


class OperatorCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    last_name: str = Field(min_length=1, max_length=100)
    first_name: str = Field(min_length=1, max_length=100)
    role: Role
    unit_id: uuid.UUID

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        value = value.strip().lower()
        if not USERNAME.match(value):
            raise ValueError(
                "Логин — латинские буквы, цифры, точка, дефис или подчёркивание, от 3 символов"
            )
        return value


class OperatorUpdate(BaseModel):
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: Role | None = None
    unit_id: uuid.UUID | None = None


@router.get("/operators", response_model=OperatorsPage, summary="Операторы в зоне ответственности")
async def list_operators(
    svc: ServiceDep,
    q: Annotated[str | None, Query(description="Логин или ФИО")] = None,
    unit_id: Annotated[uuid.UUID | None, Query(description="Подразделение с поддеревом")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return await svc.list_operators(q, str(unit_id) if unit_id else None, limit, offset)


@router.get(
    "/operators/roles",
    response_model=list[Role],
    summary="Роли, которые можно выдать в подразделении",
)
async def allowed_roles(svc: ServiceDep, unit_id: Annotated[uuid.UUID, Query()]) -> list[str]:
    return await svc.options(str(unit_id))


@router.post(
    "/operators",
    response_model=OperatorWithPassword,
    status_code=201,
    summary="Создать оператора с временным паролем",
)
async def create_operator(data: OperatorCreate, svc: ServiceDep) -> dict[str, Any]:
    return await svc.create(data.model_dump(mode="json"))


@router.patch("/operators/{user_id}", response_model=OperatorOut)
async def update_operator(
    user_id: uuid.UUID, data: OperatorUpdate, svc: ServiceDep
) -> dict[str, Any]:
    return await svc.update(str(user_id), data.model_dump(mode="json", exclude_none=True))


@router.post("/operators/{user_id}/block", response_model=OperatorOut, summary="Заблокировать")
async def block(user_id: uuid.UUID, svc: ServiceDep) -> dict[str, Any]:
    return await svc.set_enabled(str(user_id), False)


@router.post("/operators/{user_id}/unblock", response_model=OperatorOut, summary="Разблокировать")
async def unblock(user_id: uuid.UUID, svc: ServiceDep) -> dict[str, Any]:
    return await svc.set_enabled(str(user_id), True)


@router.post(
    "/operators/{user_id}/reset-password",
    response_model=OperatorWithPassword,
    summary="Сбросить пароль: новый временный, все сессии завершаются",
)
async def reset_password(user_id: uuid.UUID, svc: ServiceDep) -> dict[str, Any]:
    return await svc.reset_password(str(user_id))


@router.post(
    "/operators/{user_id}/logout",
    response_model=OperatorOut,
    summary="Завершить все сессии оператора",
)
async def logout(user_id: uuid.UUID, svc: ServiceDep) -> dict[str, Any]:
    return await svc.logout(str(user_id))
