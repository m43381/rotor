# Образ сервиса org. Контекст сборки — корень репозитория (нужны libs/common и uv.lock).
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY libs/common libs/common
COPY services/org services/org
RUN uv sync --frozen --no-dev --no-editable --package dutyflow-org

FROM python:3.12-slim
RUN useradd --system --uid 10001 --home /srv app
COPY --from=build /app/.venv /app/.venv
COPY services/org/alembic.ini /srv/org/alembic.ini
COPY services/org/migrations /srv/org/migrations
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /srv/org
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
# Миграции применяются при старте; при нескольких репликах их лучше вынести в отдельный job.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn org.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
