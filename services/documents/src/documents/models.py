"""Служебные данные documents: задачи импорта. Предметных данных сервис не хранит — они у
сервисов-владельцев (`docs/architecture.md` §3.6)."""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from dutyflow_common.audit import AuditLog
from dutyflow_common.db import Base
from dutyflow_common.outbox import OutboxEvent

__all__ = ["AuditLog", "DocumentSettings", "ImportJob", "OutboxEvent", "PrintTemplate"]

IMPORT_STATUSES = ("preview", "applied", "discarded")


class ImportJob(Base):
    """Загруженный файл, разобранные строки и результат проверки владельцем данных."""

    __tablename__ = "import_job"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in IMPORT_STATUSES) + ")",
            name="status",
        ),
        CheckConstraint("kind IN ('people', 'clearances', 'exemptions')", name="kind"),
        Index("ix_import_job_owner", "created_by", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(300))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    # Столбцы шаблона на момент загрузки: ключ, заголовок, обязательность
    columns: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    # Строки файла: [{"row": 2, "values": {...}}]
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    # Результат проверки по строкам и сводка — ответ personnel
    report: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    summary: Mapped[dict[str, int]] = mapped_column(JSONB)
    state_hash: Mapped[str] = mapped_column(String(64))
    # Предупреждения разбора файла (лишние столбцы и т. п.)
    notes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    applied_rows: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[str] = mapped_column(String(100))
    created_by_name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    applied_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentSettings(Base):
    """Реквизиты печатных форм подразделения (open-questions №52). Нет записи — действуют
    реквизиты ближайшего вышестоящего подразделения."""

    __tablename__ = "document_settings"

    unit_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    approver_position: Mapped[str | None] = mapped_column(String(300))
    approver_rank: Mapped[str | None] = mapped_column(String(100))
    approver_name: Mapped[str | None] = mapped_column(String(200))
    compiler_position: Mapped[str | None] = mapped_column(String(300))
    compiler_rank: Mapped[str | None] = mapped_column(String(100))
    compiler_name: Mapped[str | None] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by_name: Mapped[str] = mapped_column(String(200))
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012

    FIELDS = (
        "approver_position",
        "approver_rank",
        "approver_name",
        "compiler_position",
        "compiler_rank",
        "compiler_name",
    )

    def snapshot(self) -> dict[str, Any]:
        return {f: getattr(self, f) for f in self.FIELDS}


class PrintTemplate(Base):
    """Загруженный суперадминистратором HTML-шаблон PDF-формы (open-questions №51). Версии
    не удаляются: действует последняя активная, «вернуть встроенный» снимает активность."""

    __tablename__ = "print_template"
    __table_args__ = (Index("ix_print_template_form", "form", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    form: Mapped[str] = mapped_column(String(50))
    body: Mapped[str] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
