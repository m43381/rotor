"""Точка входа сервиса personnel: `uvicorn personnel.main:app`."""

from fastapi import FastAPI

from dutyflow_common.app import create_service_app
from dutyflow_common.audit_export import audit_export_router
from dutyflow_common.auth import TokenVerifier
from dutyflow_common.usage import UsageCheck, http_usage
from personnel.api import audit, clearances, imports, internal, people, refs
from personnel.settings import PersonnelSettings


def create_app(
    settings: PersonnelSettings | None = None,
    token_verifier: TokenVerifier | None = None,
    usage: UsageCheck | None = None,
) -> FastAPI:
    settings = settings or PersonnelSettings()
    app = create_service_app(settings, title="DutyFlow personnel", token_verifier=token_verifier)
    # Требования ролей и лимиты ссылаются на справочники personnel и людей (ADR-0023)
    app.state.usage = usage or http_usage([settings.scheduling_url], settings.internal_token)
    for module in (people, clearances, imports, refs, audit, internal):
        app.include_router(module.router)
    app.include_router(audit_export_router())
    return app


app = create_app()
