"""Проверка работоспособности стенда изнутри сети compose (фаза 7c, `just doctor`).

    python -m dutyflow_common.doctor

Запускается одноразовым контейнером `ops` (профиль `ops` в compose) и проверяет:
- `/health` всех сервисов и готовность Keycloak;
- очереди событий: отставание (`lag`) и неподтверждённые сообщения групп консьюмеров,
  непустые DLQ;
- срок действия сертификата HTTPS (каталог `certs` смонтирован в `/certs`).

Код выхода: 0 — всё в порядке, 1 — есть проблемы (печатаются с пометкой «!!»),
предупреждения («~~») на код выхода не влияют.
"""

import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from redis.asyncio import Redis

from dutyflow_common.certs import days_left

SERVICES = ("org", "personnel", "scheduling", "allocation", "documents", "analytics", "auth-admin")
KEYCLOAK_READY = "http://keycloak:9000/auth/health/ready"
# Отставание консьюмера, при котором стоит насторожиться (событий в очереди)
LAG_WARN = 1000
CERT_WARN_DAYS = 30


@dataclass
class Report:
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def ok(self, text: str) -> None:
        print(f"   {text}")

    def warn(self, text: str) -> None:
        self.warnings.append(text)
        print(f"~~ {text}")

    def fail(self, text: str) -> None:
        self.problems.append(text)
        print(f"!! {text}")


async def check_http(report: Report) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:

        async def probe(name: str, url: str) -> None:
            try:
                response = await client.get(url)
            except httpx.HTTPError as exc:
                report.fail(f"{name}: недоступен ({type(exc).__name__})")
                return
            if response.status_code == 200:
                report.ok(f"{name}: работает")
            else:
                report.fail(f"{name}: ответ {response.status_code}")

        await asyncio.gather(
            *(probe(name, f"http://{name}:8000/health") for name in SERVICES),
            probe("keycloak", KEYCLOAK_READY),
        )


async def check_streams(report: Report, redis: Redis) -> None:
    streams = sorted([_s(key) async for key in redis.scan_iter(match="events:*", _type="STREAM")])
    for stream in streams:
        for group in await redis.xinfo_groups(stream):
            name = _s(group["name"])
            lag, pending = group.get("lag"), int(group["pending"])
            where = f"{stream} → {name}"
            if lag is not None and int(lag) >= LAG_WARN:
                report.warn(f"{where}: отставание {lag} событий")
            elif pending:
                report.warn(f"{where}: {pending} неподтверждённых")
            else:
                report.ok(f"{where}: отставание {lag or 0}")
    async for key in redis.scan_iter(match="dlq:*", _type="STREAM"):
        length = await redis.xlen(key)
        if length:
            report.fail(
                f"{_s(key)}: {length} необработанных событий (разбор — docs/runbook, «DLQ»)"
            )


def check_cert(report: Report, path: Path) -> None:
    if not path.exists():
        report.fail(f"нет сертификата {path.name}")
        return
    left = days_left(path)
    if left < 0:
        report.fail(f"сертификат {path.name} истёк")
    elif left < CERT_WARN_DAYS:
        report.warn(f"сертификат {path.name} истекает через {left} дн. — `certs`, затем `up`")
    else:
        report.ok(f"сертификат {path.name}: ещё {left} дн.")


def _s(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


async def run() -> Report:
    report = Report()
    print("Сервисы:")
    await check_http(report)
    print("Очереди событий:")
    redis = Redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
    try:
        await check_streams(report, redis)
    except OSError as exc:
        report.fail(f"Redis недоступен: {exc}")
    finally:
        await redis.aclose()
    print("HTTPS:")
    check_cert(report, Path(os.environ.get("CERTS_DIR", "/certs")) / "server.crt")
    return report


def main() -> int:
    report = asyncio.run(run())
    print()
    if report.problems:
        print(f"Проблем: {len(report.problems)}, предупреждений: {len(report.warnings)}")
        return 1
    print(f"Всё в порядке (предупреждений: {len(report.warnings)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
