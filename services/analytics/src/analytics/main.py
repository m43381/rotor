"""Точка входа сервиса analytics: `uvicorn analytics.main:app`."""

from fastapi import FastAPI

from analytics.api import metrics
from analytics.settings import AnalyticsSettings
from dutyflow_common.app import create_service_app
from dutyflow_common.auth import TokenVerifier


def create_app(
    settings: AnalyticsSettings | None = None, token_verifier: TokenVerifier | None = None
) -> FastAPI:
    settings = settings or AnalyticsSettings()
    app = create_service_app(settings, title="DutyFlow analytics", token_verifier=token_verifier)
    app.include_router(metrics.router)
    return app


app = create_app()
