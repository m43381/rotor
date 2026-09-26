"""Полная пересинхронизация проекций org (ADR-0011): при первом старте сервиса или по команде."""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dutyflow_common.internal import InternalClient
from dutyflow_common.projections import UnitProjection, upsert_ranks, upsert_units

log = logging.getLogger(__name__)


async def resync_org(
    sessionmaker: async_sessionmaker[AsyncSession], org: InternalClient, *, only_if_empty: bool
) -> bool:
    """Загружает все подразделения и звания из org. Возвращает True, если синхронизация была."""
    async with sessionmaker() as session:
        if only_if_empty and await session.scalar(select(func.count()).select_from(UnitProjection)):
            return False
    units = await org.post("/internal/units/batch", {"unit_ids": [], "include_inactive": True})
    ranks = await org.post("/internal/ranks", {})
    async with sessionmaker() as session, session.begin():
        # Пачками: одна вставка с десятками тысяч строк упирается в лимит параметров asyncpg.
        for i in range(0, len(units), 2000):
            await upsert_units(session, units[i : i + 2000])
        await upsert_ranks(session, ranks)
    log.info("Проекции org синхронизированы: %d подразделений, %d званий", len(units), len(ranks))
    return True
