"""Печатные формы, реквизиты подразделений и шаблоны форм (фаза 6b)."""

import datetime as dt
import uuid
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from documents.api.imports import file_response
from documents.forms import REQUISITES
from documents.printing import Document, PrintService
from documents.settings import DocumentsSettings
from dutyflow_common.auth import get_operator
from dutyflow_common.context import Operator
from dutyflow_common.db import get_session
from dutyflow_common.errors import UnauthorizedError

router = APIRouter(tags=["printing"])
_bearer = HTTPBearer(auto_error=False)
Form = Literal["schedule_month", "daily_roster", "daily_order"]
FILE: dict[int | str, dict[str, Any]] = {200: {"content": {"application/octet-stream": {}}}}


def print_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    operator: Annotated[Operator, Depends(get_operator)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> PrintService:
    if credentials is None:  # pragma: no cover — get_operator уже проверил
        raise UnauthorizedError("Требуется вход в систему")
    settings: DocumentsSettings = request.app.state.settings
    return PrintService(
        session,
        operator,
        credentials.credentials,
        scheduling=request.app.state.scheduling,
        org=request.app.state.org,
        tz=ZoneInfo(settings.timezone),
    )


ServiceDep = Annotated[PrintService, Depends(print_service)]


def document(doc: Document) -> Response:
    return file_response(doc.filename, doc.content, doc.media_type)


# --- формы ----------------------------------------------------------------------------------------


@router.get(
    "/print/schedules/{schedule_id}",
    response_class=Response,
    responses=FILE,
    summary="График нарядов на месяц: PDF или XLSX",
)
async def print_schedule(
    schedule_id: uuid.UUID,
    svc: ServiceDep,
    format: Annotated[Literal["pdf", "xlsx"], Query()] = "pdf",
) -> Response:
    return document(await svc.schedule(schedule_id, format))


@router.get(
    "/print/daily",
    response_class=Response,
    responses=FILE,
    summary="Суточный наряд подразделения и поддерева на дату: ведомость или приказ",
)
async def print_daily(
    svc: ServiceDep,
    unit_id: Annotated[uuid.UUID, Query()],
    date: Annotated[dt.date, Query()],
    form: Annotated[Literal["daily_roster", "daily_order"], Query()] = "daily_roster",
    format: Annotated[Literal["pdf", "docx"], Query()] = "pdf",
) -> Response:
    return document(await svc.daily(unit_id, date, form, format))


@router.get(
    "/print/html/{form}",
    response_class=HTMLResponse,
    summary="HTML формы до перевода в PDF — для проверки шаблона",
)
async def print_html(
    form: Form,
    svc: ServiceDep,
    schedule_id: Annotated[uuid.UUID | None, Query()] = None,
    unit_id: Annotated[uuid.UUID | None, Query()] = None,
    date: Annotated[dt.date | None, Query()] = None,
) -> HTMLResponse:
    return HTMLResponse(await svc.html(form, schedule_id=schedule_id, unit_id=unit_id, date=date))


# --- реквизиты ------------------------------------------------------------------------------------


class Requisites(BaseModel):
    approver_position: str | None = Field(default=None, max_length=300)
    approver_rank: str | None = Field(default=None, max_length=100)
    approver_name: str | None = Field(default=None, max_length=200)
    compiler_position: str | None = Field(default=None, max_length=300)
    compiler_rank: str | None = Field(default=None, max_length=100)
    compiler_name: str | None = Field(default=None, max_length=200)


class SettingsIn(Requisites):
    version: int | None = None


class SettingsOut(BaseModel):
    unit_id: uuid.UUID
    unit_name: str
    own: Requisites | None
    version: int | None
    effective: Requisites | None
    # Реквизиты взяты у вышестоящего подразделения (своих нет)
    inherited_from: str | None
    can_edit: bool


@router.get("/document-settings/{unit_id}", response_model=SettingsOut)
async def get_settings(unit_id: uuid.UUID, svc: ServiceDep) -> dict[str, Any]:
    return await svc.settings_view(unit_id)


@router.put("/document-settings/{unit_id}", response_model=SettingsOut)
async def put_settings(unit_id: uuid.UUID, data: SettingsIn, svc: ServiceDep) -> dict[str, Any]:
    values = {k: getattr(data, k) for k in REQUISITES}
    return await svc.save_settings(unit_id, values, data.version)


@router.delete(
    "/document-settings/{unit_id}",
    response_model=SettingsOut,
    summary="Удалить свои реквизиты — действуют реквизиты вышестоящего",
)
async def delete_settings(unit_id: uuid.UUID, svc: ServiceDep) -> dict[str, Any]:
    return await svc.clear_settings(unit_id)


# --- шаблоны --------------------------------------------------------------------------------------


class TemplateBrief(BaseModel):
    form: Form
    title: str
    formats: list[str]
    custom: bool
    updated_at: dt.datetime | None
    updated_by_name: str | None
    comment: str | None


class TemplateOut(BaseModel):
    form: Form
    title: str
    body: str
    builtin: str
    custom: bool
    variables: str


class TemplateIn(BaseModel):
    body: str = Field(max_length=200_000)
    comment: str | None = Field(default=None, max_length=2000)


class PreviewIn(BaseModel):
    body: str | None = Field(default=None, max_length=200_000)


@router.get("/templates", response_model=list[TemplateBrief], summary="Печатные формы и шаблоны")
async def list_templates(svc: ServiceDep) -> list[dict[str, Any]]:
    return await svc.templates()


@router.get("/templates/{form}", response_model=TemplateOut)
async def get_template(form: Form, svc: ServiceDep) -> dict[str, Any]:
    return await svc.template(form)


@router.put(
    "/templates/{form}",
    response_model=TemplateOut,
    summary="Загрузить свой HTML-шаблон PDF-формы (суперадминистратор)",
    description="Шаблон проверяется отрисовкой на демо-данных; при ошибке — 422 с номером "
    "строки. Предыдущие версии сохраняются.",
)
async def put_template(form: Form, data: TemplateIn, svc: ServiceDep) -> dict[str, Any]:
    return await svc.save_template(form, data.body, data.comment)


@router.post(
    "/templates/{form}/reset",
    response_model=TemplateOut,
    summary="Вернуть встроенный шаблон",
)
async def reset_template(form: Form, svc: ServiceDep) -> dict[str, Any]:
    return await svc.reset_template(form)


@router.post(
    "/templates/{form}/preview",
    response_class=Response,
    responses=FILE,
    summary="PDF шаблона на демо-данных (без сохранения)",
)
async def preview_template(form: Form, data: PreviewIn, svc: ServiceDep) -> Response:
    return document(svc.preview(form, data.body))
