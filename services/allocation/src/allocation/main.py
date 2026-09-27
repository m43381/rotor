"""Точка входа сервиса allocation: `uvicorn allocation.main:app`."""

from fastapi import FastAPI

from allocation.api import internal
from allocation.settings import AllocationSettings
from dutyflow_common.app import create_service_app
from dutyflow_common.auth import TokenVerifier


def create_app(
    settings: AllocationSettings | None = None, token_verifier: TokenVerifier | None = None
) -> FastAPI:
    settings = settings or AllocationSettings()
    app = create_service_app(settings, title="DutyFlow allocation", token_verifier=token_verifier)
    app.include_router(internal.router)
    return app


app = create_app()
