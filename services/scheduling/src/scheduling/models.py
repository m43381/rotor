"""Модели БД сервиса scheduling (`docs/data-model.md` §5).

Типы нарядов с шаблоном времени (ADR-0008) и роли с требованиями (ADR-0009); графики
подразделений на месяц и ячейки «дата × роль» с делегированием вниз по дереву.
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import DATERANGE, JSONB, ExcludeConstraint, Range
from sqlalchemy.orm import Mapped, mapped_column

from dutyflow_common.audit import AuditLog
from dutyflow_common.calendar import CalendarProjection
from dutyflow_common.db import Base, TimestampMixin, UuidPkMixin, VersionedMixin
from dutyflow_common.outbox import OutboxEvent, ProcessedEvent
from dutyflow_common.projections import RankProjection, UnitProjection

__all__ = [
    "Assignment",
    "AuditLog",
    "Base",
    "CalendarProjection",
    "DayPlan",
    "DutyLimit",
    "DutyRole",
    "DutyType",
    "OutboxEvent",
    "ProcessedEvent",
    "RankProjection",
    "Schedule",
    "UnitProjection",
]

MIN_DURATION = 60
MAX_DURATION = 7 * 24 * 60
DEFAULT_REST_HOURS = 48  # open-questions №8


class DutyType(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    """Тип наряда. Интервал экземпляра: [дата + start_time, + duration) (ADR-0008)."""

    __tablename__ = "duty_type"
    __table_args__ = (
        CheckConstraint(
            f"duration_minutes BETWEEN {MIN_DURATION} AND {MAX_DURATION}", name="duration"
        ),
        CheckConstraint("rest_hours BETWEEN 0 AND 720", name="rest_hours"),
        CheckConstraint("load_weight > 0", name="load_weight"),
        # Два действующих наряда с одним именем у одного подразделения путали бы операторов.
        Index(
            "uq_duty_type_owner_name_active",
            "owner_unit_id",
            "name",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    name: Mapped[str] = mapped_column(String(200))
    short_name: Mapped[str | None] = mapped_column(String(50))
    owner_unit_id: Mapped[uuid.UUID] = mapped_column(index=True)
    assigned_unit_id: Mapped[uuid.UUID | None]
    start_time: Mapped[dt.time] = mapped_column(Time)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    rest_hours: Mapped[int] = mapped_column(SmallInteger, default=DEFAULT_REST_HOURS)
    load_weight: Mapped[float] = mapped_column(Numeric(4, 2, asdecimal=False), default=1.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "short_name": self.short_name,
            "owner_unit_id": self.owner_unit_id,
            "assigned_unit_id": self.assigned_unit_id,
            "start_time": self.start_time,
            "duration_minutes": self.duration_minutes,
            "rest_hours": self.rest_hours,
            "load_weight": self.load_weight,
            "is_active": self.is_active,
        }


class DutyRole(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    """Роль внутри наряда: численность и требования к человеку (ADR-0009).

    Требования используются только при выдаче допуска и в отчёте о несоответствиях —
    движок распределения их не видит, он смотрит на допуск.
    """

    __tablename__ = "duty_role"
    __table_args__ = (
        UniqueConstraint("duty_type_id", "code"),
        CheckConstraint("headcount BETWEEN 1 AND 100", name="headcount"),
    )

    duty_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("duty_type.id"), index=True)
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200))
    headcount: Mapped[int] = mapped_column(SmallInteger, default=1)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)
    min_rank_order: Mapped[int | None] = mapped_column(SmallInteger)
    allowed_position_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(Uuid()))
    # [{"code": "category", "op": "in", "value": ["Курсант"]}] — dutyflow_common.requirements
    attribute_requirements: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def snapshot(self) -> dict[str, Any]:
        return {
            "duty_type_id": self.duty_type_id,
            "code": self.code,
            "name": self.name,
            "headcount": self.headcount,
            "sort_order": self.sort_order,
            "min_rank_order": self.min_rank_order,
            "allowed_position_ids": (
                sorted(map(str, self.allowed_position_ids))
                if self.allowed_position_ids is not None
                else None
            ),
            "attribute_requirements": self.attribute_requirements,
            "is_active": self.is_active,
        }


class Schedule(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    """График подразделения на месяц: draft → published → archived."""

    __tablename__ = "schedule"
    __table_args__ = (
        UniqueConstraint("unit_id", "month"),
        CheckConstraint("status IN ('draft', 'published', 'archived')", name="status"),
        CheckConstraint("extract(day FROM month) = 1", name="month_first_day"),
    )

    unit_id: Mapped[uuid.UUID]
    month: Mapped[dt.date] = mapped_column(Date)  # первое число месяца
    status: Mapped[str] = mapped_column(String(20), default="draft")
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[str | None] = mapped_column(String(200))


class DayPlan(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    """Ячейка «дата начала × роль наряда» в графике подразделения (ADR-0008, ADR-0009).

    `own` — роль наряда самого подразделения, `incoming` — пришла от родителя по делегированию
    (`parent_day_plan_id`). `executor_unit_id` — кто закрывает роль: само подразделение
    графика или его прямое дочернее; во втором случае у ячейки есть дочерняя ячейка в графике
    исполнителя. Смена решения удаляет цепочку вниз каскадом (как в legacy).
    """

    __tablename__ = "day_plan"
    __table_args__ = (
        UniqueConstraint("schedule_id", "date", "duty_role_id"),
        CheckConstraint("origin IN ('own', 'incoming')", name="origin"),
        CheckConstraint(
            "delegation_status IN ('none', 'pending', 'accepted')", name="delegation_status"
        ),
        CheckConstraint(
            "(origin = 'own') = (parent_day_plan_id IS NULL)", name="incoming_has_parent"
        ),
        # Непринятые входящие: счётчики в списке графиков и предупреждения при публикации
        Index(
            "ix_day_plan_pending",
            "schedule_id",
            postgresql_where=text("delegation_status = 'pending'"),
        ),
    )

    # Индекс по schedule_id не нужен: его покрывает UNIQUE(schedule_id, date, duty_role_id)
    schedule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schedule.id", ondelete="CASCADE"))
    date: Mapped[dt.date] = mapped_column(Date)
    duty_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("duty_type.id"))
    duty_role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("duty_role.id"), index=True)
    origin: Mapped[str] = mapped_column(String(10))
    parent_day_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("day_plan.id", ondelete="CASCADE"), unique=True
    )
    executor_unit_id: Mapped[uuid.UUID]
    delegation_status: Mapped[str] = mapped_column(String(10), default="none")
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)


class Assignment(UuidPkMixin, TimestampMixin, Base):
    """Человек в ячейке (фаза 3b). Интервал и занятые сутки денормализованы из шаблона
    времени наряда (ADR-0008): «не больше одного наряда в сутки» проверяет сама БД."""

    __tablename__ = "assignment"
    __table_args__ = (
        UniqueConstraint("day_plan_id", "person_id"),
        CheckConstraint("source IN ('manual', 'auto')", name="source"),
        CheckConstraint("end_at > start_at", name="interval"),
        CheckConstraint(
            "NOT (rest_override OR limit_override)"
            " OR length(btrim(coalesce(override_comment, ''))) > 0",
            name="override_comment",
        ),
        # Два наряда одного человека не делят ни одних суток — даже при гонке операторов
        ExcludeConstraint(
            (Column("person_id"), "="),
            (Column("occupied_days"), "&&"),
            name="ex_assignment_one_per_day",
            using="gist",
        ),
        Index("ix_assignment_person_start", "person_id", "start_at"),
    )

    # Индекс не нужен: его покрывает UNIQUE(day_plan_id, person_id)
    day_plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("day_plan.id", ondelete="CASCADE"))
    person_id: Mapped[uuid.UUID]
    # «Фамилия И. О.» на момент назначения — таблица месяца не ходит в personnel
    person_name: Mapped[str] = mapped_column(String(200))
    start_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    occupied_days: Mapped[Range[dt.date]] = mapped_column(DATERANGE)
    source: Mapped[str] = mapped_column(String(10), default="manual")
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    rest_override: Mapped[bool] = mapped_column(Boolean, default=False)
    limit_override: Mapped[bool] = mapped_column(Boolean, default=False)
    override_comment: Mapped[str | None] = mapped_column(Text)
    # Изменения у человека после назначения (open-questions №39): не снимаем, а помечаем
    conflict: Mapped[str | None] = mapped_column(Text)
    assigned_by: Mapped[str] = mapped_column(String(100))
    assigned_by_name: Mapped[str] = mapped_column(String(200))
    assigned_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    def snapshot(self) -> dict[str, Any]:
        return {
            "day_plan_id": self.day_plan_id,
            "person_id": self.person_id,
            "person_name": self.person_name,
            "start_at": self.start_at,
            "end_at": self.end_at,
            "rest_override": self.rest_override,
            "limit_override": self.limit_override,
            "override_comment": self.override_comment,
            "is_pinned": self.is_pinned,
        }


class DutyLimit(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    """Лимит нарядов на человека за календарный месяц (open-questions №9, 27).

    К человеку применяется самое специфичное правило: ближайшее по дереву подразделение,
    затем уточнение по званию и должности (`docs/data-model.md` §5).
    """

    __tablename__ = "duty_limit"
    __table_args__ = (
        CheckConstraint(
            "max_duties IS NOT NULL OR max_holiday_duties IS NOT NULL", name="has_limit"
        ),
    )

    unit_id: Mapped[uuid.UUID] = mapped_column(index=True)
    applies_to_subtree: Mapped[bool] = mapped_column(Boolean, default=True)
    rank_id: Mapped[uuid.UUID | None]
    position_id: Mapped[uuid.UUID | None]
    max_duties: Mapped[int | None] = mapped_column(SmallInteger)
    max_holiday_duties: Mapped[int | None] = mapped_column(SmallInteger)

    def snapshot(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "applies_to_subtree": self.applies_to_subtree,
            "rank_id": self.rank_id,
            "position_id": self.position_id,
            "max_duties": self.max_duties,
            "max_holiday_duties": self.max_holiday_duties,
        }


def include_object(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    return True
