#!/usr/bin/env bash
# Эксплуатация стенда DutyFlow (фаза 7c). Нужны только bash и Docker с плагином compose:
# Python, just и доступ в интернет на сервере не требуются.
#
#   ./dutyflow.sh init               создать .env со случайными паролями (установка из git:
#                                    затем `docker compose up -d --build` в этом же каталоге)
#   ./dutyflow.sh install            первая установка: .env, образы (из пакета или сборка), запуск
#   ./dutyflow.sh update <каталог>   переход на эту версию с прежней (каталог прежнего пакета):
#                                    перенос .env, резервная копия, запуск
#   ./dutyflow.sh up | down | status | logs [сервис]
#   ./dutyflow.sh backup             резервная копия всех БД (включая Keycloak) и настроек
#   ./dutyflow.sh restore <каталог>  восстановление из копии (стенд останавливается)
#   ./dutyflow.sh doctor             проверка: контейнеры, /health, очереди, свежесть копий
#   ./dutyflow.sh demo               сгенерировать демо-данные (стенд должен быть запущен)
#   ./dutyflow.sh demo-snapshot      сохранить текущие данные стенда как демо-снимок для git
#
# Скрипт лежит рядом с docker-compose.yml и .env: в репозитории — в deploy/, в пакете — в корне.
set -euo pipefail
export MSYS_NO_PATHCONV=1 # Git Bash на Windows не должен переписывать пути внутри контейнеров

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$DIR/.env"
# Пути для docker — в форме хоста (на Windows с Git Bash /tmp и т. п. не совпадают с C:)
DIR_HOST="$(cd "$DIR" && (pwd -W 2>/dev/null || pwd))"
compose() { docker compose -f "$DIR_HOST/docker-compose.yml" --env-file "$DIR_HOST/.env" "$@"; }

say() { printf '%s\n' "$*"; }
die() { printf 'Ошибка: %s\n' "$*" >&2; exit 1; }

env_value() { # значение переменной из .env; ссылки ${VAR} на другие строки .env раскрываются
    local key="$1" default="${2:-}" line value ref re='\$\{([A-Za-z0-9_]+)\}'
    line="$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -n1 || true)"
    if [ -z "$line" ]; then printf '%s' "$default"; return; fi
    value="${line#*=}"
    while [[ "$value" =~ $re ]]; do
        ref="${BASH_REMATCH[1]}"
        value="${value//"\${$ref}"/"$(env_value "$ref")"}"
    done
    printf '%s' "$value"
}

host_path() { # абсолютный путь в форме, понятной Docker (на Windows — C:/...)
    (cd "$1" && (pwd -W 2>/dev/null || pwd))
}

backup_dir() {
    local dir
    dir="$(env_value BACKUP_DIR ./backups)"
    case "$dir" in /*) ;; *) dir="$DIR/${dir#./}" ;; esac
    mkdir -p "$dir"
    printf '%s' "$dir"
}

require_env() { [ -f "$ENV_FILE" ] || die "нет $ENV_FILE — сначала ./dutyflow.sh install"; }

# --- .env ----------------------------------------------------------------------------------

random_secret() { head -c 18 /dev/urandom | base64 | tr '+/' '-_'; }

make_env() {
    if [ -f "$ENV_FILE" ]; then
        # Новые переменные шаблона дописываются, существующие секреты не меняются
        local added=()
        while IFS= read -r line; do
            [[ "$line" =~ ^([A-Z0-9_]+)= ]] || continue
            grep -qE "^${BASH_REMATCH[1]}=" "$ENV_FILE" && continue
            [[ "$line" == *=CHANGE_ME ]] && line="${line%CHANGE_ME}$(random_secret)"
            printf '%s\n' "$line" >> "$ENV_FILE"
            added+=("${BASH_REMATCH[1]}")
        done < "$DIR/.env.example"
        [ ${#added[@]} -eq 0 ] || say "В .env добавлены новые переменные: ${added[*]}"
        return
    fi
    while IFS= read -r line; do
        [[ "$line" == *=CHANGE_ME ]] && line="${line%CHANGE_ME}$(random_secret)"
        printf '%s\n' "$line"
    done < "$DIR/.env.example" > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    say "Создан $ENV_FILE со случайными секретами. Пароль admin: DUTYFLOW_ADMIN_PASSWORD."
}

# --- Команды ---------------------------------------------------------------------------------

cmd_init() {
    [ -f "$ENV_FILE" ] && say "$ENV_FILE уже есть — пароли не меняются."
    make_env
    say "Проверьте в .env: SERVER_HOST (IP или имя сервера), GATEWAY_PORT (внешний порт)"
    say "и BACKUP_DIR. Затем в этом каталоге: docker compose up -d --build"
}

cmd_install() {
    if [ ! -f "$ENV_FILE" ]; then
        # Адрес сервера нужен до выпуска сертификата и первого запуска Keycloak
        make_env
        say "Укажите в .env SERVER_HOST, GATEWAY_PORT и BACKUP_DIR и запустите ./dutyflow.sh install ещё раз."
        return
    fi
    if [ -f "$DIR/images.tar.gz" ]; then
        load_images
    else
        # Каталог deploy/ репозитория: образы собираются из исходников
        say "Сборка образов из исходников (в первый раз — 5–15 минут)…"
        compose build
    fi
    make_env
    cmd_up
    say "Готово. Адрес: $(env_value PUBLIC_URL), вход: admin / DUTYFLOW_ADMIN_PASSWORD из .env"
    say "Проверка: ./dutyflow.sh doctor (через 1–2 минуты, пока стартует Keycloak)"
}

cmd_update() {
    local old="${1:-}"
    if [ -n "$old" ]; then
        [ -f "$old/.env" ] || die "в $old нет .env — укажите каталог прежней версии"
        [ "$(cd "$old" && pwd)" != "$DIR" ] || die "укажите каталог прежней версии, а не текущий"
        if [ ! -f "$ENV_FILE" ]; then cp -p "$old/.env" "$ENV_FILE"; fi
        say "Настройки перенесены из $old"
    fi
    require_env
    if compose ps --status running -q postgres | grep -q .; then
        say "Резервная копия перед обновлением:"
        cmd_backup
    fi
    load_images
    make_env
    cmd_up
    say "Обновлено до версии $(env_value DUTYFLOW_VERSION dev). Откат — README, «Откат»."
}

load_images() {
    [ -f "$DIR/images.tar.gz" ] || die "нет images.tar.gz рядом со скриптом (это пакет поставки?)"
    if [ -f "$DIR/MANIFEST.sha256" ]; then
        say "Проверка контрольных сумм пакета…"
        (cd "$DIR" && sha256sum -c MANIFEST.sha256 > /dev/null) || die "пакет повреждён"
    fi
    say "Загрузка образов (несколько минут)…"
    docker load -i "$DIR_HOST/images.tar.gz"
    local version
    version="$(cat "$DIR/VERSION")"
    if [ -f "$ENV_FILE" ] && grep -q '^DUTYFLOW_VERSION=' "$ENV_FILE"; then
        sed -i.bak "s/^DUTYFLOW_VERSION=.*/DUTYFLOW_VERSION=$version/" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
    elif [ -f "$ENV_FILE" ]; then
        printf 'DUTYFLOW_VERSION=%s\n' "$version" >> "$ENV_FILE"
    fi
}

cmd_up() { require_env; compose up -d --remove-orphans; }
cmd_down() { require_env; compose down; }
cmd_status() { require_env; compose ps -a; }
cmd_logs() { require_env; compose logs -f --tail=200 "$@"; }

cmd_backup() {
    require_env
    local stamp
    stamp="$(date +%Y%m%d-%H%M%S)"
    compose run --rm -e BACKUP_STAMP="$stamp" -v "$(host_path "$(backup_dir)"):/backups" ops-db \
        sh /scripts/backup.sh
    say "Каталог копии на сервере: $(backup_dir)/$stamp"
}

cmd_restore() {
    require_env
    local src="${1:-}" yes="${2:-}"
    [ -n "$src" ] && [ -d "$src" ] || die "укажите каталог копии: ./dutyflow.sh restore <каталог>"
    ls "$src"/*.dump >/dev/null 2>&1 || die "в $src нет файлов *.dump"
    if [ "$yes" != "--yes" ]; then
        say "Все текущие данные стенда будут заменены данными копии $src."
        read -r -p "Продолжить? Введите «да»: " answer
        [ "$answer" = "да" ] || die "отменено"
    fi
    say "Остановка сервисов…"
    compose stop
    compose up -d postgres redis
    compose run --rm db-init
    compose run --rm -v "$(host_path "$src"):/restore:ro" ops-db sh /scripts/restore.sh
    # Очереди событий после точки копии не относятся к восстановленным данным; неотправленное
    # из outbox уйдёт заново, повторы отсекаются отметками обработки (ADR-0004)
    compose exec -T redis redis-cli FLUSHALL > /dev/null
    say "Redis очищен (очереди событий и фоновых задач)"
    compose up -d
    say "Восстановлено. Настройки копии (.env) — в $src/config, если стенд переносится."
}

cmd_doctor() {
    require_env
    local failed=0
    say "Контейнеры:"
    # Разделитель не пробельный: иначе read склеит пустое поле Health с соседними
    while IFS='|' read -r service state health status; do
        case "$service" in
            db-init | keycloak-init | demo-db | demo-operators)
                if [[ "$status" == "Exited (0)"* ]]; then say "   $service: выполнен"
                else say "!! $service: $status — ./dutyflow.sh logs $service"; failed=1; fi ;;
            *)
                if [ "$state" != running ]; then say "!! $service: $state"; failed=1
                elif [ "$health" = unhealthy ]; then say "!! $service: unhealthy"; failed=1
                elif [ "$health" = starting ]; then say "~~ $service: запускается"
                else say "   $service: работает"; fi ;;
        esac
    done < <(compose ps -a --format '{{.Service}}|{{.State}}|{{.Health}}|{{.Status}}')
    # Служебные строки compose о создании контейнера в отчёте не нужны
    compose run --rm --no-deps ops 2> >(grep -v '^ Container ' >&2) || failed=1
    say "Резервные копии:"
    local dir last
    dir="$(backup_dir)"
    last="$(find "$dir" -mindepth 1 -maxdepth 1 -type d -name '20*' -mtime -2 | sort | tail -n1)"
    if [ -n "$last" ]; then say "   последняя: $(basename "$last")"
    else say "~~ за последние сутки копий нет в $dir (ежедневный запуск — README, «Резервные копии»)"; fi
    say "   свободно на диске копий: $(df -h "$dir" | awk 'NR==2 {print $4}')"
    return $failed
}

cmd_demo_snapshot() { # БД сервисов (без Keycloak) и список операторов → demo/snapshot
    require_env
    mkdir -p "$DIR/demo/snapshot"
    compose run --rm --no-deps -v "$(host_path "$DIR/demo/snapshot"):/out" ops-db         sh /scripts/demo-snapshot.sh
    compose --profile demo run --rm --no-deps -e DEMO_SNAPSHOT_DIR=/out         -v "$(host_path "$DIR/demo/snapshot"):/out" demo python /demo/operators.py export
    say "Снимок готов: $DIR/demo/snapshot — закоммитьте его, чтобы он попал на сервер"
}

cmd="${1:-}"
shift || true
case "$cmd" in
    init) cmd_init ;;
    install) cmd_install ;;
    update) cmd_update "$@" ;;
    up) cmd_up ;;
    down) cmd_down ;;
    status) cmd_status ;;
    logs) cmd_logs "$@" ;;
    backup) cmd_backup ;;
    restore) cmd_restore "$@" ;;
    doctor) cmd_doctor ;;
    demo) require_env; compose --profile demo run --rm demo ;;
    demo-snapshot) cmd_demo_snapshot ;;
    *) sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; [ -z "$cmd" ] || exit 1 ;;
esac
