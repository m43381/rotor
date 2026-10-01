"""Справочники: типы подразделений, звания, производственный календарь.

Читают все операторы, меняет только суперадминистратор (правила в libs/common/policy).
"""

import datetime as dt
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from dutyflow_common import audit
from dutyflow_common.errors import ConflictError, NotFoundError
from dutyflow_common.ids import uuid7
from dutyflow_common.outbox import add_event
from dutyflow_common.policy import default_policy
from dutyflow_common.usage import ensure_unused
from org.api.deps import OperatorDep, SessionDep
from org.models import CalendarDay, Rank, Unit, UnitType
from org.schemas import CalendarDayModel, RankIn, RankOut, UnitTypeIn, UnitTypeOut

router = APIRouter(tags=["references"])


def _row(obj: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {f: getattr(obj, f) for f in fields}


async def _commit_unique(session: SessionDep, message: str) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(message) from exc


# --- типы подразделений ----------------------------------------------------------------

_TYPE_FIELDS = ("code", "name", "level", "can_have_children")


@router.get("/unit-types", response_model=list[UnitTypeOut])
async def list_unit_types(session: SessionDep, operator: OperatorDep) -> list[UnitType]:
    default_policy.require(operator.roles, "unit_type", "read")
    return list((await session.scalars(select(UnitType).order_by(UnitType.level))).all())


@router.post("/unit-types", response_model=UnitTypeOut, status_code=201)
async def create_unit_type(
    data: UnitTypeIn, session: SessionDep, operator: OperatorDep
) -> UnitType:
    default_policy.require(operator.roles, "unit_type", "create")
    item = UnitType(id=uuid7(), **data.model_dump())
    session.add(item)
    audit.record(
        session,
        action="unit_type.create",
        entity_type="unit_type",
        entity_id=item.id,
        scope_unit_id=None,
        after=_row(item, _TYPE_FIELDS),
    )
    add_event(session, "unit_type.changed", "unit_type", item.id, data.model_dump())
    await _commit_unique(session, "Тип с таким кодом уже существует")
    return item


@router.put("/unit-types/{type_id}", response_model=UnitTypeOut)
async def update_unit_type(
    type_id: uuid.UUID, data: UnitTypeIn, session: SessionDep, operator: OperatorDep
) -> UnitType:
    default_policy.require(operator.roles, "unit_type", "update")
    item = await session.get(UnitType, type_id)
    if item is None:
        raise NotFoundError("Тип подразделения не найден")
    before = _row(item, _TYPE_FIELDS)
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    if audit.record(
        session,
        action="unit_type.update",
        entity_type="unit_type",
        entity_id=item.id,
        scope_unit_id=None,
        before=before,
        after=_row(item, _TYPE_FIELDS),
    ):
        add_event(session, "unit_type.changed", "unit_type", item.id, data.model_dump())
    await _commit_unique(session, "Тип с таким кодом уже существует")
    return item


@router.delete(
    "/unit-types/{type_id}",
    status_code=204,
    summary="Удалить тип подразделения, если подразделений этого типа нет (ADR-0023)",
)
async def delete_unit_type(
    type_id: uuid.UUID, session: SessionDep, operator: OperatorDep
) -> Response:
    default_policy.require(operator.roles, "unit_type", "delete")
    item = await session.get(UnitType, type_id)
    if item is None:
        raise NotFoundError("Тип подразделения не найден")
    # Расформированные подразделения тоже ссылаются на тип
    units = await session.scalar(
        select(func.count()).select_from(Unit).where(Unit.unit_type_id == item.id)
    )
    ensure_unused(f"Тип «{item.name}»", {"units": units or 0}, "")
    audit.record(
        session,
        action="unit_type.delete",
        entity_type="unit_type",
        entity_id=item.id,
        scope_unit_id=None,
        before=_row(item, _TYPE_FIELDS),
    )
    add_event(session, "unit_type.deleted", "unit_type", item.id, {"code": item.code})
    await session.delete(item)
    await session.commit()
    return Response(status_code=204)


# --- звания -------------------------------------------------------------------------------

_RANK_FIELDS = ("name", "short_name", "order", "is_active")


@router.get("/ranks", response_model=list[RankOut])
async def list_ranks(session: SessionDep, operator: OperatorDep) -> list[Rank]:
    default_policy.require(operator.roles, "rank", "read")
    return list((await session.scalars(select(Rank).order_by(Rank.order))).all())


@router.post("/ranks", response_model=RankOut, status_code=201)
async def create_rank(data: RankIn, session: SessionDep, operator: OperatorDep) -> Rank:
    default_policy.require(operator.roles, "rank", "create")
    item = Rank(id=uuid7(), **data.model_dump())
    session.add(item)
    audit.record(
        session,
        action="rank.create",
        entity_type="rank",
        entity_id=item.id,
        scope_unit_id=None,
        after=_row(item, _RANK_FIELDS),
    )
    add_event(session, "rank.changed", "rank", item.id, data.model_dump())
    await _commit_unique(session, "Звание с таким порядковым номером уже есть")
    return item


@router.put("/ranks/{rank_id}", response_model=RankOut)
async def update_rank(
    rank_id: uuid.UUID, data: RankIn, session: SessionDep, operator: OperatorDep
) -> Rank:
    default_policy.require(operator.roles, "rank", "update")
    item = await session.get(Rank, rank_id)
    if item is None:
        raise NotFoundError("Звание не найдено")
    before = _row(item, _RANK_FIELDS)
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    if audit.record(
        session,
        action="rank.update",
        entity_type="rank",
        entity_id=item.id,
        scope_unit_id=None,
        before=before,
        after=_row(item, _RANK_FIELDS),
    ):
        add_event(session, "rank.changed", "rank", item.id, data.model_dump())
    await _commit_unique(session, "Звание с таким порядковым номером уже есть")
    return item


@router.delete(
    "/ranks/{rank_id}",
    status_code=204,
    summary="Удалить звание, если оно нигде не используется (ADR-0022)",
)
async def delete_rank(
    rank_id: uuid.UUID, request: Request, session: SessionDep, operator: OperatorDep
) -> Response:
    default_policy.require(operator.roles, "rank", "delete")
    item = await session.get(Rank, rank_id)
    if item is None:
        raise NotFoundError("Звание не найдено")
    # Без ответа personnel или scheduling удалять нельзя: ServiceUnavailableError → 503
    usage = await request.app.state.usage("rank", {"id": str(item.id), "order": item.order})
    ensure_unused(f"Звание «{item.name}»", usage, "Его можно только выключить.")
    audit.record(
        session,
        action="rank.delete",
        entity_type="rank",
        entity_id=item.id,
        scope_unit_id=None,
        before=_row(item, _RANK_FIELDS),
    )
    add_event(session, "rank.deleted", "rank", item.id, {"order": item.order})
    await session.delete(item)
    await session.commit()
    return Response(status_code=204)


# --- производственный календарь --------------------------------------------------------------

_CALENDAR_ENTITY = uuid.UUID(int=0)  # у календаря нет своего id, аудит пишется на «календарь»


@router.get("/calendar", response_model=list[CalendarDayModel])
async def list_calendar(
    session: SessionDep,
    operator: OperatorDep,
    date_from: Annotated[dt.date, Query()],
    date_to: Annotated[dt.date, Query()],
) -> list[CalendarDay]:
    default_policy.require(operator.roles, "calendar", "read")
    stmt = (
        select(CalendarDay)
        .where(CalendarDay.date >= date_from, CalendarDay.date <= date_to)
        .order_by(CalendarDay.date)
    )
    return list((await session.scalars(stmt)).all())


@router.put("/calendar/{day}", response_model=CalendarDayModel)
async def upsert_calendar_day(
    day: dt.date, data: CalendarDayModel, session: SessionDep, operator: OperatorDep
) -> CalendarDay:
    default_policy.require(operator.roles, "calendar", "update")
    item = await session.get(CalendarDay, day)
    before = None if item is None else {"kind": item.kind, "name": item.name}
    if item is None:
        item = CalendarDay(date=day, kind=data.kind, name=data.name)
        session.add(item)
    else:
        item.kind, item.name = data.kind, data.name
    audit.record(
        session,
        action="calendar.upsert",
        entity_type="calendar",
        entity_id=_CALENDAR_ENTITY,
        scope_unit_id=None,
        before=before,
        after={"date": day, "kind": data.kind, "name": data.name},
    )
    add_event(
        session,
        "calendar.changed",
        "calendar",
        _CALENDAR_ENTITY,
        {"date": day, "kind": data.kind, "name": data.name},
    )
    await session.commit()
    return item


@router.delete("/calendar/{day}", status_code=204)
async def delete_calendar_day(day: dt.date, session: SessionDep, operator: OperatorDep) -> None:
    default_policy.require(operator.roles, "calendar", "delete")
    item = await session.get(CalendarDay, day)
    if item is None:
        raise NotFoundError("Такого дня в календаре нет")
    audit.record(
        session,
        action="calendar.delete",
        entity_type="calendar",
        entity_id=_CALENDAR_ENTITY,
        scope_unit_id=None,
        before={"date": day, "kind": item.kind, "name": item.name},
    )
    add_event(
        session, "calendar.changed", "calendar", _CALENDAR_ENTITY, {"date": day, "deleted": True}
    )
    await session.delete(item)
    await session.commit()
