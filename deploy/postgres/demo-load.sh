#!/bin/sh
# Демонстрационный снимок данных при первом запуске стенда (deploy/demo/snapshot).
# Одноразовый контейнер `demo-db` после db-init и до старта сервисов: если DEMO_DATA=true и
# стенд ещё пустой (в org_db нет таблиц), каждая БД сервиса заполняется из своего дампа.
# Базы Keycloak в снимке нет: учётные записи операторов пересоздаёт `demo-operators`.
# На уже работающем стенде ничего не делает — данные не перезаписываются.
set -eu

export PGHOST=postgres PGUSER="$POSTGRES_USER" PGPASSWORD="$POSTGRES_PASSWORD"
sql() { psql -v ON_ERROR_STOP=1 -qtA "$@"; }

case "${DEMO_DATA:-false}" in
    true | 1 | yes) ;;
    *) echo "DEMO_DATA выключен — стенд стартует без демонстрационных данных"; exit 0 ;;
esac
if ! ls /snapshot/*.dump > /dev/null 2>&1; then
    echo "Снимка демо-данных нет (deploy/demo/snapshot) — пропускаю"
    exit 0
fi
if [ -n "$(sql -d org_db -c "SELECT to_regclass('public.alembic_version')")" ]; then
    echo "Стенд уже инициализирован — демо-данные не загружаются"
    exit 0
fi

cd /snapshot
if [ -f SHA256SUMS ]; then
    sha256sum -c SHA256SUMS > /dev/null
fi
for file in ./*.dump; do
    db="$(basename "$file" .dump)"
    owner="$(sql -d postgres -c "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = '$db'")"
    if [ -z "$owner" ]; then
        echo "  $db: такой БД нет в этой версии — пропускаю" >&2
        continue
    fi
    sql -d postgres -c "DROP DATABASE IF EXISTS \"$db\" WITH (FORCE)"
    sql -d postgres -c "CREATE DATABASE \"$db\" OWNER \"$owner\""
    pg_restore -d "$db" --exit-on-error "$file"
    echo "  $db: загружена из снимка"
done
echo "Демо-данные загружены (снимок от $(cat SNAPSHOT_DATE 2>/dev/null || echo '?'))"
