"""Признак жизни фоновых процессов без HTTP-порта: релеев outbox и консьюмеров (фаза 7c).

Процесс после каждого успешного цикла обновляет время файла `HEARTBEAT_FILE`; проверка
готовности контейнера (`python -m dutyflow_common.heartbeat 60`) требует, чтобы файл
обновлялся не реже заданного числа секунд. Зависший или непрерывно падающий цикл даёт
статус unhealthy, который видят `docker compose ps` и `dutyflow.sh doctor`.
"""

import contextlib
import os
import sys
import time
from pathlib import Path


def _path() -> Path:
    return Path(os.environ.get("HEARTBEAT_FILE", "/tmp/heartbeat"))  # noqa: S108


def beat() -> None:
    # Признак жизни не должен ронять сам процесс
    with contextlib.suppress(OSError):
        _path().touch()


def main(argv: list[str]) -> int:
    max_age = float(argv[0]) if argv else 60.0
    try:
        age = time.time() - _path().stat().st_mtime
    except FileNotFoundError:
        print("нет признака жизни")
        return 1
    if age > max_age:
        print(f"признак жизни устарел: {age:.0f} с")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
