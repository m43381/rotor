"""Схемы API сервиса scheduling."""

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dutyflow_common.requirements import AttributeRequirement
from scheduling.models import DEFAULT_REST_HOURS, MAX_DURATION, MIN_DURATION

# --- роли -------------------------------------------------------------------------------------


class DutyRoleIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # Код роли нужен для импорта и печати; если не задан, сервис назначит его сам.
    code: str | None = Field(
        default=None, min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$"
    )
    headcount: int = Field(default=1, ge=1, le=100)
    sort_order: int = Field(default=0, ge=0, le=1000)
    min_rank_order: int | None = Field(default=None, ge=0, le=32767)
    # None — любая должность; пустой список не допускается (роль стала бы недостижимой)
    allowed_position_ids: list[uuid.UUID] | None = None
    attribute_requirements: list[AttributeRequirement] = Field(default_factory=list, max_length=20)
    is_active: bool = True

    @model_validator(mode="after")
    def _check(self) -> "DutyRoleIn":
        if self.allowed_position_ids is not None:
            if not self.allowed_position_ids:
                raise ValueError("Укажите хотя бы одну должность или снимите ограничение")
            self.allowed_position_ids = list(dict.fromkeys(self.allowed_position_ids))
        codes = [r.code for r in self.attribute_requirements]
        if len(set(codes)) != len(codes):
            raise ValueError("Для каждой характеристики допускается одно требование")
        return self


class DutyRoleUpdate(DutyRoleIn):
    version: int


class DutyRoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    duty_type_id: uuid.UUID
    code: str
    name: str
    headcount: int
    sort_order: int
    min_rank_order: int | None
    allowed_position_ids: list[uuid.UUID] | None
    attribute_requirements: list[AttributeRequirement]
    is_active: bool
    version: int


# --- типы нарядов --------------------------------------------------------------------------------


class DutyTypeBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    short_name: str | None = Field(default=None, max_length=50)
    assigned_unit_id: uuid.UUID | None = None
    start_time: dt.time
    duration_minutes: int = Field(ge=MIN_DURATION, le=MAX_DURATION)
    rest_hours: int = Field(default=DEFAULT_REST_HOURS, ge=0, le=720)
    load_weight: float = Field(default=1.0, gt=0, le=99)

    @model_validator(mode="after")
    def _clean(self) -> "DutyTypeBase":
        self.start_time = self.start_time.replace(second=0, microsecond=0, tzinfo=None)
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Название обязательно")
        return self


class DutyTypeCreate(DutyTypeBase):
    owner_unit_id: uuid.UUID
    roles: list[DutyRoleIn] = Field(min_length=1, max_length=20)


class DutyTypeUpdate(DutyTypeBase):
    """Владелец наряда не меняется: наряд другого подразделения — это другой наряд."""

    version: int
    is_active: bool = True


class DutyTypeOut(BaseModel):
    id: uuid.UUID
    name: str
    short_name: str | None
    owner_unit_id: uuid.UUID
    owner_unit_name: str | None
    assigned_unit_id: uuid.UUID | None
    assigned_unit_name: str | None
    start_time: dt.time
    duration_minutes: int
    rest_hours: int
    load_weight: float
    is_active: bool
    version: int
    roles: list[DutyRoleOut]
    # Может ли текущий оператор менять наряд — чтобы UI не дублировал политику доступа
    can_edit: bool


# --- внутренний API ----------------------------------------------------------------------------


class DutyRolesBatchIn(BaseModel):
    # Пустой список — все роли (полная пересинхронизация проекции в personnel)
    role_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10_000)
    include_inactive: bool = True


class DutyTypeBrief(BaseModel):
    id: uuid.UUID
    name: str
    short_name: str | None
    owner_unit_id: uuid.UUID
    is_active: bool
    version: int


class DutyRoleBatchItem(BaseModel):
    id: uuid.UUID
    duty_type_id: uuid.UUID
    code: str
    name: str
    headcount: int
    sort_order: int
    min_rank_order: int | None
    allowed_position_ids: list[uuid.UUID] | None
    attribute_requirements: list[dict[str, Any]]
    is_active: bool
    version: int
    duty_type: DutyTypeBrief


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


# --- графики и ячейки (фаза 3a) ------------------------------------------------------------------

CellState = Literal[
    "own",  # своя роль, закрывает само подразделение
    "delegated_pending",  # своя роль передана дочернему, ещё не принята
    "delegated_accepted",  # своя роль передана дочернему и принята
    "incoming_pending",  # пришла сверху, ждёт принятия
    "incoming_active",  # пришла сверху и принята, закрывает само подразделение
    "incoming_delegated_pending",  # пришла сверху и передана дальше, ниже не принята
    "incoming_delegated_accepted",  # пришла сверху и передана дальше, ниже принята
    "inactive",  # роль или наряд выведены из действия
]
ScheduleStatus = Literal["draft", "published", "archived"]


class ScheduleCreate(BaseModel):
    unit_id: uuid.UUID
    month: dt.date  # любой день месяца; хранится первое число


class ScheduleOut(BaseModel):
    id: uuid.UUID
    unit_id: uuid.UUID
    unit_name: str | None
    month: dt.date
    status: ScheduleStatus
    published_at: dt.datetime | None
    published_by: str | None
    version: int
    can_edit: bool
    # Входящие ячейки, ожидающие принятия этим подразделением
    pending_incoming: int


class CellOut(BaseModel):
    id: uuid.UUID
    state: CellState
    executor_unit_id: uuid.UUID
    is_pinned: bool


class TableDay(BaseModel):
    date: dt.date
    kind: Literal["workday", "weekend", "holiday", "preholiday"]
    name: str | None


class TableRow(BaseModel):
    duty_type_id: uuid.UUID
    duty_type_name: str
    duty_type_short_name: str | None
    owner_unit_id: uuid.UUID
    owner_unit_name: str | None
    start_time: dt.time
    duration_minutes: int
    duty_role_id: uuid.UUID
    role_name: str
    headcount: int
    is_active: bool
    # По дням месяца, в порядке `days`; null — ячейки в этот день нет
    cells: list[CellOut | None]


class UnitRef(BaseModel):
    id: uuid.UUID
    name: str
    short_name: str | None


class TableOut(BaseModel):
    schedule: ScheduleOut
    days: list[TableDay]
    rows: list[TableRow]
    # Кому можно делегировать: прямые действующие дочерние подразделения
    children: list[UnitRef]
    # Имена исполнителей, встречающихся в ячейках
    units: dict[uuid.UUID, UnitRef]


class CellsIn(BaseModel):
    cell_ids: list[uuid.UUID] = Field(min_length=1, max_length=10_000)


class DelegateIn(CellsIn):
    # Само подразделение графика — вернуть себе; прямое дочернее — делегировать
    executor_unit_id: uuid.UUID


class AcceptIn(BaseModel):
    # None — принять все входящие ячейки графика
    cell_ids: list[uuid.UUID] | None = Field(default=None, max_length=10_000)


class PinIn(CellsIn):
    pinned: bool


class ChangedOut(BaseModel):
    changed: int


class VersionIn(BaseModel):
    version: int


class PendingWarning(BaseModel):
    unit_id: uuid.UUID
    unit_name: str | None
    count: int


class PublishOut(BaseModel):
    schedule: ScheduleOut
    # Непринятые ячейки в поддереве — публикацию не блокируют (ADR-0009)
    warnings: list[PendingWarning]
