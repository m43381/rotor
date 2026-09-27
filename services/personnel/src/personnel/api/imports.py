"""Пакетный импорт (фаза 6a): описание шаблона и проверка / применение строк.

Файлы xlsx/csv разбирает сервис `documents` и вызывает эти эндпоинты от имени оператора
(его токеном): права и аудит — те же, что при работе из интерфейса.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from personnel.api.deps import OperatorDep, SessionDep
from personnel.imports import ImportService
from personnel.schemas import ImportIn, ImportKind, ImportOut, ImportTemplateOut

router = APIRouter(tags=["imports"])


def import_service(session: SessionDep, operator: OperatorDep) -> ImportService:
    return ImportService(session, operator)


ImportServiceDep = Annotated[ImportService, Depends(import_service)]


@router.get(
    "/imports/{kind}/template",
    response_model=ImportTemplateOut,
    summary="Столбцы шаблона импорта и значения выпадающих списков для оператора",
)
async def import_template(kind: ImportKind, svc: ImportServiceDep) -> ImportTemplateOut:
    return await svc.template(kind)


@router.post(
    "/imports/{kind}",
    response_model=ImportOut,
    summary="Проверить или применить строки импорта",
    description="`dry_run: true` — предпросмотр: действие и ошибки по каждой строке и хэш "
    "состояния. `dry_run: false` — применение одной транзакцией; с `expected_hash` "
    "применяется, только если данные не изменились с предпросмотра (иначе 409 `import_stale`). "
    "Строки с ошибками пропускаются только при `skip_invalid: true`, иначе 422.",
)
async def run_import(kind: ImportKind, data: ImportIn, svc: ImportServiceDep) -> ImportOut:
    return await svc.run(kind, data)
