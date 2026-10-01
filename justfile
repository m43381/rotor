# DutyFlow 2 — команды разработки. Запуск: `just <команда>`, список: `just --list`.

set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command"]
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

# Резервная копия всех БД и настроек → deploy/backups/<время> (хранится BACKUP_KEEP_DAYS дней)
backup:
    bash deploy/dutyflow.sh backup

# Восстановить стенд из копии: `just restore deploy/backups/20260929-020000` (данные заменяются)
restore dir:
    bash deploy/dutyflow.sh restore {{dir}}

# Проверка стенда: контейнеры, /health, очереди событий, сертификат, свежесть копий
doctor:
    bash deploy/dutyflow.sh doctor

# Пакет поставки для изолированной сети → dist/dutyflow-<версия>.tar (установка: deploy/README.md)
bundle version:
    uv run python tools/bundle.py --version {{version}}

# Логи сервиса (по умолчанию все)
logs service="":
    {{compose}} logs -f --tail=200 {{service}}

# Линтеры и проверка типов
lint:
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy libs/common/src services/org/src services/personnel/src services/scheduling/src services/allocation/src services/documents/src services/analytics/src services/auth_admin/src tools
    cd frontend; npm run lint; npm run typecheck; npm run check:licenses

# Автоисправление форматирования
fmt:
    uv run ruff check --fix .
    uv run ruff format .

# Тесты: по отдельному pytest на пакет (сервисы независимы, имена тестовых модулей совпадают).
# Интеграционные поднимают Postgres и Redis через testcontainers — нужен запущенный Docker.
test *args:
    uv run pytest libs/common {{args}}
    uv run pytest services/org {{args}}
    uv run pytest services/personnel {{args}}
    uv run pytest services/scheduling {{args}}
    uv run pytest services/allocation {{args}}
    uv run pytest services/documents {{args}}
    uv run pytest services/analytics {{args}}
    uv run pytest services/auth_admin {{args}}
    cd frontend; npm test

# E2E-тесты UI против стенда (после up и seed); браузер системный, PW_CHANNEL=msedge|chrome
e2e:
    cd frontend; $env:PW_CHANNEL = if ($env:PW_CHANNEL) { $env:PW_CHANNEL } else { "msedge" }; npx playwright test

# Скриншоты интерфейса для пояснительной записки → frontend/screenshots/
screenshots:
    cd frontend; npm run screenshots

# Перегенерировать типы API фронтенда из OpenAPI сервисов
gen-api:
    cd frontend; npm run gen:api

# Запустить фронтенд в режиме разработки (API и вход — через стенд на :8088)
dev-frontend:
    cd frontend; npm run dev

# Применить миграции org к БД из DATABASE_URL
migrate-org:
    cd services/org; uv run alembic upgrade head

# Бенчмарк иерархии (ADR-0003) → docs/benchmarks/hierarchy.md
bench:
    uv run python tools/bench/hierarchy.py

# Бенчмарк снимка личного состава (фаза 2) → docs/benchmarks/people-snapshot.md
bench-people:
    uv run python tools/bench/people_snapshot.py

# Бенчмарк графика: таблица месяца и снимок задачи (фаза 3) → docs/benchmarks/schedule.md
bench-schedule:
    uv run python tools/bench/schedule_snapshot.py

# Бенчмарк движка распределения (фаза 4) → docs/benchmarks/allocation.md
bench-allocation:
    uv run python tools/bench/engine.py

# Бенчмарк импорта: разбор файла и проверка / применение до 20 000 строк (фаза 6a) → docs/benchmarks/import.md
bench-import:
    uv run python tools/bench/imports.py

# Экспериментальный стенд (фаза 5): legacy и методы движка на оргструктурах 1k–50k,
# затухание, пороги auto → docs/experiments.md (десятки минут; `--report` — только отчёт)
experiment *args:
    uv run --group experiment python -m tools.experiment.run {{args}}

# Перестроить read-model analytics из фактов scheduling (после восстановления БД и т. п.)
analytics-rebuild:
    {{compose}} exec analytics python -m analytics.rebuild

# Демо-данные стенда: дерево, учётки операторов, личный состав (~1000 человек), наряды, допуски и графики на следующий месяц
seed:
    uv run python tools/gen/seed_org.py
    uv run python tools/gen/seed_people.py
    uv run python tools/gen/seed_duties.py
    uv run python tools/gen/seed_schedules.py

# Нагрузочный прогон на отдельном стенде (№62): up → populate → run → down, отчёт docs/benchmarks/load.md
load *args:
    uv run python -m tools.load {{args}}
