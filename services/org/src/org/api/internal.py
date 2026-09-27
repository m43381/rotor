"""Внутренние batch-эндпоинты для других сервисов (`docs/architecture.md` §3.1).

Не проксируются gateway наружу и требуют `X-Internal-Token`. Отдают срез дерева одним
запросом — замена рекурсивного обхода из legacy.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select

from dutyflow_common.auth import require_internal
from dutyflow_common.ltree import is_descendant_or_self
from org.api.deps import SessionDep
from org.models import CalendarDay, Rank, Unit
from org.schemas import CalendarDayModel, RankOut, UnitBrief, UnitsBatchIn

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_internal)])


@router.post("/units/batch", response_model=list[UnitBrief])
async def units_batch(data: UnitsBatchIn, session: SessionDep) -> list[Unit]:
    stmt = select(Unit).order_by(func.nlevel(Unit.path), Unit.sort_order)
    if data.unit_ids:
        stmt = stmt.where(Unit.id.in_(data.unit_ids))
    if not data.include_inactive:
        stmt = stmt.where(Unit.is_active)
    return list((await session.scalars(stmt)).all())


@router.post("/units/descendants-batch", response_model=list[UnitBrief])
async def descendants_batch(data: UnitsBatchIn, session: SessionDep) -> list[Unit]:
    """Все узлы поддеревьев переданных подразделений (включая сами узлы), одним запросом:
    `path <@ p1 OR path <@ p2 …` — каждое условие использует GiST-индекс."""
    roots = (await session.scalars(select(Unit.path).where(Unit.id.in_(data.unit_ids)))).all()
    if not roots:
        return []
    stmt = (
        select(Unit)
        .where(or_(*(is_descendant_or_self(Unit.path, p) for p in roots)))
        .order_by(func.nlevel(Unit.path), Unit.sort_order)
    )
    if not data.include_inactive:
        stmt = stmt.where(Unit.is_active)
    return list((await session.scalars(stmt)).all())


@router.post("/ranks", response_model=list[RankOut])
async def ranks(session: SessionDep) -> list[Rank]:
    """Все звания, включая неактивные: у людей может остаться снятое с учёта звание."""
    return list((await session.scalars(select(Rank).order_by(Rank.order))).all())


@router.post("/calendar", response_model=list[CalendarDayModel])
async def calendar(session: SessionDep) -> list[CalendarDay]:
    """Все исключения производственного календаря — для пересинхронизации проекций."""
    return list((await session.scalars(select(CalendarDay).order_by(CalendarDay.date))).all())
