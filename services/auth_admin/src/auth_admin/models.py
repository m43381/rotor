"""Своих пользователей auth-admin не хранит (ADR-0002): операторы живут в Keycloak. БД —
только журнал аудита и outbox для событий `audit.recorded` (ADR-0010)."""

from dutyflow_common.audit import AuditLog
from dutyflow_common.db import Base
from dutyflow_common.outbox import OutboxEvent, ProcessedEvent

__all__ = ["AuditLog", "Base", "OutboxEvent", "ProcessedEvent"]
