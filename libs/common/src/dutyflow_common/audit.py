"""Журнал аудита (ADR-0010): кто, что, когда, было → стало. Пишется в той же транзакции,
что и изменение, и дублируется событием `audit.recorded` для сводного журнала в analytics."""

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from dutyflow_common.context import current_operator, current_request_id
from dutyflow_common.db import Base
from dutyflow_common.errors import ValidationFailedError
from dutyflow_common.ids import uuid7
from dutyflow_common.outbox import add_event

SYSTEM_ACTOR = "system"


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_entity", "entity_type", "entity_id", "occurred_at"),
        Index("ix_audit_log_scope", "scope_unit_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    actor_id: Mapped[str] = mapped_column(String(100))
    actor_name: Mapped[str] = mapped_column(String(200))
    actor_unit_id: Mapped[uuid.UUID | None]
    request_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID]
    scope_unit_id: Mapped[uuid.UUID | None]
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    comment: Mapped[str | None] = mapped_column(Text)


def diff(
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Оставляет только изменившиеся поля. Для создания/удаления возвращает объект целиком."""
    b = jsonable_encoder(dict(before)) if before is not None else None
    a = jsonable_encoder(dict(after)) if after is not None else None
    if b is None or a is None:
        return b, a
    keys = sorted(set(b) | set(a))
    changed = [k for k in keys if b.get(k) != a.get(k)]
    return {k: b.get(k) for k in changed}, {k: a.get(k) for k in changed}


def record(
    session: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    scope_unit_id: uuid.UUID | None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    comment: str | None = None,
    require_comment: bool = False,
) -> AuditLog | None:
    """Добавляет запись аудита в текущую транзакцию. Если ничего не изменилось — не пишет.

    `require_comment=True` — для override-операций (допуск вопреки требованиям, нарушение отдыха).
    """
    if require_comment and not (comment and comment.strip()):
        raise ValidationFailedError("Для этой операции обязателен комментарий")
    b, a = diff(before, after)
    if before is not None and after is not None and not b and not a:
        return None
    operator = current_operator.get()
    entry = AuditLog(
        id=uuid7(),
        actor_id=operator.subject if operator else SYSTEM_ACTOR,
        actor_name=(operator.full_name or operator.username) if operator else SYSTEM_ACTOR,
        actor_unit_id=operator.unit_id if operator else None,
        request_id=current_request_id.get(),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        scope_unit_id=scope_unit_id,
        before=b,
        after=a,
        comment=comment,
    )
    session.add(entry)
    add_event(
        session,
        "audit.recorded",
        entity_type,
        entity_id,
        {
            "audit_id": entry.id,
            "actor_id": entry.actor_id,
            "actor_name": entry.actor_name,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "scope_unit_id": scope_unit_id,
            "before": b,
            "after": a,
            "comment": comment,
            "request_id": entry.request_id,
        },
    )
    return entry
