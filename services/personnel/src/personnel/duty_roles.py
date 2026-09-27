"""Локальная копия типов нарядов и ролей из scheduling (события + пересинхронизация).

Владелец данных — scheduling. Версия записи защищает от устаревших событий так же, как в
проекции подразделений (ADR-0011).
"""

import logging
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dutyflow_common.events import Event
from dutyflow_common.internal import InternalClient
from personnel.models import DutyRoleProjection, DutyTypeProjection

log = logging.getLogger(__name__)


def _uuid(value: Any) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


async def upsert_duty_types(session: AsyncSession, types: Sequence[dict[str, Any]]) -> None:
    if not types:
        return
    rows = [
        {
            "duty_type_id": _uuid(t["id"]),
            "name": t["name"],
            "short_name": t.get("short_name"),
            "owner_unit_id": _uuid(t["owner_unit_id"]),
            "is_active": bool(t["is_active"]),
            "source_version": int(t.get("version", 0)),
        }
        for t in types
    ]
    stmt = insert(DutyTypeProjection).values(rows)
    ex = stmt.excluded
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[DutyTypeProjection.duty_type_id],
            set_={
                "name": ex.name,
                "short_name": ex.short_name,
                "owner_unit_id": ex.owner_unit_id,
                "is_active": ex.is_active,
                "source_version": ex.source_version,
            },
            where=DutyTypeProjection.source_version <= ex.source_version,
        )
    )


async def upsert_duty_roles(session: AsyncSession, roles: Sequence[dict[str, Any]]) -> None:
    if not roles:
        return
    rows = [
        {
            "duty_role_id": _uuid(r["id"]),
            "duty_type_id": _uuid(r["duty_type_id"]),
            "code": r["code"],
            "name": r["name"],
            "sort_order": int(r.get("sort_order", 0)),
            "min_rank_order": r.get("min_rank_order"),
            "allowed_position_ids": (
                [_uuid(p) for p in r["allowed_position_ids"]]
                if r.get("allowed_position_ids") is not None
                else None
            ),
            "attribute_requirements": r.get("attribute_requirements") or [],
            "is_active": bool(r["is_active"]),
            "source_version": int(r.get("version", 0)),
        }
        for r in roles
    ]
    stmt = insert(DutyRoleProjection).values(rows)
    ex = stmt.excluded
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[DutyRoleProjection.duty_role_id],
            set_={
                "duty_type_id": ex.duty_type_id,
                "code": ex.code,
                "name": ex.name,
                "sort_order": ex.sort_order,
                "min_rank_order": ex.min_rank_order,
                "allowed_position_ids": ex.allowed_position_ids,
                "attribute_requirements": ex.attribute_requirements,
                "is_active": ex.is_active,
                "source_version": ex.source_version,
            },
            where=DutyRoleProjection.source_version <= ex.source_version,
        )
    )


async def handle_duty_event(session: AsyncSession, event: Event) -> None:
    if event.type == "duty_type.changed":
        await upsert_duty_types(session, [event.payload])
    elif event.type == "duty_role.changed":
        await upsert_duty_roles(session, [event.payload])


async def resync_scheduling(
    sessionmaker: async_sessionmaker[AsyncSession],
    scheduling: InternalClient,
    *,
    only_if_empty: bool,
) -> bool:
    """Загружает все роли с типами из scheduling. True — синхронизация была."""
    async with sessionmaker() as session:
        if only_if_empty and await session.scalar(
            select(func.count()).select_from(DutyRoleProjection)
        ):
            return False
    roles = await scheduling.post("/internal/duty-roles/batch", {"include_inactive": True})
    types = {r["duty_type"]["id"]: r["duty_type"] for r in roles}
    async with sessionmaker() as session, session.begin():
        await upsert_duty_types(session, list(types.values()))
        for i in range(0, len(roles), 1000):
            await upsert_duty_roles(session, roles[i : i + 1000])
    log.info("Роли нарядов синхронизированы: %d типов, %d ролей", len(types), len(roles))
    return True
