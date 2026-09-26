"""Процесс-релей outbox → Redis Streams (ADR-0004). Запускается отдельным контейнером
рядом с сервисом: `python -m <service>.relay`."""

import asyncio
import contextlib
import logging
import signal

from redis.asyncio import Redis

from dutyflow_common.db import Database
from dutyflow_common.outbox import relay_once
from dutyflow_common.settings import ServiceSettings

log = logging.getLogger(__name__)


async def run_relay(settings: ServiceSettings, *, idle_sleep: float = 1.0) -> None:
    db = Database(settings.database_url)
    redis = Redis.from_url(settings.redis_url)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        # На Windows сигналы в asyncio не поддерживаются — там релей останавливают Ctrl+C.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    log.info("Релей outbox запущен: %s", settings.service_name)
    try:
        while not stop.is_set():
            try:
                sent = await relay_once(db.sessionmaker, redis)
            except Exception:
                log.exception("Ошибка публикации событий, повтор через %s с", idle_sleep * 5)
                sent = 0
                await asyncio.sleep(idle_sleep * 4)
            if sent == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=idle_sleep)
    finally:
        await redis.aclose()
        await db.dispose()
