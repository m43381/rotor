"""Внутренние batch-эндпоинты для scheduling/documents (`docs/architecture.md` §3.2).

Снимок личного состава собирается четырьмя запросами (люди, характеристики, освобождения,
допуски)
независимо от числа людей — без N+1 (правило `CLAUDE.md` №4). Ответ сериализуется напрямую
в JSON (pydantic-core), минуя построение 50 тыс. pydantic-моделей.
"""

import datetime as dt
import uuid
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic_core import to_json
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import aggregate_order_by

from dutyflow_common.auth import require_internal
from dutyflow_common.db import in_array
from dutyflow_common.errors import ValidationFailedError
from dutyflow_common.ltree import is_descendant_or_self
from dutyflow_common.projections import RankProjection, UnitProjection
from personnel.api.deps import SessionDep
from personnel.models import (
    AttributeDefinition,
    Clearance,
    Exemption,
    Person,
    PersonAttribute,
    Position,
)
from personnel.schemas import (
    AvailabilityIn,
    AvailabilityOut,
    PeopleBatchIn,
    PeopleBatchPerson,
    ReferencesOut,
)

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_internal)])


def _json(content: Any) -> Response:
    return Response(content=to_json(content), media_type="application/json")


@router.post("/people/batch", response_model=list[PeopleBatchPerson])
async def people_batch(data: PeopleBatchIn, session: SessionDep) -> Response:
    if data.person_ids:
        people_q = select(Person.id).where(in_array(Person.id, data.person_ids))
    elif data.include_descendants:
        roots = (
            await session.scalars(
                select(UnitProjection.path).where(in_array(UnitProjection.unit_id, data.unit_ids))
            )
        ).all()
        if not roots:
            return _json([])
        people_q = (
            select(Person.id)
            .join(UnitProjection, UnitProjection.unit_id == Person.unit_id)
            .where(
                Person.is_active,
                or_(*(is_descendant_or_self(UnitProjection.path, p) for p in roots)),
            )
        )
    else:
        people_q = select(Person.id).where(
            Person.is_active, in_array(Person.unit_id, data.unit_ids)
        )
    ids = people_q.subquery()

    people = await session.execute(
        select(
            Person.id,
            Person.unit_id,
            Person.is_active,
            Person.rank_id,
            RankProjection.order.label("rank_order"),
            Person.position_id,
            Person.last_name,
            Person.first_name,
            Person.middle_name,
            RankProjection.name.label("rank_name"),
        )
        .join(ids, ids.c.id == Person.id)
        .outerjoin(RankProjection, RankProjection.rank_id == Person.rank_id)
        .order_by(Person.id)
    )
    attrs: dict[uuid.UUID, dict[str, Any]] = defaultdict(dict)
    for person_id, code, value in await session.execute(
        select(PersonAttribute.person_id, AttributeDefinition.code, PersonAttribute.value)
        .join(ids, ids.c.id == PersonAttribute.person_id)
        .join(AttributeDefinition, AttributeDefinition.id == PersonAttribute.definition_id)
    ):
        attrs[person_id][code] = value["v"]
    exemptions: dict[uuid.UUID, list[tuple[dt.date, dt.date]]] = defaultdict(list)
    for person_id, date_from, date_to in await session.execute(
        select(Exemption.person_id, Exemption.date_from, Exemption.date_to)
        .join(ids, ids.c.id == Exemption.person_id)
        .where(Exemption.date_to >= data.date_from, Exemption.date_from <= data.date_to)
        .order_by(Exemption.date_from)
    ):
        exemptions[person_id].append((date_from, date_to))
    # Допусков в ~5 раз больше, чем людей: агрегируем в БД — одна строка на человека,
    # массивы декодирует asyncpg, а не цикл по строкам в Python.
    clearances: dict[uuid.UUID, list[tuple[uuid.UUID, dt.date | None, dt.date | None]]] = {}
    for person_id, roles, froms, tos in await session.execute(
        select(
            Clearance.person_id,
            func.array_agg(aggregate_order_by(Clearance.duty_role_id, Clearance.duty_role_id)),
            func.array_agg(aggregate_order_by(Clearance.valid_from, Clearance.duty_role_id)),
            func.array_agg(aggregate_order_by(Clearance.valid_to, Clearance.duty_role_id)),
        )
        .join(ids, ids.c.id == Clearance.person_id)
        .where(
            Clearance.revoked_at.is_(None),
            or_(Clearance.valid_from.is_(None), Clearance.valid_from <= data.date_to),
            or_(Clearance.valid_to.is_(None), Clearance.valid_to >= data.date_from),
        )
        .group_by(Clearance.person_id)
    ):
        clearances[person_id] = list(zip(roles, froms, tos, strict=True))

    result = []
    for p in people:
        pid = p.id
        item: dict[str, Any] = {
            "id": pid,
            "unit_id": p.unit_id,
            "is_active": p.is_active,
            "rank_id": p.rank_id,
            "rank_order": p.rank_order,
            "position_id": p.position_id,
            "attributes": attrs.get(pid, {}),
            "exemptions": exemptions.get(pid, []),
            "clearances": clearances.get(pid, []),
        }
        if data.include_names:
            item |= {
                "last_name": p.last_name,
                "first_name": p.first_name,
                "middle_name": p.middle_name,
                "rank_name": p.rank_name,
            }
        result.append(item)
    return _json(result)


@router.post("/people/availability-batch", response_model=AvailabilityOut)
async def availability_batch(data: AvailabilityIn, session: SessionDep) -> Response:
    """Доступность по дням: строка '1'/'0' на каждого человека. Архивные — все '0'."""
    days = (data.date_to - data.date_from).days + 1
    if days <= 0 or days > 366:
        raise ValidationFailedError("Период должен быть от 1 до 366 дней")
    masks: dict[uuid.UUID, bytearray] = {}
    active = await session.execute(
        select(Person.id, Person.is_active).where(in_array(Person.id, data.person_ids))
    )
    for pid, is_active in active:
        masks[pid] = bytearray(b"1" * days if is_active else b"0" * days)
    for pid, date_from, date_to in await session.execute(
        select(Exemption.person_id, Exemption.date_from, Exemption.date_to).where(
            in_array(Exemption.person_id, data.person_ids),
            Exemption.date_to >= data.date_from,
            Exemption.date_from <= data.date_to,
        )
    ):
        start = max((date_from - data.date_from).days, 0)
        end = min((date_to - data.date_from).days, days - 1)
        masks[pid][start : end + 1] = b"0" * (end - start + 1)
    return _json(
        {
            "date_from": data.date_from,
            "days": days,
            "masks": {k: v.decode() for k, v in masks.items()},
        }
    )


@router.post("/references", response_model=ReferencesOut)
async def references(session: SessionDep) -> ReferencesOut:
    """Должности и характеристики — для проверки ссылок в требованиях ролей (scheduling)."""
    positions = await session.execute(select(Position.id, Position.name, Position.is_active))
    attributes = await session.scalars(select(AttributeDefinition))
    return ReferencesOut(
        positions=[{"id": i, "name": n, "is_active": a} for i, n, a in positions],
        attributes=[
            {
                "code": a.code,
                "name": a.name,
                "value_type": a.value_type,
                "enum_options": a.enum_options,
                "is_active": a.is_active,
            }
            for a in attributes
        ],
    )
