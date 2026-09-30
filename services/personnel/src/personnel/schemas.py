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


class PersonCategoryIn(BaseModel):
    code: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=200)
    sort_order: int = Field(default=0, ge=0, le=10_000)
    is_active: bool = True


class PersonCategoryOut(PersonCategoryIn):
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
    # Категория обязательна: от неё зависит, в какие роли человек может заступать (ADR-0018)
    category_id: uuid.UUID
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
    # Сбросить категорию нельзя — только сменить
    category_id: uuid.UUID | None = None
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
    category_id: uuid.UUID | None
    category_name: str | None
    personal_no: str | None
    is_active: bool
    # Действующее сегодня освобождение: до какого числа (включительно) и причина
    exempt_until: dt.date | None = None
    exempt_reason: str | None = None
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
    category_id: uuid.UUID | None = None
    # Только освобождённые сегодня
    exempt_today: bool = False
    include_archived: bool = False


class UnitCount(BaseModel):
    unit_id: uuid.UUID
    # Действующие люди, числящиеся прямо в подразделении (без нижестоящих)
    people: int


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
    """Выборка — либо по подразделениям (действующие люди), либо по конкретным людям
    (включая исключённых из списков: scheduling проверяет свои назначения)."""

    unit_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10_000)
    include_descendants: bool = True
    person_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50_000)
    date_from: dt.date
    date_to: dt.date
    # ФИО и звание — для списков кандидатов; для снимка движка не нужны
    include_names: bool = False
    # Только люди с действующим в периоде допуском к одной из ролей (кандидаты в ячейку):
    # без допуска человек в ячейку не встаёт, а поддерево бывает в десятки тысяч (фаза 7d)
    duty_role_ids: list[uuid.UUID] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def _one_selector(self) -> "PeopleBatchIn":
        if bool(self.unit_ids) == bool(self.person_ids):
            raise ValueError("Укажите либо подразделения, либо людей")
        return self


class PeopleBatchPerson(BaseModel):
    id: uuid.UUID
    unit_id: uuid.UUID
    is_active: bool
    rank_id: uuid.UUID | None
    rank_order: int | None
    position_id: uuid.UUID | None
    category_id: uuid.UUID | None = None
    attributes: dict[str, Any]
    # Освобождения, пересекающие период, как пары [from, to] включительно
    exemptions: list[tuple[dt.date, dt.date]]
    # Неотозванные допуски, действующие хотя бы в часть периода: [роль, с, по] (NULL — без границы).
    # Требования ролей здесь не проверяются: допуск важнее требований (ADR-0009). Исключение —
    # категория: допуски к ролям, не допускающим категорию человека, сюда не попадают (ADR-0018).
    clearances: list[tuple[uuid.UUID, dt.date | None, dt.date | None]]
    # Только при include_names
    last_name: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    rank_name: str | None = None


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


# --- допуски (ADR-0009) -----------------------------------------------------------------------

# category_mismatch — категория человека больше не допускается ролью: допуск не действует
ClearanceStatus = Literal[
    "active", "future", "expired", "revoked", "role_inactive", "category_mismatch"
]


class ClearanceDates(BaseModel):
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None

    @model_validator(mode="after")
    def _dates(self) -> "ClearanceDates":
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("Дата окончания допуска раньше даты начала")
        return self


class OverrideIn(BaseModel):
    """Подтверждение выдачи вопреки требованиям роли: без комментария не принимается."""

    confirm_override: bool = False
    override_comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _comment(self) -> "OverrideIn":
        if self.confirm_override and not (self.override_comment or "").strip():
            raise ValueError("Укажите, почему допуск выдаётся вопреки требованиям роли")
        return self


class ClearanceIn(ClearanceDates, OverrideIn):
    duty_role_id: uuid.UUID


class ClearanceUpdate(ClearanceDates):
    version: int


class RevokeIn(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class BulkClearanceIn(ClearanceDates, OverrideIn):
    person_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)
    duty_role_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


class ViolationOut(BaseModel):
    kind: Literal["category", "rank", "position", "attribute"]
    code: str | None
    message: str
    # Жёсткое нарушение (категория) допуском-исключением не перекрывается (ADR-0018)
    hard: bool = False


class RoleRef(BaseModel):
    """Роль наряда с названием типа и подразделения-владельца — для списков и отчётов."""

    duty_role_id: uuid.UUID
    role_name: str
    duty_type_id: uuid.UUID | None
    duty_type_name: str
    owner_unit_id: uuid.UUID | None
    owner_unit_name: str | None
    # Подразделение, за которым закреплена роль (ADR-0018)
    assigned_unit_id: uuid.UUID | None = None
    assigned_unit_name: str | None = None


class ClearanceOut(RoleRef):
    id: uuid.UUID
    person_id: uuid.UUID
    valid_from: dt.date | None
    valid_to: dt.date | None
    status: ClearanceStatus
    overrides_requirements: bool
    override_comment: str | None
    granted_by_name: str
    granted_at: dt.datetime
    revoked_at: dt.datetime | None
    # Нарушения текущих требований роли (пусто — соответствует); отчёт о несоответствиях
    violations: list[ViolationOut]
    version: int


class ClearanceOption(RoleRef):
    """Роль, к которой человеку можно выдать допуск, и его соответствие требованиям.
    С жёстким нарушением (категория) выдать нельзя."""

    sort_order: int
    has_requirements: bool
    violations: list[ViolationOut]
    granted: bool


class ClearanceRoleOut(RoleRef):
    sort_order: int
    has_requirements: bool


class BulkClearanceResult(BaseModel):
    done: int
    # Не выдано: {person_id, name, duty_role_id, role_name, reason, violations?}
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    # Сколько пропущено только из-за несоответствия требованиям — их можно выдать с подтверждением
    needs_override: int = 0


class MismatchItem(RoleRef):
    clearance_id: uuid.UUID
    person_id: uuid.UUID
    person_name: str
    unit_id: uuid.UUID
    unit_name: str | None
    overrides_requirements: bool
    override_comment: str | None
    valid_to: dt.date | None
    violations: list[ViolationOut]


class ReferencesOut(BaseModel):
    """Внутренний API для scheduling: справочники, на которые ссылаются требования ролей."""

    positions: list[dict[str, Any]]
    attributes: list[dict[str, Any]]
    categories: list[dict[str, Any]] = Field(default_factory=list)


# --- пакетный импорт (фаза 6a, open-questions №54–55) ------------------------------------------

ImportKind = Literal["people", "clearances", "exemptions"]
ImportAction = Literal["create", "update", "unchanged", "error"]
MAX_IMPORT_ROWS = 20_000


class ImportRowIn(BaseModel):
    """Строка файла: номер строки в файле и значения по ключам столбцов шаблона. Значения —
    как в файле (строка, число, дата ISO); ссылки — названиями из шаблона."""

    row: int = Field(ge=1)
    values: dict[str, Any]


class ImportIn(BaseModel):
    rows: list[ImportRowIn] = Field(min_length=1, max_length=MAX_IMPORT_ROWS)
    # true — только проверить (предпросмотр); false — применить
    dry_run: bool = True
    # Применить только корректные строки (№54); иначе при ошибках ничего не применяется
    skip_invalid: bool = False
    # Хэш предпросмотра: при применении данные должны остаться такими же
    expected_hash: str | None = None


class ImportIssue(BaseModel):
    column: str | None = None
    message: str


class ImportRowOut(BaseModel):
    row: int
    action: ImportAction
    label: str | None = None  # о ком строка: «Иванов Иван Иванович»
    errors: list[ImportIssue] = Field(default_factory=list)
    warnings: list[ImportIssue] = Field(default_factory=list)
    # Для изменения — «было → стало» по полям, в человекочитаемом виде
    changes: dict[str, list[Any]] = Field(default_factory=dict)


class ImportOut(BaseModel):
    kind: ImportKind
    applied: bool
    summary: dict[ImportAction, int]
    rows: list[ImportRowOut]
    state_hash: str


class TemplateColumn(BaseModel):
    key: str
    title: str
    required: bool = False
    type: Literal["text", "date", "int", "bool", "list"] = "text"
    options: list[str] | None = None
    hint: str | None = None


class ImportTemplateOut(BaseModel):
    kind: ImportKind
    title: str
    columns: list[TemplateColumn]
    instructions: list[str]
