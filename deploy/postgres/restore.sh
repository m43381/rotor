#!/bin/sh
# Восстановление всех БД из резервной копии (фаза 7c, open-questions №63).
# Запускается в одноразовом контейнере `ops-db` при остановленных сервисах
# (`dutyflow.sh restore <каталог>`): каталог копии смонтирован в /restore.
# Роли и пустые БД к этому моменту созданы db-init; каждая БД пересоздаётся и заполняется
# из дампа с исходными владельцами объектов.
set -eu

export PGHOST=postgres PGUSER="$POSTGRES_USER" PGPASSWORD="$POSTGRES_PASSWORD"
sql() { psql -v ON_ERROR_STOP=1 -qtA "$@"; }

cd /restore
if ! ls ./*.dump >/dev/null 2>&1; then
    echo "В каталоге копии нет файлов *.dump" >&2
    exit 1
fi
if [ -f SHA256SUMS ]; then
    sha256sum -c SHA256SUMS > /dev/null
    echo "Контрольные суммы совпадают"
fi

for file in ./*.dump; do
    db="$(basename "$file" .dump)"
    # Владелец — роль сервиса, которой db-init создал эту БД
    owner="$(sql -d postgres -c "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = '$db'")"
    if [ -z "$owner" ]; then
        echo "  $db: нет роли-владельца (БД неизвестна этой версии?) — пропускаю" >&2
        continue
    fi
    sql -d postgres -c "DROP DATABASE IF EXISTS \"$db\" WITH (FORCE)"
    sql -d postgres -c "CREATE DATABASE \"$db\" OWNER \"$owner\""
    pg_restore -d "$db" --exit-on-error "$file"
    echo "  $db: восстановлена (владелец $owner)"
done
echo "БД восстановлены"
