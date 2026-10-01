"""Локальные read-only проекции справочников `org` (ADR-0011).

`unit_projection` нужна для scope-фильтрации по поддереву одним JOIN в своей БД,
`rank_projection` — для отображения званий и проверки минимального звания.
Владелец данных — `org`; сюда они попадают событиями и полной пересинхронизацией.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    SmallInteger,
    String,
    case,
    cast,
    delete,
    func,
    literal,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from dutyflow_common.db import Base
from dutyflow_common.errors import ForbiddenError
from dutyflow_common.events import Event
from dutyflow_common.ltree import Ltree, is_descendant_or_self


class UnitProjection(Base):
    __tablename__ = "unit_projection"
    __table_args__ = (Index("ix_unit_projection_path_gist", "path", postgresql_using="gist"),)

    unit_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    parent_id: Mapped[uuid.UUID | None]
    path: Mapped[str] = mapped_column(Ltree())
    name: Mapped[str] = mapped_column(String(300))
    short_name: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean)
    # Версия узла в org: событие со старой версией не перетирает более свежие данные.
    source_version: Mapped[int] = mapped_column(Integer, default=0)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RankProjection(Base):
    __tablename__ = "rank_projection"

    rank_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    short_name: Mapped[str | None] = mapped_column(String(50))
    order: Mapped[int] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean)


# --- units ------------------------------------------------------------------------------------


async def upsert_units(session: AsyncSession, units: Sequence[dict[str, Any]]) -> None:
    """Вставка или обновление узлов (из события или batch-ответа org).

    Условие `source_version <= EXCLUDED.source_version` защищает от устаревших данных.
    """
    if not units:
        return
    rows = [
        {
            "unit_id": uuid.UUID(str(u.get("unit_id") or u["id"])),
            "parent_id": uuid.UUID(str(u["parent_id"])) if u.get("parent_id") else None,
            "path": u["path"],
            "name": u["name"],
            "short_name": u.get("short_name"),
            "is_active": bool(u.get("is_active", True)),
            "source_version": int(u.get("version", 0)),
        }
        for u in units
    ]
    stmt = insert(UnitProjection).values(rows)
    excluded = stmt.excluded
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[UnitProjection.unit_id],
            set_={
                "parent_id": excluded.parent_id,
                "path": excluded.path,
                "name": excluded.name,
                "short_name": excluded.short_name,
                "is_active": excluded.is_active,
                "source_version": excluded.source_version,
                "synced_at": func.now(),
            },
            where=UnitProjection.source_version <= excluded.source_version,
        )
    )


async def move_unit_subtree(session: AsyncSession, old_path: str, new_path: str) -> None:
    """Повторяет в проекции перенос поддерева из org: пути потомков переписываются одним UPDATE."""
    old_ltree = cast(literal(old_path), Ltree())
    new_ltree = cast(literal(new_path), Ltree())
    await session.execute(
        update(UnitProjection)
        .where(is_descendant_or_self(UnitProjection.path, old_path))
        .values(
            path=case(
                (UnitProjection.path == old_ltree, new_ltree),
                else_=new_ltree.op("||", return_type=Ltree())(
                    func.subpath(UnitProjection.path, func.nlevel(old_ltree))
                ),
            )
        )
        .execution_options(synchronize_session=False)
    )


async def handle_unit_event(session: AsyncSession, event: Event) -> None:
    payload = event.payload
    if event.type == "unit.purged":
        # org удаляет только подразделение без людей, нарядов и дочерних (ADR-0023)
        await session.execute(
            delete(UnitProjection).where(UnitProjection.unit_id == event.aggregate_id)
        )
        return
    if event.type == "unit.moved":
        await move_unit_subtree(session, payload["old_path"], payload["new_path"])
    if event.type.startswith("unit."):
        await upsert_units(session, [payload])


async def unit_path(session: AsyncSession, unit_id: uuid.UUID) -> str:
    """Путь подразделения оператора для scope. Нет в проекции — доступа нет."""
    path = await session.scalar(
        select(UnitProjection.path).where(
            UnitProjection.unit_id == unit_id, UnitProjection.is_active
        )
    )
    if path is None:
        raise ForbiddenError(
            "Подразделение оператора не найдено. Если его только что создали, повторите "
            "через несколько секунд."
        )
    return path


# --- ranks ------------------------------------------------------------------------------------


async def upsert_ranks(session: AsyncSession, ranks: Sequence[dict[str, Any]]) -> None:
    if not ranks:
        return
    rows = [
        {
            "rank_id": uuid.UUID(str(r.get("rank_id") or r["id"])),
            "name": r["name"],
            "short_name": r.get("short_name"),
            "order": int(r["order"]),
            "is_active": bool(r.get("is_active", True)),
        }
        for r in ranks
    ]
    stmt = insert(RankProjection).values(rows)
    excluded = stmt.excluded
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[RankProjection.rank_id],
            set_={
                "name": excluded.name,
                "short_name": excluded.short_name,
                "order": excluded.order,
                "is_active": excluded.is_active,
            },
        )
    )


async def handle_rank_event(session: AsyncSession, event: Event) -> None:
    if event.type == "rank.changed":
        await upsert_ranks(session, [{**event.payload, "rank_id": event.aggregate_id}])
    elif event.type == "rank.deleted":
        # org удаляет только неиспользуемое звание (ADR-0022), ссылок на копию нет
        await session.execute(
            delete(RankProjection).where(RankProjection.rank_id == event.aggregate_id)
        )
