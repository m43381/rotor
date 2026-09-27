"""Импорт xlsx/csv: шаблоны, загрузка с предпросмотром, строки с результатом проверки,
отчёт об ошибках, применение и отмена."""

import datetime as dt
import uuid
from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from documents.imports import ImportService
from documents.models import ImportJob
from documents.settings import DocumentsSettings
from dutyflow_common.auth import get_operator
from dutyflow_common.context import Operator
from dutyflow_common.db import get_session
from dutyflow_common.errors import UnauthorizedError, ValidationFailedError

router = APIRouter(tags=["imports"])
Kind = Literal["people", "clearances", "exemptions"]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_bearer = HTTPBearer(auto_error=False)


def import_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    operator: Annotated[Operator, Depends(get_operator)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> ImportService:
    if credentials is None:  # pragma: no cover — get_operator уже проверил
        raise UnauthorizedError("Требуется вход в систему")
    settings: DocumentsSettings = request.app.state.settings
    return ImportService(
        session,
        operator,
        credentials.credentials,
        request.app.state.personnel,
        settings.import_ttl_days,
    )


ServiceDep = Annotated[ImportService, Depends(import_service)]


class ImportColumn(BaseModel):
    key: str
    title: str
    required: bool


class ImportJobOut(BaseModel):
    id: uuid.UUID
    kind: Kind
    status: Literal["preview", "applied", "discarded"]
    filename: str
    columns: list[ImportColumn]
    summary: dict[str, int]
    notes: list[str]
    total: int
    applied_rows: int | None
    created_by_name: str
    created_at: dt.datetime
    applied_at: dt.datetime | None


class ImportRowView(BaseModel):
    row: int
    values: dict[str, Any]
    action: Literal["create", "update", "unchanged", "error"]
    label: str | None
    errors: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    changes: dict[str, list[Any]]


class ImportRowsPage(BaseModel):
    items: list[ImportRowView]
    total: int
    limit: int
    offset: int


class ApplyIn(BaseModel):
    skip_invalid: bool = False


def job_out(job: ImportJob) -> ImportJobOut:
    return ImportJobOut(
        id=job.id,
        kind=job.kind,
        status=job.status,
        filename=job.filename,
        columns=[ImportColumn(**c) for c in job.columns],
        summary=job.summary,
        notes=job.notes,
        total=len(job.rows),
        applied_rows=job.applied_rows,
        created_by_name=job.created_by_name,
        created_at=job.created_at,
        applied_at=job.applied_at,
    )


def file_response(name: str, content: bytes, media_type: str = XLSX) -> Response:
    ascii_name = name.encode("ascii", "replace").decode().replace("?", "_")
    return Response(
        content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{ascii_name}"; '
            f"filename*=UTF-8''{quote(name)}"
        },
    )


@router.get(
    "/imports/templates/{kind}",
    response_class=Response,
    responses={200: {"content": {XLSX: {}}}},
    summary="Скачать xlsx-шаблон со списками значений для оператора",
)
async def download_template(kind: Kind, svc: ServiceDep) -> Response:
    return file_response(*await svc.template_file(kind))


@router.post(
    "/imports/{kind}",
    response_model=ImportJobOut,
    status_code=201,
    summary="Загрузить файл: разбор и предпросмотр, ничего не меняется",
)
async def upload(
    kind: Kind, svc: ServiceDep, request: Request, file: Annotated[UploadFile, File()]
) -> ImportJobOut:
    settings: DocumentsSettings = request.app.state.settings
    content = await file.read(settings.max_upload_mb * 2**20 + 1)
    if len(content) > settings.max_upload_mb * 2**20:
        raise ValidationFailedError(f"Файл больше {settings.max_upload_mb} МБ")
    return job_out(await svc.upload(kind, file.filename or "import", content))


@router.get("/imports", response_model=list[ImportJobOut], summary="Мои последние импорты")
async def list_imports(svc: ServiceDep) -> list[ImportJobOut]:
    return [job_out(j) for j in await svc.list_mine()]


@router.get("/imports/{job_id}", response_model=ImportJobOut)
async def get_import(job_id: uuid.UUID, svc: ServiceDep) -> ImportJobOut:
    return job_out(await svc.get(job_id))


@router.get(
    "/imports/{job_id}/rows",
    response_model=ImportRowsPage,
    summary="Строки файла с результатом проверки",
)
async def import_rows(
    job_id: uuid.UUID,
    svc: ServiceDep,
    action: Annotated[Literal["create", "update", "unchanged", "error"] | None, Query()] = None,
    with_warnings: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ImportRowsPage:
    job = await svc.get(job_id)
    report = {r["row"]: r for r in job.report}
    items = []
    for row in job.rows:
        result = report.get(row["row"], {})
        if action is not None and result.get("action") != action:
            continue
        if with_warnings and not result.get("warnings"):
            continue
        items.append(
            ImportRowView(
                row=row["row"],
                values=row["values"],
                action=result.get("action", "error"),
                label=result.get("label"),
                errors=result.get("errors", []),
                warnings=result.get("warnings", []),
                changes=result.get("changes", {}),
            )
        )
    return ImportRowsPage(
        items=items[offset : offset + limit], total=len(items), limit=limit, offset=offset
    )


@router.get(
    "/imports/{job_id}/report",
    response_class=Response,
    responses={200: {"content": {XLSX: {}}}},
    summary="Отчёт проверки в xlsx: строки файла, результат, ошибки с подсветкой",
)
async def import_report(job_id: uuid.UUID, svc: ServiceDep) -> Response:
    return file_response(*await svc.report_file(job_id))


@router.post(
    "/imports/{job_id}/recheck",
    response_model=ImportJobOut,
    summary="Проверить строки заново на текущих данных",
)
async def recheck(job_id: uuid.UUID, svc: ServiceDep) -> ImportJobOut:
    return job_out(await svc.recheck(job_id))


@router.post(
    "/imports/{job_id}/apply",
    response_model=ImportJobOut,
    summary="Применить предпросмотр",
    description="Если данные изменились после проверки — 409 `import_stale`, а задача "
    "проверяется заново (её можно применить повторно). При ошибках в строках — 422, если "
    "не выбрано `skip_invalid`.",
)
async def apply(job_id: uuid.UUID, data: ApplyIn, svc: ServiceDep) -> ImportJobOut:
    return job_out(await svc.apply(job_id, data.skip_invalid))


@router.post("/imports/{job_id}/discard", response_model=ImportJobOut)
async def discard(job_id: uuid.UUID, svc: ServiceDep) -> ImportJobOut:
    return job_out(await svc.discard(job_id))
