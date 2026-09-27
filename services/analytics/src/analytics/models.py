"""Read-model analytics (фаза 6c): факт наряда на каждое назначение. Строится только по
событиям `scheduling` (ADR-0004); перестраивается с нуля выгрузкой фактов (`analytics.rebuild`).
Подразделения — общая проекция org (ADR-0011): по ней считается поддерево для scope и отчётов.
"""

import datetime as dt
import uuid

from sqlalchemy import Boolean, Date, DateTime, Float, Index, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from dutyflow_common.db import Base
from dutyflow_common.outbox import OutboxEvent, ProcessedEvent
from dutyflow_common.projections import RankProjection, UnitProjection

__all__ = ["DutyFact", "OutboxEvent", "ProcessedEvent", "RankProjection", "UnitProjection"]


class DutyFact(Base):
    __tablename__ = "duty_fact"
    __table_args__ = (
        Index("ix_duty_fact_unit_date", "unit_id", "date"),
        Index("ix_duty_fact_schedule", "schedule_id"),
        Index("ix_duty_fact_person_date", "person_id", "date"),
    )

    assignment_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    person_id: Mapped[uuid.UUID]
    person_name: Mapped[str] = mapped_column(String(200))
    # Подразделение, закрывшее ячейку своими людьми (подразделение графика)
    unit_id: Mapped[uuid.UUID]
    schedule_id: Mapped[uuid.UUID]
    schedule_status: Mapped[str] = mapped_column(String(10))
    duty_type_id: Mapped[uuid.UUID]
    duty_role_id: Mapped[uuid.UUID]
    date: Mapped[dt.date] = mapped_column(Date)
    start_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    occupied_days: Mapped[int] = mapped_column(SmallInteger)
    load: Mapped[float] = mapped_column(Float)
    holiday: Mapped[bool] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(10))
