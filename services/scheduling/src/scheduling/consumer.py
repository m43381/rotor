"""Консьюмер событий org для проекций scheduling: `python -m scheduling.consumer`.

При первом запуске (проекция пуста) выполняет полную синхронизацию через batch-API org,
затем слушает `events:unit`, `events:rank` и `events:calendar` (ADR-0011).

События personnel (`person.*`, `exemption.*`, `clearance.*`) перепроверяют будущие назначения
человека и помечают конфликты (open-questions №39): назначения не снимаются автоматически.
"""

import asyncio
import contextlib
import logging
import signal
import uuid

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from dutyflow_common.app import setup_logging
from dutyflow_common.calendar import handle_calendar_event, resync_calendar
from dutyflow_common.db import Database
from dutyflow_common.events import Event, EventConsumer, Handler
from dutyflow_common.internal import InternalClient
from dutyflow_common.projections import handle_rank_event, handle_unit_event
from dutyflow_common.sync import resync_org
from scheduling.assignments import recompute_conflicts
from scheduling.people import PeopleLoader, http_people_loader
from scheduling.settings import SchedulingSettings

log = logging.getLogger(__name__)


def conflicts_handler(people: PeopleLoader) -> Handler:
    async def handle(session: AsyncSession, event: Event) -> None:
        person_id = event.payload.get("person_id")
        if person_id:
            await recompute_conflicts(session, people, [uuid.UUID(str(person_id))])

    return handle


async def main(settings: SchedulingSettings) -> None:
    db = Database(settings.database_url)
    redis = Redis.from_url(settings.redis_url)
    org = InternalClient(settings.org_url, settings.internal_token, retries=10)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    conflicts = conflicts_handler(http_people_loader(settings))
    consumer = EventConsumer(
        "scheduling",
        db.sessionmaker,
        redis,
        {
            "events:unit": handle_unit_event,
            "events:rank": handle_rank_event,
            "events:calendar": handle_calendar_event,
            "events:person": conflicts,
            "events:exemption": conflicts,
            "events:clearance": conflicts,
        },
    )
    try:
        # Группа создаётся до пересинхронизации: события, пришедшие во время неё, не потеряются
        # и будут применены после (проекция сравнивает версии узлов).
        await consumer.ensure_groups()
        if await resync_org(db.sessionmaker, org, only_if_empty=True):
            await resync_calendar(db.sessionmaker, org)
        await consumer.run(stop)
    finally:
        await org.aclose()
        await redis.aclose()
        await db.dispose()


if __name__ == "__main__":
    s = SchedulingSettings()
    setup_logging(s.log_level)
    asyncio.run(main(s))
