"""Модели БД сервиса personnel (`docs/data-model.md` §4).

Люди — данные, а не пользователи: учётных записей у них нет, их ведут операторы.
Состав карточки минимален (open-questions №29): ФИО, звание, должность, подразделение,
личный номер, характеристики, примечание.
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from dutyflow_common.audit import AuditLog
from dutyflow_common.db import Base, TimestampMixin, UuidPkMixin, VersionedMixin
from dutyflow_common.outbox import OutboxEvent, ProcessedEvent
from dutyflow_common.projections import RankProjection, UnitProjection

__all__ = [
    "AttributeDefinition",
    "AuditLog",
    "Exemption",
    "ExemptionReason",
    "OutboxEvent",
    "Person",
    "PersonAttribute",
    "Position",
    "ProcessedEvent",
    "RankProjection",
    "UnitProjection",
]

VALUE_TYPES = ("bool", "int", "enum", "date", "string")


class Position(UuidPkMixin, TimestampMixin, Base):
    """Должность — отдельный справочник: участвует в требованиях ролей и лимитах (ADR-0005)."""

    __tablename__ = "position"

    name: Mapped[str] = mapped_column(String(200), unique=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Person(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "person"
    __table_args__ = (
        Index("ix_person_unit_active", "unit_id", postgresql_where=text("is_active")),
        Index("ix_person_sort", "last_name", "first_name", "middle_name", "id"),
    )

    unit_id: Mapped[uuid.UUID]
    last_name: Mapped[str] = mapped_column(String(100))
    first_name: Mapped[str] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100))
    rank_id: Mapped[uuid.UUID | None]
    position_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("position.id"))
    personal_no: Mapped[str | None] = mapped_column(String(50), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    archived_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)

    def snapshot(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "last_name": self.last_name,
            "first_name": self.first_name,
            "middle_name": self.middle_name,
            "rank_id": self.rank_id,
            "position_id": self.position_id,
            "personal_no": self.personal_no,
            "is_active": self.is_active,
            "note": self.note,
        }


# Поиск по ФИО подстрокой: триграммный GIN-индекс по склеенному ФИО. Запрос поиска обязан
# использовать то же выражение (`person_fio`), иначе индекс не применится. `||` и `lower`
# — IMMUTABLE, поэтому выражение индексируемо (в отличие от concat_ws).
person_fio = func.lower(
    Person.last_name + " " + Person.first_name + " " + func.coalesce(Person.middle_name, "")
)
# Alembic не умеет сравнивать индексы по выражению и считает их расхождением —
# такие индексы исключаются из autogenerate (migrations/env.py, тест миграций).
EXPRESSION_INDEXES = frozenset({"ix_person_fio_trgm"})


def include_object(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    return not (type_ == "index" and name in EXPRESSION_INDEXES)


Index(
    "ix_person_fio_trgm",
    person_fio.label("fio"),
    postgresql_using="gin",
    postgresql_ops={"fio": "gin_trgm_ops"},
)


class AttributeDefinition(UuidPkMixin, TimestampMixin, Base):
    """Типизированное определение расширяемой характеристики (ADR-0005)."""

    __tablename__ = "attribute_definition"
    __table_args__ = (
        CheckConstraint(
            "value_type IN ('bool', 'int', 'enum', 'date', 'string')", name="value_type"
        ),
    )

    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    value_type: Mapped[str] = mapped_column(String(10))
    enum_options: Mapped[list[str] | None] = mapped_column(JSONB)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PersonAttribute(Base):
    __tablename__ = "person_attribute"
    __table_args__ = (Index("ix_person_attribute_value", "value", postgresql_using="gin"),)

    person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), primary_key=True
    )
    definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attribute_definition.id"), primary_key=True
    )
    # Значение обёрнуто: {"v": ...} — тип задаёт AttributeDefinition.value_type.
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ExemptionReason(UuidPkMixin, TimestampMixin, Base):
    """Справочник причин освобождения (open-questions №30)."""

    __tablename__ = "exemption_reason"

    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Exemption(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    """Период, когда человек недоступен. Даты включительно (open-questions №25)."""

    __tablename__ = "exemption"
    __table_args__ = (
        CheckConstraint("date_to >= date_from", name="dates"),
        # Пересечение периодов одного человека запрещено на уровне БД, даже при гонке двух
        # операторов. btree_gist нужен для «person_id WITH =» внутри GiST.
        ExcludeConstraint(
            (Column("person_id"), "="),
            (func.daterange(Column("date_from"), Column("date_to"), "[]"), "&&"),
            name="ex_exemption_no_overlap",
            using="gist",
        ),
    )

    person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), index=True
    )
    reason_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exemption_reason.id"))
    date_from: Mapped[dt.date] = mapped_column(Date)
    date_to: Mapped[dt.date] = mapped_column(Date)
    comment: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(100))

    def snapshot(self) -> dict[str, Any]:
        return {
            "person_id": self.person_id,
            "reason_id": self.reason_id,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "comment": self.comment,
        }
