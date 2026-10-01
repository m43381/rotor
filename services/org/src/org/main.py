"""Точка входа сервиса org: `uvicorn org.main:app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from dutyflow_common.app import create_service_app
from dutyflow_common.audit_export import audit_export_router
from dutyflow_common.auth import TokenVerifier
from dutyflow_common.db import Database
from dutyflow_common.usage import UsageCheck, http_usage
from org.api import audit, internal, refs, units
from org.bootstrap import ensure_root
from org.settings import OrgSettings


def create_app(
    settings: OrgSettings | None = None,
    token_verifier: TokenVerifier | None = None,
    usage: UsageCheck | None = None,
) -> FastAPI:
    settings = settings or OrgSettings()
    app = create_service_app(settings, title="DutyFlow org", token_verifier=token_verifier)
    # Ссылки на звания и подразделения хранят personnel, scheduling и auth-admin (ADR-0023)
    app.state.usage = usage or http_usage(
        [settings.personnel_url, settings.scheduling_url, settings.auth_admin_url],
        settings.internal_token,
    )
    for module in (units, refs, audit, internal):
        app.include_router(module.router)
    app.include_router(audit_export_router())

    base_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db: Database = app.state.db
        await ensure_root(db.sessionmaker, settings)
        async with base_lifespan(app):
            yield

    app.router.lifespan_context = lifespan
    return app


app = create_app()
