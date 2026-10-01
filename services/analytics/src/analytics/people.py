"""Люди и категории личного состава для разрезов аналитики (фаза 8, ADR-0020).

Владелец данных — personnel. Копия держится событиями `person.*` (категория, звание,
подразделение; защита версией карточки) и `person_category.changed`; пустая копия
заполняется выгрузкой `POST /internal/people/batch` и `POST /internal/references`.
"""

import datetime as dt
import logging
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analytics.models import CategoryDim, PersonDim
from dutyflow_common.events import Event
from dutyflow_common.internal import InternalClient
from dutyflow_common.projections import UnitProjection

log = logging.getLogger(__name__)
CHUNK = 1_000


def _uuid(value: Any) -> uuid.UUID | None:
    return None if value is None else uuid.UUID(str(value))


async def upsert_people(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    for i in range(0, len(rows), CHUNK):
        stmt = insert(PersonDim).values(list(rows[i : i + CHUNK]))
        ex = stmt.excluded
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[PersonDim.person_id],
                set_={
                    "unit_id": ex.unit_id,
                    "category_id": ex.category_id,
                    "rank_id": ex.rank_id,
                    "is_active": ex.is_active,
                    "source_version": ex.source_version,
                },
                where=PersonDim.source_version <= ex.source_version,
            )
        )


async def upsert_categories(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    stmt = insert(CategoryDim).values(list(rows))
    ex = stmt.excluded
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[CategoryDim.category_id],
            set_={"name": ex.name, "sort_order": ex.sort_order, "is_active": ex.is_active},
        )
    )


async def handle_person_event(session: AsyncSession, event: Event) -> None:
    p = event.payload
    if "person_id" not in p or "unit_id" not in p:
        return
    await upsert_people(
        session,
        [
            {
                "person_id": uuid.UUID(str(p["person_id"])),
                "unit_id": uuid.UUID(str(p["unit_id"])),
                "category_id": _uuid(p.get("category_id")),
                "rank_id": _uuid(p.get("rank_id")),
                "is_active": bool(p.get("is_active", True)),
                "source_version": int(p.get("version", 0)),
            }
        ],
    )


async def handle_category_event(session: AsyncSession, event: Event) -> None:
    if event.type == "person_category.deleted":
        # Удаляется только категория, которой нет ни у кого из людей (ADR-0023)
        await session.execute(
            delete(CategoryDim).where(CategoryDim.category_id == event.aggregate_id)
        )
        return
    if event.type != "person_category.changed":
        return
    p = event.payload
    await upsert_categories(
        session,
        [
            {
                "category_id": event.aggregate_id,
                "name": str(p["name"]),
                "sort_order": int(p.get("sort_order", 0)),
                "is_active": bool(p.get("is_active", True)),
            }
        ],
    )


async def resync_people(
    sessionmaker: async_sessionmaker[AsyncSession],
    personnel: InternalClient,
    *,
    only_if_empty: bool,
) -> bool:
    """Выгрузка действующих людей и категорий из personnel. True — синхронизация была."""
    async with sessionmaker() as session:
        if only_if_empty and await session.scalar(select(func.count()).select_from(PersonDim)):
            return False
        roots = [
            str(u)
            for u in await session.scalars(
                select(UnitProjection.unit_id).where(UnitProjection.parent_id.is_(None))
            )
        ]
    refs = await personnel.post("/internal/references", {})
    categories = [
        {"category_id": uuid.UUID(c["id"]), "name": c["name"], "sort_order": i,
         "is_active": bool(c["is_active"])}
        for i, c in enumerate(refs.get("categories", []))
    ]  # fmt: skip
    people: list[dict[str, Any]] = []
    if roots:
        today = dt.date.today().isoformat()
        people = await personnel.post(
            "/internal/people/batch",
            {"unit_ids": roots, "include_descendants": True, "date_from": today, "date_to": today},
        )
    rows = [
        {
            "person_id": uuid.UUID(p["id"]),
            "unit_id": uuid.UUID(p["unit_id"]),
            "category_id": _uuid(p.get("category_id")),
            "rank_id": _uuid(p.get("rank_id")),
            "is_active": bool(p["is_active"]),
            "source_version": 0,
        }
        for p in people
    ]
    async with sessionmaker() as session, session.begin():
        await upsert_categories(session, categories)
        await upsert_people(session, rows)
    log.info("Люди для аналитики синхронизированы: %d, категорий %d", len(rows), len(categories))
    return True
