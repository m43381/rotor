"""Отдельный стенд для нагрузки: compose-проект `dutyflow-load` со своими томами и портами
9080/9443, настройки — `deploy/.env.load` (копия `deploy/.env` с другим адресом).
Рабочий стенд разработки при этом не трогается; на время прогона его лучше остановить."""

import asyncio
import time

import httpx

from tools.load.common import (
    BASE_URL,
    ENV_FILE,
    HTTPS_PORT,
    ROOT,
    client,
    compose_cmd,
    run,
)

SERVICES = ("org", "personnel", "scheduling", "allocation", "documents", "analytics", "auth-admin")


def make_env() -> None:
    if ENV_FILE.exists():
        return
    source = ROOT / "deploy" / ".env"
    if not source.exists():
        raise SystemExit("Нет deploy/.env — сначала `just env`")
    lines = []
    for line in source.read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0]
        line = {
            "PUBLIC_URL": f"PUBLIC_URL={BASE_URL}",
            "GATEWAY_PORT": "GATEWAY_PORT=9080",
            "GATEWAY_HTTPS_PORT": f"GATEWAY_HTTPS_PORT={HTTPS_PORT}",
            "BACKUP_DIR": "BACKUP_DIR=./backups-load",
            # Эталон — 8 CPU / 16 ГБ (№62): воркеру распределения — как на эталоне
            "ALLOCATION_WORKER_MEMORY": "ALLOCATION_WORKER_MEMORY=4g",
        }.get(key, line)
        lines.append(line)
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"Создан {ENV_FILE.relative_to(ROOT)}")


async def wait_ready(limit_s: float = 600) -> None:
    deadline = time.monotonic() + limit_s
    async with client(timeout=5) as http:
        while True:
            try:
                paths = [f"/api/{s}/health" for s in SERVICES]
                paths.append("/auth/realms/dutyflow/.well-known/openid-configuration")
                codes = [(await http.get(p)).status_code for p in paths]
                if all(c == 200 for c in codes):
                    return
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                raise SystemExit(
                    "Нагрузочный стенд не поднялся — `docker compose -p dutyflow-load ps`"
                )
            await asyncio.sleep(5)


def up() -> None:
    make_env()
    run(compose_cmd("up", "-d"))
    asyncio.run(wait_ready())
    print(f"Нагрузочный стенд готов: {BASE_URL}")


def down() -> None:
    run(compose_cmd("--profile", "ops", "down", "-v"))
    print("Нагрузочный стенд удалён вместе с данными")
