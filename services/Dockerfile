# Общий образ Python-сервисов. Контекст сборки — корень репозитория.
#   docker build -f services/Dockerfile --build-arg SERVICE=org .
# Копируется весь каталог services/: uv workspace проверяет наличие всех членов,
# а сами исходники занимают мало места. В образ ставится только нужный сервис.
FROM python:3.12-slim AS build
ARG SERVICE
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY libs libs
COPY services services
RUN uv sync --frozen --no-dev --no-editable --package dutyflow-${SERVICE}

FROM python:3.12-slim
ARG SERVICE
RUN useradd --system --uid 10001 --home /srv app
COPY --from=build /app/.venv /app/.venv
COPY services/${SERVICE}/alembic.ini /srv/service/alembic.ini
COPY services/${SERVICE}/migrations /srv/service/migrations
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 SERVICE=${SERVICE}
WORKDIR /srv/service
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
# Миграции применяются при старте; при нескольких репликах их лучше вынести в отдельный job.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn ${SERVICE}.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
