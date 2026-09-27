"""Перестроение read-model с нуля: `python -m analytics.rebuild` (`just analytics-rebuild`).

Нужно при первом запуске (события до появления analytics в потоках могут быть обрезаны)
и после восстановления из резервной копии. Факты берутся из scheduling пачками по
возрастанию id назначения и заменяют текущие в одной транзакции.
"""

import asyncio
import logging

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analytics.facts import upsert_facts
from analytics.models import DutyFact
from analytics.settings import AnalyticsSettings
from dutyflow_common.app import setup_logging
from dutyflow_common.db import Database
from dutyflow_common.internal import InternalClient

log = logging.getLogger(__name__)
PAGE = 2_000


async def rebuild(
    sessionmaker: async_sessionmaker[AsyncSession], scheduling: InternalClient
) -> int:
    total = 0
    after: str | None = None
    async with sessionmaker() as session, session.begin():
        await session.execute(delete(DutyFact))
        while True:
            query = f"?limit={PAGE}" + (f"&after={after}" if after else "")
            page = await scheduling.get(f"/internal/assignments/facts{query}")
            if not page:
                break
            total += await upsert_facts(session, page)
            after = page[-1]["assignment_id"]
            if len(page) < PAGE:
                break
    log.info("Read-model analytics перестроена: %d фактов", total)
    return total


async def main(settings: AnalyticsSettings) -> None:
    db = Database(settings.database_url)
    scheduling = InternalClient(settings.scheduling_url, settings.internal_token, timeout=60.0)
    try:
        await rebuild(db.sessionmaker, scheduling)
    finally:
        await scheduling.aclose()
        await db.dispose()


if __name__ == "__main__":
    s = AnalyticsSettings()
    setup_logging(s.log_level)
    asyncio.run(main(s))
