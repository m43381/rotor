"""Печать (фаза 6b): реквизиты подразделений, загруженные шаблоны форм, журнал аудита и
outbox (записи аудита публикуются событием `audit.recorded`, ADR-0010).

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_settings",
        sa.Column("unit_id", sa.Uuid(), primary_key=True),
        sa.Column("approver_position", sa.String(300)),
        sa.Column("approver_rank", sa.String(100)),
        sa.Column("approver_name", sa.String(200)),
        sa.Column("compiler_position", sa.String(300)),
        sa.Column("compiler_rank", sa.String(100)),
        sa.Column("compiler_name", sa.String(200)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by_name", sa.String(200), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "print_template",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("form", sa.String(50), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_name", sa.String(200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_print_template_form", "print_template", ["form", "created_at"])
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("actor_name", sa.String(200), nullable=False),
        sa.Column("actor_unit_id", sa.Uuid()),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("scope_unit_id", sa.Uuid()),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("comment", sa.Text()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(
        "ix_audit_log_entity", "audit_log", ["entity_type", "entity_id", "occurred_at"]
    )
    op.create_index("ix_audit_log_scope", "audit_log", ["scope_unit_id", "occurred_at"])
    op.create_table(
        "outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("aggregate_type", sa.String(50), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox")),
    )
    op.create_index(
        "ix_outbox_unpublished",
        "outbox",
        ["id"],
        postgresql_where=sa.text("published_at IS NULL"),
    )
    # Общая таблица модуля outbox; documents пока не потребляет событий
    op.create_table(
        "processed_event",
        sa.Column("consumer", sa.String(100), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("consumer", "event_id", name=op.f("pk_processed_event")),
    )


def downgrade() -> None:
    op.drop_table("processed_event")
    op.drop_table("outbox")
    op.drop_table("audit_log")
    op.drop_table("print_template")
    op.drop_table("document_settings")
