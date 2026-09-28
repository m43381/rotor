#!/usr/bin/env bash
# Эксплуатация стенда DutyFlow (фаза 7c). Нужны только bash и Docker с плагином compose:
# Python, just и доступ в интернет на сервере не требуются.
#
#   ./dutyflow.sh install            первая установка из пакета поставки: образы, .env, сертификаты
#   ./dutyflow.sh update             установка новой версии пакета поверх старой (с резервной копией)
#   ./dutyflow.sh up | down | status | logs [сервис]
#   ./dutyflow.sh backup             резервная копия всех БД (включая Keycloak) и настроек
#   ./dutyflow.sh restore <каталог>  восстановление из копии (стенд останавливается)
#   ./dutyflow.sh doctor             проверка: контейнеры, /health, очереди, сертификат, копии
#   ./dutyflow.sh certs              перевыпуск сертификата HTTPS на имена из TLS_HOSTS
#
# Скрипт лежит рядом с docker-compose.yml и .env: в репозитории — в deploy/, в пакете — в корне.
set -euo pipefail
export MSYS_NO_PATHCONV=1 # Git Bash на Windows не должен переписывать пути внутри контейнеров

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$DIR/.env"
compose() { docker compose -f "$DIR/docker-compose.yml" --env-file "$ENV_FILE" "$@"; }

say() { printf '%s\n' "$*"; }
die() { printf 'Ошибка: %s\n' "$*" >&2; exit 1; }

env_value() { # значение переменной из .env (без подстановок)
    local key="$1" default="${2:-}" line
    line="$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -n1 || true)"
    if [ -n "$line" ]; then printf '%s' "${line#*=}"; else printf '%s' "$default"; fi
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

# --- .env и сертификаты ----------------------------------------------------------------------

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
    say "Проверьте PUBLIC_URL и TLS_HOSTS (адрес сервера в сети) до первого запуска."
}

issue_certs() { # $1=force — перевыпустить сертификат сервера
    local certs="$DIR/certs"
    mkdir -p "$certs"
    if [ -f "$certs/server.crt" ] && [ "${1:-}" != force ]; then return; fi
    local args=() user=()
    IFS=',' read -ra hosts <<< "$(env_value TLS_HOSTS localhost)"
    for h in "${hosts[@]}"; do h="${h// /}"; [ -n "$h" ] && args+=(--host "$h"); done
    [ "$(uname -s)" = Linux ] && user=(--user "$(id -u):$(id -g)")
    compose run --rm --no-deps "${user[@]}" -v "$(host_path "$certs"):/out" ops \
        python -m dutyflow_common.certs generate --out /out "${args[@]}"
    say "Корневой сертификат для рабочих мест: $certs/ca.crt (установка — README, «HTTPS»)"
}

# --- Команды ---------------------------------------------------------------------------------

cmd_install() {
    load_images
    make_env
    issue_certs
    cmd_up
    say "Готово. Адрес: $(env_value PUBLIC_URL), вход: admin / DUTYFLOW_ADMIN_PASSWORD из .env"
    say "Проверка: ./dutyflow.sh doctor (через 1–2 минуты, пока стартует Keycloak)"
}

cmd_update() {
    require_env
    if compose ps --status running -q postgres | grep -q .; then
        say "Резервная копия перед обновлением:"
        cmd_backup
    fi
    load_images
    make_env
    issue_certs
    cmd_up
    say "Обновлено до версии $(env_value DUTYFLOW_VERSION dev). Откат — README, «Откат»."
}

load_images() {
    [ -f "$DIR/images.tar" ] || die "нет images.tar рядом со скриптом (это пакет поставки?)"
    if [ -f "$DIR/MANIFEST.sha256" ]; then
        say "Проверка контрольных сумм пакета…"
        (cd "$DIR" && sha256sum -c MANIFEST.sha256 > /dev/null) || die "пакет повреждён"
    fi
    say "Загрузка образов (несколько минут)…"
    docker load -i "$DIR/images.tar"
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
    say "Восстановлено. Настройки копии (.env, certs) — в $src/config, если стенд переносится."
}

cmd_doctor() {
    require_env
    local failed=0
    say "Контейнеры:"
    # Разделитель не пробельный: иначе read склеит пустое поле Health с соседними
    while IFS='|' read -r service state health status; do
        case "$service" in
            db-init | keycloak-init)
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

cmd="${1:-}"
shift || true
case "$cmd" in
    install) cmd_install ;;
    update) cmd_update ;;
    up) cmd_up ;;
    down) cmd_down ;;
    status) cmd_status ;;
    logs) cmd_logs "$@" ;;
    backup) cmd_backup ;;
    restore) cmd_restore "$@" ;;
    doctor) cmd_doctor ;;
    certs) require_env; issue_certs force; compose restart gateway; say "Шлюз перезапущен с новым сертификатом" ;;
    *) sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; [ -z "$cmd" ] || exit 1 ;;
esac
