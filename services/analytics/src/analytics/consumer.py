"""Консьюмер событий для read-model analytics: `python -m analytics.consumer`.

Подразделения — проекция org (`events:unit`, при пустой проекции — полная синхронизация).
Факты нарядов — `events:assignment` и `events:schedule` от scheduling. При первом запуске
(фактов нет) read-model заполняется выгрузкой из scheduling — как `analytics.rebuild`.
Сводный журнал аудита — `events:audit` от всех сервисов; пустой журнал заполняется выгрузкой
`/internal/audit` из каждого сервиса (фаза 7b).
"""

import asyncio
import contextlib
import logging
import signal

from redis.asyncio import Redis
from sqlalchemy import func, select

from analytics.facts import handle_assignment_event, handle_schedule_event
from analytics.journal import handle_audit_event, rebuild_journal
from analytics.models import AuditEntry, DutyFact
from analytics.rebuild import rebuild
from analytics.settings import AnalyticsSettings
from dutyflow_common.app import setup_logging
from dutyflow_common.db import Database
from dutyflow_common.events import EventConsumer
from dutyflow_common.internal import InternalClient
from dutyflow_common.projections import handle_rank_event, handle_unit_event
from dutyflow_common.sync import resync_org

log = logging.getLogger(__name__)


async def main(settings: AnalyticsSettings) -> None:
    db = Database(settings.database_url)
    redis = Redis.from_url(settings.redis_url)
    org = InternalClient(settings.org_url, settings.internal_token, retries=10)
    scheduling = InternalClient(settings.scheduling_url, settings.internal_token, retries=10)
    sources = {
        name: InternalClient(url, settings.internal_token, retries=3)
        for name, url in settings.audit_sources().items()
    }
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    consumer = EventConsumer(
        "analytics",
        db.sessionmaker,
        redis,
        {
            "events:unit": handle_unit_event,
            "events:rank": handle_rank_event,
            "events:assignment": handle_assignment_event,
            "events:schedule": handle_schedule_event,
            "events:audit": handle_audit_event,
        },
    )
    try:
        # Группы — до начального заполнения: события, пришедшие во время него, применятся после
        # (обработчики идемпотентны)
        await consumer.ensure_groups()
        await resync_org(db.sessionmaker, org, only_if_empty=True)
        async with db.sessionmaker() as session:
            empty = not await session.scalar(select(func.count()).select_from(DutyFact))
            no_journal = not await session.scalar(select(func.count()).select_from(AuditEntry))
        if empty:
            await rebuild(db.sessionmaker, scheduling)
        if no_journal:
            await rebuild_journal(db.sessionmaker, sources)
        await consumer.run(stop)
    finally:
        await org.aclose()
        await scheduling.aclose()
        for client in sources.values():
            await client.aclose()
        await redis.aclose()
        await db.dispose()


if __name__ == "__main__":
    s = AnalyticsSettings()
    setup_logging(s.log_level)
    asyncio.run(main(s))
