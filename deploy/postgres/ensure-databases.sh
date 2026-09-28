#!/bin/sh
# Одна инсталляция PostgreSQL, отдельная БД и роль на каждый сервис (CLAUDE.md, «Хранилище»).
# Запускается одноразовым контейнером `db-init` при каждом `just up` и идемпотентен: на уже
# существующем томе создаёт только недостающее (например, БД нового сервиса), а пароли ролей
# приводит к значениям из deploy/.env.
set -eu

export PGHOST=postgres PGUSER="$POSTGRES_USER" PGPASSWORD="$POSTGRES_PASSWORD"
# Без NOTICE «extension already exists» при каждом запуске
export PGOPTIONS="-c client_min_messages=warning"

sql() { psql -v ON_ERROR_STOP=1 -qtA "$@"; }

ensure_db() {
    db="$1"; user="$2"; password="$3"
    if [ -z "$(sql -d postgres -c "SELECT 1 FROM pg_roles WHERE rolname = '$user'")" ]; then
        sql -d postgres -c "CREATE ROLE \"$user\" LOGIN PASSWORD '$password'"
        echo "Создана роль $user"
    else
        sql -d postgres -c "ALTER ROLE \"$user\" LOGIN PASSWORD '$password'"
    fi
    if [ -z "$(sql -d postgres -c "SELECT 1 FROM pg_database WHERE datname = '$db'")" ]; then
        sql -d postgres -c "CREATE DATABASE \"$db\" OWNER \"$user\""
        echo "Создана БД $db"
    fi
    # Расширения ставит суперпользователь: у роли сервиса таких прав нет.
    sql -d "$db" -c "CREATE EXTENSION IF NOT EXISTS ltree; CREATE EXTENSION IF NOT EXISTS btree_gist; CREATE EXTENSION IF NOT EXISTS pg_trgm;"
}

ensure_db org_db org "$ORG_DB_PASSWORD"
ensure_db personnel_db personnel "$PERSONNEL_DB_PASSWORD"
ensure_db scheduling_db scheduling "$SCHEDULING_DB_PASSWORD"
ensure_db documents_db documents "$DOCUMENTS_DB_PASSWORD"
ensure_db analytics_db analytics "$ANALYTICS_DB_PASSWORD"
ensure_db auth_admin_db auth_admin "$AUTH_ADMIN_DB_PASSWORD"
ensure_db keycloak_db keycloak "$KEYCLOAK_DB_PASSWORD"
echo "Базы данных сервисов готовы"
