"""Справочники personnel: должности, категории, характеристики, причины освобождений.

Читают все операторы, меняет суперадминистратор. Удаления нет — только `is_active=false`:
на записи ссылаются люди и история.
"""

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from dutyflow_common import audit
from dutyflow_common.context import Operator
from dutyflow_common.errors import ConflictError, NotFoundError, ValidationFailedError
from dutyflow_common.ids import uuid7
from dutyflow_common.outbox import add_event
from dutyflow_common.policy import default_policy
from personnel.api.deps import OperatorDep, SessionDep
from personnel.models import AttributeDefinition, ExemptionReason, PersonCategory, Position
from personnel.schemas import (
    AttributeDefinitionIn,
    AttributeDefinitionOut,
    ExemptionReasonIn,
    ExemptionReasonOut,
    PersonCategoryIn,
    PersonCategoryOut,
    PositionIn,
    PositionOut,
)

router = APIRouter(tags=["references"])


async def _list(session: SessionDep, operator: Operator, resource: str, stmt: Any) -> list[Any]:
    default_policy.require(operator.roles, resource, "read")
    return list((await session.scalars(stmt)).all())


async def _create(
    session: SessionDep, operator: Operator, resource: str, model: Any, data: BaseModel, dup: str
) -> Any:
    default_policy.require(operator.roles, resource, "create")
    values = data.model_dump()
    item = model(id=uuid7(), **values)
    session.add(item)
    audit.record(
        session,
        action=f"{resource}.create",
        entity_type=resource,
        entity_id=item.id,
        scope_unit_id=None,
        after=values,
    )
    add_event(session, f"{resource}.changed", resource, item.id, values)
    await _commit(session, dup)
    return item


async def _update(
    session: SessionDep,
    operator: Operator,
    resource: str,
    model: Any,
    item_id: uuid.UUID,
    data: BaseModel,
    dup: str,
) -> Any:
    default_policy.require(operator.roles, resource, "update")
    item = await session.get(model, item_id)
    if item is None:
        raise NotFoundError("Запись справочника не найдена")
    values = data.model_dump()
    before = {k: getattr(item, k) for k in values}
    if resource == "attribute_definition" and before["value_type"] != values["value_type"]:
        raise ValidationFailedError(
            "Тип характеристики менять нельзя: уже сохранённые значения станут некорректными"
        )
    for key, value in values.items():
        setattr(item, key, value)
    if audit.record(
        session,
        action=f"{resource}.update",
        entity_type=resource,
        entity_id=item.id,
        scope_unit_id=None,
        before=before,
        after=values,
    ):
        add_event(session, f"{resource}.changed", resource, item.id, values)
    await _commit(session, dup)
    return item


async def _commit(session: SessionDep, message: str) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(message) from exc


# --- должности ------------------------------------------------------------------------------

_POSITION_DUP = "Такая должность уже есть"


@router.get("/positions", response_model=list[PositionOut])
async def list_positions(session: SessionDep, operator: OperatorDep) -> list[Any]:
    return await _list(
        session, operator, "position", select(Position).order_by(Position.sort_order, Position.name)
    )


@router.post("/positions", response_model=PositionOut, status_code=201)
async def create_position(data: PositionIn, session: SessionDep, operator: OperatorDep) -> Any:
    return await _create(session, operator, "position", Position, data, _POSITION_DUP)


@router.put("/positions/{item_id}", response_model=PositionOut)
async def update_position(
    item_id: uuid.UUID, data: PositionIn, session: SessionDep, operator: OperatorDep
) -> Any:
    return await _update(session, operator, "position", Position, item_id, data, _POSITION_DUP)


# --- категории личного состава (ADR-0018) ------------------------------------------------------

_CATEGORY = "person_category"
_CATEGORY_DUP = "Категория с таким кодом или названием уже есть"


@router.get("/person-categories", response_model=list[PersonCategoryOut])
async def list_person_categories(session: SessionDep, operator: OperatorDep) -> list[Any]:
    stmt = select(PersonCategory).order_by(PersonCategory.sort_order, PersonCategory.name)
    return await _list(session, operator, _CATEGORY, stmt)


@router.post("/person-categories", response_model=PersonCategoryOut, status_code=201)
async def create_person_category(
    data: PersonCategoryIn, session: SessionDep, operator: OperatorDep
) -> Any:
    return await _create(session, operator, _CATEGORY, PersonCategory, data, _CATEGORY_DUP)


@router.put("/person-categories/{item_id}", response_model=PersonCategoryOut)
async def update_person_category(
    item_id: uuid.UUID, data: PersonCategoryIn, session: SessionDep, operator: OperatorDep
) -> Any:
    return await _update(session, operator, _CATEGORY, PersonCategory, item_id, data, _CATEGORY_DUP)


# --- характеристики --------------------------------------------------------------------------

_ATTR = "attribute_definition"
_ATTR_DUP = "Характеристика с таким кодом уже есть"


@router.get("/attribute-definitions", response_model=list[AttributeDefinitionOut])
async def list_attribute_definitions(session: SessionDep, operator: OperatorDep) -> list[Any]:
    stmt = select(AttributeDefinition).order_by(
        AttributeDefinition.sort_order, AttributeDefinition.name
    )
    return await _list(session, operator, _ATTR, stmt)


@router.post("/attribute-definitions", response_model=AttributeDefinitionOut, status_code=201)
async def create_attribute_definition(
    data: AttributeDefinitionIn, session: SessionDep, operator: OperatorDep
) -> Any:
    return await _create(session, operator, _ATTR, AttributeDefinition, data, _ATTR_DUP)


@router.put("/attribute-definitions/{item_id}", response_model=AttributeDefinitionOut)
async def update_attribute_definition(
    item_id: uuid.UUID, data: AttributeDefinitionIn, session: SessionDep, operator: OperatorDep
) -> Any:
    return await _update(session, operator, _ATTR, AttributeDefinition, item_id, data, _ATTR_DUP)


# --- причины освобождений --------------------------------------------------------------------

_REASON = "exemption_reason"
_REASON_DUP = "Причина с таким кодом уже есть"


@router.get("/exemption-reasons", response_model=list[ExemptionReasonOut])
async def list_exemption_reasons(session: SessionDep, operator: OperatorDep) -> list[Any]:
    return await _list(
        session, operator, _REASON, select(ExemptionReason).order_by(ExemptionReason.name)
    )


@router.post("/exemption-reasons", response_model=ExemptionReasonOut, status_code=201)
async def create_exemption_reason(
    data: ExemptionReasonIn, session: SessionDep, operator: OperatorDep
) -> Any:
    return await _create(session, operator, _REASON, ExemptionReason, data, _REASON_DUP)


@router.put("/exemption-reasons/{item_id}", response_model=ExemptionReasonOut)
async def update_exemption_reason(
    item_id: uuid.UUID, data: ExemptionReasonIn, session: SessionDep, operator: OperatorDep
) -> Any:
    return await _update(session, operator, _REASON, ExemptionReason, item_id, data, _REASON_DUP)
