"""Внутренние batch-эндпоинты для scheduling/documents (`docs/architecture.md` §3.2).

Снимок личного состава собирается тремя запросами (люди, характеристики, освобождения)
независимо от числа людей — без N+1 (правило `CLAUDE.md` №4). Ответ сериализуется напрямую
в JSON (pydantic-core), минуя построение 50 тыс. pydantic-моделей.
"""

import datetime as dt
import uuid
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic_core import to_json
from sqlalchemy import or_, select

from dutyflow_common.auth import require_internal
from dutyflow_common.errors import ValidationFailedError
from dutyflow_common.ltree import is_descendant_or_self
from dutyflow_common.projections import RankProjection, UnitProjection
from personnel.api.deps import SessionDep
from personnel.models import AttributeDefinition, Exemption, Person, PersonAttribute
from personnel.schemas import AvailabilityIn, AvailabilityOut, PeopleBatchIn, PeopleBatchPerson

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_internal)])


def _json(content: Any) -> Response:
    return Response(content=to_json(content), media_type="application/json")


@router.post("/people/batch", response_model=list[PeopleBatchPerson])
async def people_batch(data: PeopleBatchIn, session: SessionDep) -> Response:
    if data.include_descendants:
        roots = (
            await session.scalars(
                select(UnitProjection.path).where(UnitProjection.unit_id.in_(data.unit_ids))
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
        people_q = select(Person.id).where(Person.is_active, Person.unit_id.in_(data.unit_ids))
    ids = people_q.subquery()

    people = await session.execute(
        select(Person.id, Person.unit_id, Person.rank_id, RankProjection.order, Person.position_id)
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

    return _json(
        [
            {
                "id": pid,
                "unit_id": unit_id,
                "rank_id": rank_id,
                "rank_order": rank_order,
                "position_id": position_id,
                "attributes": attrs.get(pid, {}),
                "exemptions": exemptions.get(pid, []),
            }
            for pid, unit_id, rank_id, rank_order, position_id in people
        ]
    )


@router.post("/people/availability-batch", response_model=AvailabilityOut)
async def availability_batch(data: AvailabilityIn, session: SessionDep) -> Response:
    """Доступность по дням: строка '1'/'0' на каждого человека. Архивные — все '0'."""
    days = (data.date_to - data.date_from).days + 1
    if days <= 0 or days > 366:
        raise ValidationFailedError("Период должен быть от 1 до 366 дней")
    masks: dict[uuid.UUID, bytearray] = {}
    active = await session.execute(
        select(Person.id, Person.is_active).where(Person.id.in_(data.person_ids))
    )
    for pid, is_active in active:
        masks[pid] = bytearray(b"1" * days if is_active else b"0" * days)
    for pid, date_from, date_to in await session.execute(
        select(Exemption.person_id, Exemption.date_from, Exemption.date_to).where(
            Exemption.person_id.in_(data.person_ids),
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
