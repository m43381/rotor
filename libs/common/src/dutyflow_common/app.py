"""Фабрика FastAPI-приложения сервиса: ошибки, request_id, логирование, health, БД, auth."""

import logging
import sys
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from dutyflow_common.auth import TokenVerifier
from dutyflow_common.context import current_operator, current_request_id, set_service_name
from dutyflow_common.db import Database
from dutyflow_common.errors import install_error_handlers
from dutyflow_common.settings import ServiceSettings

type Lifespan = Callable[[FastAPI], AsyncIterator[None]]


def setup_logging(level: str) -> None:
    logging.basicConfig(
        stream=sys.stdout,
        level=level,
        format="%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s",
    )
    old_factory = logging.getLogRecordFactory()

    def factory(*args: object, **kwargs: object) -> logging.LogRecord:
        record = old_factory(*args, **kwargs)
        record.request_id = current_request_id.get()
        return record

    logging.setLogRecordFactory(factory)


def create_service_app(
    settings: ServiceSettings,
    *,
    title: str,
    root_path: str = "",
    token_verifier: TokenVerifier | None = None,
) -> FastAPI:
    setup_logging(settings.log_level)
    set_service_name(settings.service_name)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await app.state.db.dispose()

    app = FastAPI(title=title, root_path=root_path, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = Database(settings.database_url)
    app.state.token_verifier = token_verifier or TokenVerifier(settings)
    install_error_handlers(app)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        rid_token = current_request_id.set(request_id)
        op_token = current_operator.set(None)
        try:
            response = await call_next(request)
        finally:
            current_request_id.reset(rid_token)
            current_operator.reset(op_token)
        response.headers["X-Request-Id"] = request_id
        return response

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    return app
