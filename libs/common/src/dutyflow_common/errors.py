"""Ошибки предметной области и их отображение в HTTP-ответы.

Формат ответа — упрощённый RFC 9457 (problem details): `code` машиночитаемый,
`message` на русском для показа оператору, `details` — необязательные подробности.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationFailedError(AppError):
    status_code = 422
    code = "validation_failed"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


def _problem(status: int, code: str, message: str, details: Any = None) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status, content=body)


async def _app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return _problem(exc.status_code, exc.code, exc.message, exc.details)


async def _validation_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return _problem(422, "validation_failed", "Некорректные данные запроса", exc.errors())


async def _integrity_handler(_: Request, exc: Exception) -> JSONResponse:
    """Страховка: нарушение ограничения БД, не перехваченное сервисом, — это конфликт данных,
    а не 500. Текст ошибки БД наружу не отдаётся."""
    return _problem(409, "conflict", "Операция нарушает ограничение целостности данных")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(IntegrityError, _integrity_handler)
