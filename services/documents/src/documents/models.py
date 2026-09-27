"""Служебные данные documents: задачи импорта. Предметных данных сервис не хранит — они у
сервисов-владельцев (`docs/architecture.md` §3.6)."""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from dutyflow_common.db import Base

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
