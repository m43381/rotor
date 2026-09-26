"""Схемы API сервиса org."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UnitPermissions(BaseModel):
    """Что оператор может делать с узлом. Считается сервером, чтобы UI не дублировал политику."""

    update: bool
    move: bool
    delete: bool
    create_child: bool


class UnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_id: uuid.UUID | None
    unit_type_id: uuid.UUID
    name: str
    short_name: str | None
    path: str
    depth: int
    sort_order: int
    is_active: bool
    version: int
    permissions: UnitPermissions | None = None


class UnitCreate(BaseModel):
    parent_id: uuid.UUID
    unit_type_id: uuid.UUID
    name: str = Field(min_length=1, max_length=300)
    short_name: str | None = Field(default=None, max_length=100)
    sort_order: int = 0


class UnitUpdate(BaseModel):
    version: int
    name: str | None = Field(default=None, min_length=1, max_length=300)
    short_name: str | None = Field(default=None, max_length=100)
    unit_type_id: uuid.UUID | None = None
    sort_order: int | None = None


class UnitMove(BaseModel):
    version: int
    new_parent_id: uuid.UUID


class UnitTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    level: int
    can_have_children: bool


class UnitTypeIn(BaseModel):
    code: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=200)
    level: int = Field(ge=0, le=50)
    can_have_children: bool = True


class RankOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    short_name: str | None
    order: int
    is_active: bool


class RankIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    short_name: str | None = Field(default=None, max_length=50)
    order: int = Field(ge=0, le=10_000)
    is_active: bool = True


class CalendarDayModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: dt.date
    kind: Literal["holiday", "workday", "preholiday"]
    name: str | None = None


class MeOut(BaseModel):
    subject: str
    username: str
    full_name: str
    roles: list[str]
    unit: UnitOut


class UnitsBatchIn(BaseModel):
    """Пустой список — все подразделения (для пересинхронизации проекций, ADR-0011)."""

    unit_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10_000)
    include_inactive: bool = True


class UnitBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_id: uuid.UUID | None
    unit_type_id: uuid.UUID
    name: str
    short_name: str | None
    path: str
    is_active: bool


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
