"""Точка входа сервиса documents: `uvicorn documents.main:app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from documents.api import imports, printing
from documents.settings import DocumentsSettings
from dutyflow_common.app import create_service_app
from dutyflow_common.auth import TokenVerifier
from dutyflow_common.upstream import UpstreamClient


def create_app(
    settings: DocumentsSettings | None = None,
    token_verifier: TokenVerifier | None = None,
    personnel_transport: httpx.AsyncBaseTransport | None = None,
    scheduling_transport: httpx.AsyncBaseTransport | None = None,
    org_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    settings = settings or DocumentsSettings()
    app = create_service_app(settings, title="DutyFlow documents", token_verifier=token_verifier)
    for module in (imports, printing):
        app.include_router(module.router)
    app.state.personnel = UpstreamClient(settings.personnel_url, transport=personnel_transport)
    app.state.scheduling = UpstreamClient(settings.scheduling_url, transport=scheduling_transport)
    app.state.org = UpstreamClient(settings.org_url, transport=org_transport)

    base_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with base_lifespan(app):
            yield
        for client in (app.state.personnel, app.state.scheduling, app.state.org):
            await client.aclose()

    app.router.lifespan_context = lifespan
    return app


app = create_app()
