#!/bin/sh
# Снимок демонстрационных данных для репозитория (`dutyflow.sh demo-snapshot`): дампы всех БД
# сервисов, кроме Keycloak (в ней пароли этой инсталляции). Каталог снимка смонтирован в /out.
set -eu

export PGHOST=postgres PGUSER="$POSTGRES_USER" PGPASSWORD="$POSTGRES_PASSWORD"

rm -f /out/*.dump /out/SHA256SUMS
for db in org_db personnel_db scheduling_db documents_db analytics_db auth_admin_db; do
    pg_dump -d "$db" -Fc -Z 9 -f "/out/$db.dump"
    echo "  $db: $(du -h "/out/$db.dump" | cut -f1)"
done
date +%Y-%m-%d > /out/SNAPSHOT_DATE
(cd /out && sha256sum ./*.dump > SHA256SUMS)
echo "Снимок БД: deploy/demo/snapshot"
