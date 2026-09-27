"""Консьюмер событий для локальных копий personnel: `python -m personnel.consumer`.

- `events:unit`, `events:rank` — проекции org (ADR-0011);
- `events:duty_type`, `events:duty_role` — требования ролей нарядов из scheduling (ADR-0009).

При первом запуске (копия пуста) выполняет полную синхронизацию через batch-API владельца.
"""

import asyncio
import contextlib
import logging
import signal

from redis.asyncio import Redis

from dutyflow_common.app import setup_logging
from dutyflow_common.db import Database
from dutyflow_common.events import EventConsumer
from dutyflow_common.internal import InternalClient
from dutyflow_common.projections import handle_rank_event, handle_unit_event
from dutyflow_common.sync import resync_org
from personnel.duty_roles import handle_duty_event, resync_scheduling
from personnel.settings import PersonnelSettings

log = logging.getLogger(__name__)


async def main(settings: PersonnelSettings) -> None:
    db = Database(settings.database_url)
    redis = Redis.from_url(settings.redis_url)
    org = InternalClient(settings.org_url, settings.internal_token, retries=10)
    scheduling = InternalClient(settings.scheduling_url, settings.internal_token, retries=10)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    consumer = EventConsumer(
        "personnel",
        db.sessionmaker,
        redis,
        {
            "events:unit": handle_unit_event,
            "events:rank": handle_rank_event,
            "events:duty_type": handle_duty_event,
            "events:duty_role": handle_duty_event,
        },
    )
    try:
        # Группа создаётся до пересинхронизации: события, пришедшие во время неё, не потеряются
        # и будут применены после (проекция сравнивает версии узлов).
        await consumer.ensure_groups()
        await resync_org(db.sessionmaker, org, only_if_empty=True)
        await resync_scheduling(db.sessionmaker, scheduling, only_if_empty=True)
        await consumer.run(stop)
    finally:
        await org.aclose()
        await scheduling.aclose()
        await redis.aclose()
        await db.dispose()


if __name__ == "__main__":
    s = PersonnelSettings()
    setup_logging(s.log_level)
    asyncio.run(main(s))
