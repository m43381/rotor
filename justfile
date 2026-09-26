# DutyFlow 2 — команды разработки. Запуск: `just <команда>`, список: `just --list`.

set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]
set dotenv-load := false

compose := "docker compose -f deploy/docker-compose.yml --env-file deploy/.env"

# Список команд
default:
    @just --list

# Установить зависимости Python (все сервисы и libs) и фронтенда
install:
    uv sync --all-packages
    cd frontend; npm ci

# Создать deploy/.env из шаблона со случайными секретами (если его ещё нет)
env:
    uv run python tools/make_env.py

# Поднять весь стенд
up: env
    {{compose}} up -d --build

# Остановить стенд
down:
    {{compose}} down

# Остановить стенд и удалить данные (БД, Redis)
reset:
    {{compose}} down -v

# Логи сервиса (по умолчанию все)
logs service="":
    {{compose}} logs -f --tail=200 {{service}}

# Линтеры и проверка типов
lint:
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy libs/common/src services/org/src tools
    cd frontend; npm run lint; npm run typecheck

# Автоисправление форматирования
fmt:
    uv run ruff check --fix .
    uv run ruff format .

# Тесты (интеграционные поднимают Postgres через testcontainers — нужен запущенный Docker)
test *args:
    uv run pytest libs/common services/org {{args}}

# Применить миграции org к БД из DATABASE_URL
migrate-org:
    cd services/org; uv run alembic upgrade head

# Бенчмарк иерархии (ADR-0003)
bench:
    uv run python tools/bench/hierarchy.py

# Синтетические данные для стенда
seed:
    uv run python tools/gen/seed_org.py
