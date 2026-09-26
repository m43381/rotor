"""Модели БД сервиса org (`docs/data-model.md` §3)."""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Sequence,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from dutyflow_common.audit import AuditLog
from dutyflow_common.db import Base, TimestampMixin, UuidPkMixin, VersionedMixin
from dutyflow_common.ltree import Ltree
from dutyflow_common.outbox import OutboxEvent, ProcessedEvent

__all__ = [
    "AuditLog",
    "CalendarDay",
    "InstallationSetting",
    "OutboxEvent",
    "ProcessedEvent",
    "Rank",
    "Unit",
    "UnitType",
]

# Номер узла — метка в ltree-пути. Не меняется при переименовании (ADR-0011).
unit_node_no_seq = Sequence("unit_node_no_seq", start=1)


class UnitType(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "unit_type"

    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    level: Mapped[int] = mapped_column(SmallInteger)
    can_have_children: Mapped[bool] = mapped_column(Boolean, default=True)


class Unit(UuidPkMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "unit"
    __table_args__ = (
        Index("ix_unit_path_gist", "path", postgresql_using="gist"),
        Index(
            "uq_unit_parent_name_active",
            "parent_id",
            "name",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    node_no: Mapped[int] = mapped_column(
        BigInteger, unit_node_no_seq, server_default=unit_node_no_seq.next_value(), unique=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("unit.id"), index=True)
    unit_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unit_type.id"))
    name: Mapped[str] = mapped_column(String(300))
    short_name: Mapped[str | None] = mapped_column(String(100))
    path: Mapped[str] = mapped_column(Ltree())
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def snapshot(self) -> dict[str, Any]:
        """Поля для аудита и событий."""
        return {
            "name": self.name,
            "short_name": self.short_name,
            "parent_id": self.parent_id,
            "unit_type_id": self.unit_type_id,
            "path": self.path,
            "sort_order": self.sort_order,
            "is_active": self.is_active,
        }


class Rank(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "rank"

    name: Mapped[str] = mapped_column(String(100))
    short_name: Mapped[str | None] = mapped_column(String(50))
    # Чем больше, тем старше звание. Уникален: справочник упорядоченный.
    order: Mapped[int] = mapped_column(SmallInteger, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class CalendarDay(Base):
    """Исключения производственного календаря. Обычные выходные вычисляются по дню недели."""

    __tablename__ = "calendar_day"
    __table_args__ = (CheckConstraint("kind IN ('holiday', 'workday', 'preholiday')", name="kind"),)

    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str | None] = mapped_column(String(200))


class InstallationSetting(Base):
    __tablename__ = "installation_setting"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
