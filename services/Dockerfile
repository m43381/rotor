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
# Печать в PDF (documents, WeasyPrint): pango и шрифты ставятся в образ при сборке — во время
# работы внешних шрифтов и сети нет. Liberation Serif метрически совместим с Times New Roman.
RUN if [ "$SERVICE" = "documents" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends \
            libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
            fonts-liberation2 fonts-dejavu-core \
        && fc-cache -f \
        && rm -rf /var/lib/apt/lists/*; \
    fi
RUN useradd --system --uid 10001 --home /srv app
COPY --from=build /app/.venv /app/.venv
# Каталог сервиса целиком: миграции есть не у всех (у allocation нет предметной БД)
COPY services/${SERVICE} /srv/service
# XDG_CACHE_HOME: пользователю сервиса нужен записываемый каталог кэша (fontconfig)
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 SERVICE=${SERVICE} XDG_CACHE_HOME=/tmp/.cache
WORKDIR /srv/service
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
# Миграции применяются при старте; при нескольких репликах их лучше вынести в отдельный job.
CMD ["sh", "-c", "if [ -f alembic.ini ]; then alembic upgrade head; fi && exec uvicorn ${SERVICE}.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
