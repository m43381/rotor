#!/bin/sh
# Резервная копия всех БД инсталляции, включая Keycloak (фаза 7c, open-questions №63).
# Запускается в одноразовом контейнере `ops-db` (`dutyflow.sh backup`, `just backup`):
#   /backups/<ГГГГММДД-ЧЧММСС>/<БД>.dump  — pg_dump в формате custom (сжатый);
#   /backups/<...>/SHA256SUMS             — контрольные суммы;
#   /backups/<...>/config/                — .env и сертификаты (секреты: копия хранится как
#                                           сами данные, шифрование — средствами хоста);
# копии старше BACKUP_KEEP_DAYS дней удаляются. Каждая БД снимается согласованным снимком;
# между БД разница — секунды, это покрывается идемпотентной доставкой событий (ADR-0004).
set -eu

export PGHOST=postgres PGUSER="$POSTGRES_USER" PGPASSWORD="$POSTGRES_PASSWORD"
keep="${BACKUP_KEEP_DAYS:-14}"
stamp="${BACKUP_STAMP:-$(date +%Y%m%d-%H%M%S)}"
target="/backups/$stamp"
partial="/backups/.$stamp.partial"

mkdir -p "$partial"
dbs="$(psql -d postgres -qtA -c "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres' ORDER BY datname")"
for db in $dbs; do
    pg_dump -d "$db" -Fc -Z 6 -f "$partial/$db.dump"
    echo "  $db: $(du -h "$partial/$db.dump" | cut -f1)"
done
psql -d postgres -qtA -c "SELECT version()" > "$partial/POSTGRES_VERSION"
(cd "$partial" && sha256sum ./*.dump > SHA256SUMS)
if [ -d /config ]; then
    mkdir -p "$partial/config"
    cp -R /config/. "$partial/config/"
    chmod -R go-rwx "$partial/config"
fi
# Каталог появляется целиком: прерванная копия не выглядит готовой
mv "$partial" "$target"
echo "Резервная копия: $target"

find /backups -mindepth 1 -maxdepth 1 -type d -name '20*' -mtime "+$((keep - 1))" | while read -r old; do
    rm -rf "$old"
    echo "Удалена копия старше $keep дн.: $old"
done
find /backups -mindepth 1 -maxdepth 1 -type d -name '.*.partial' -mmin +720 -exec rm -rf {} +
