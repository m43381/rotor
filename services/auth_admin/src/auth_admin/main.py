"""Точка входа сервиса auth-admin: `uvicorn auth_admin.main:app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from auth_admin.api import operators
from auth_admin.keycloak import KeycloakAdmin
from auth_admin.settings import AuthAdminSettings
from dutyflow_common.app import create_service_app
from dutyflow_common.auth import TokenVerifier
from dutyflow_common.upstream import UpstreamClient


def create_app(
    settings: AuthAdminSettings | None = None,
    token_verifier: TokenVerifier | None = None,
    keycloak_transport: httpx.AsyncBaseTransport | None = None,
    org_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    settings = settings or AuthAdminSettings()
    app = create_service_app(settings, title="DutyFlow auth-admin", token_verifier=token_verifier)
    app.include_router(operators.router)
    app.state.keycloak = KeycloakAdmin(
        settings.keycloak_url,
        settings.keycloak_realm,
        settings.auth_admin_client_id,
        settings.auth_admin_client_secret,
        transport=keycloak_transport,
    )
    app.state.org = UpstreamClient(settings.org_url, transport=org_transport)

    base_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with base_lifespan(app):
            yield
        await app.state.keycloak.aclose()
        await app.state.org.aclose()

    app.router.lifespan_context = lifespan
    return app


app = create_app()
