"""Базовые настройки сервиса. Значения берутся из переменных окружения (см. deploy/.env.example)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    service_name: str = "service"
    database_url: str = "postgresql+asyncpg://dutyflow:dutyflow@localhost:5432/dutyflow"
    redis_url: str = "redis://localhost:6379/0"

    # OIDC (Keycloak, ADR-0002). issuer — как его видит браузер, jwks_url — как его видит сервис
    # внутри сети compose (адреса могут отличаться).
    oidc_issuer: str = "http://localhost:8080/auth/realms/dutyflow"
    oidc_jwks_url: str = "http://keycloak:8080/auth/realms/dutyflow/protocol/openid-connect/certs"
    oidc_audience: str = "dutyflow-api"
    # Имя claim-а с подразделением оператора; настраивается, чтобы IdP можно было заменить.
    oidc_unit_claim: str = "unit_id"

    # Общий секрет для /internal/* между сервисами (не выставляются наружу через gateway).
    # Пустое значение означает «внутренние эндпоинты закрыты»: секрета по умолчанию нет.
    internal_token: str = ""

    log_level: str = "INFO"
