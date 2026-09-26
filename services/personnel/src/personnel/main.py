"""Точка входа сервиса personnel: `uvicorn personnel.main:app`."""

from fastapi import FastAPI

from dutyflow_common.app import create_service_app
from dutyflow_common.auth import TokenVerifier
from personnel.api import audit, internal, people, refs
from personnel.settings import PersonnelSettings


def create_app(
    settings: PersonnelSettings | None = None, token_verifier: TokenVerifier | None = None
) -> FastAPI:
    settings = settings or PersonnelSettings()
    app = create_service_app(settings, title="DutyFlow personnel", token_verifier=token_verifier)
    for module in (people, refs, audit, internal):
        app.include_router(module.router)
    return app


app = create_app()
