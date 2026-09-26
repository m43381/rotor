"""Схемы API сервиса personnel."""

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ValueType = Literal["bool", "int", "enum", "date", "string"]


# --- справочники -----------------------------------------------------------------------------


class PositionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sort_order: int = Field(default=0, ge=0, le=10_000)
    is_active: bool = True


class PositionOut(PositionIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class AttributeDefinitionIn(BaseModel):
    code: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=200)
    value_type: ValueType
    enum_options: list[str] | None = None
    is_required: bool = False
    sort_order: int = Field(default=0, ge=0, le=10_000)
    is_active: bool = True

    @model_validator(mode="after")
    def _enum_options(self) -> "AttributeDefinitionIn":
        if self.value_type == "enum":
            options = [o.strip() for o in self.enum_options or [] if o.strip()]
            if not options:
                raise ValueError("Для перечисления нужен хотя бы один вариант")
            if len(set(options)) != len(options):
                raise ValueError("Варианты перечисления не должны повторяться")
            self.enum_options = options
        else:
            self.enum_options = None
        return self


class AttributeDefinitionOut(AttributeDefinitionIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class ExemptionReasonIn(BaseModel):
    code: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=200)
    is_active: bool = True


class ExemptionReasonOut(ExemptionReasonIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


# --- люди -----------------------------------------------------------------------------------


class PersonBase(BaseModel):
    last_name: str = Field(min_length=1, max_length=100)
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    rank_id: uuid.UUID | None = None
    position_id: uuid.UUID | None = None
    personal_no: str | None = Field(default=None, max_length=50)
    note: str | None = Field(default=None, max_length=2000)


class PersonCreate(PersonBase):
    unit_id: uuid.UUID
    # Значения характеристик по коду: {"category": "Курсант"}
    attributes: dict[str, Any] = Field(default_factory=dict)


class PersonUpdate(BaseModel):
    """Частичное изменение. Подразделение меняется отдельной операцией перевода."""

    version: int
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    rank_id: uuid.UUID | None = None
    position_id: uuid.UUID | None = None
    personal_no: str | None = Field(default=None, max_length=50)
    note: str | None = Field(default=None, max_length=2000)
    # Передаются только изменяемые характеристики; значение null удаляет характеристику.
    attributes: dict[str, Any] | None = None


class PersonListItem(BaseModel):
    """Строка списка: без характеристик и освобождений, зато с именами справочников."""

    id: uuid.UUID
    last_name: str
    first_name: str
    middle_name: str | None
    unit_id: uuid.UUID
    unit_name: str | None
    rank_id: uuid.UUID | None
    rank_name: str | None
    position_id: uuid.UUID | None
    position_name: str | None
    personal_no: str | None
    is_active: bool
    version: int


class ExemptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    person_id: uuid.UUID
    reason_id: uuid.UUID
    date_from: dt.date
    date_to: dt.date
    comment: str | None
    version: int


class PersonOut(PersonListItem):
    note: str | None
    archived_at: dt.datetime | None
    attributes: dict[str, Any]
    exemptions: list[ExemptionOut]
    can_edit: bool


class PeopleFilter(BaseModel):
    unit_id: uuid.UUID | None = None
    subtree: bool = True
    q: str | None = None
    rank_id: uuid.UUID | None = None
    position_id: uuid.UUID | None = None
    include_archived: bool = False


class TransferIn(BaseModel):
    person_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)
    unit_id: uuid.UUID


class ArchiveIn(BaseModel):
    version: int
    comment: str | None = Field(default=None, max_length=2000)


# --- освобождения ---------------------------------------------------------------------------


class ExemptionIn(BaseModel):
    reason_id: uuid.UUID
    date_from: dt.date
    date_to: dt.date
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _dates(self) -> "ExemptionIn":
        if self.date_to < self.date_from:
            raise ValueError("Дата окончания раньше даты начала")
        return self


class ExemptionUpdate(ExemptionIn):
    version: int


class BulkExemptionIn(ExemptionIn):
    person_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)


class BulkResult(BaseModel):
    done: int
    skipped: list[dict[str, Any]] = Field(default_factory=list)


# --- внутренний API ---------------------------------------------------------------------------


class PeopleBatchIn(BaseModel):
    unit_ids: list[uuid.UUID] = Field(min_length=1, max_length=10_000)
    include_descendants: bool = True
    date_from: dt.date
    date_to: dt.date


class PeopleBatchPerson(BaseModel):
    id: uuid.UUID
    unit_id: uuid.UUID
    rank_id: uuid.UUID | None
    rank_order: int | None
    position_id: uuid.UUID | None
    attributes: dict[str, Any]
    # Освобождения, пересекающие период, как пары [from, to] включительно
    exemptions: list[tuple[dt.date, dt.date]]


class AvailabilityIn(BaseModel):
    person_ids: list[uuid.UUID] = Field(min_length=1, max_length=50_000)
    date_from: dt.date
    date_to: dt.date


class AvailabilityOut(BaseModel):
    date_from: dt.date
    days: int
    # Строка из '1' (доступен) и '0' (освобождён) по дням периода — компактно для 50 тыс. человек
    masks: dict[uuid.UUID, str]


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    occurred_at: dt.datetime
    actor_id: str
    actor_name: str
    action: str
    entity_type: str
    entity_id: uuid.UUID
    before: dict[str, object] | None
    after: dict[str, object] | None
    comment: str | None
