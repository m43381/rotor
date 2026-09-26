#!/bin/sh
# Одна инсталляция PostgreSQL, отдельная БД и роль на каждый сервис (CLAUDE.md, «Хранилище»).
# Выполняется образом postgres только при первой инициализации тома.
set -eu

create_db() {
    db="$1"; user="$2"; password="$3"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE ROLE "$user" LOGIN PASSWORD '$password';
CREATE DATABASE "$db" OWNER "$user";
SQL
    # Расширения ставит суперпользователь: у роли сервиса таких прав нет.
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<SQL
CREATE EXTENSION IF NOT EXISTS ltree;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
SQL
}

create_db org_db org "$ORG_DB_PASSWORD"
create_db keycloak_db keycloak "$KEYCLOAK_DB_PASSWORD"
