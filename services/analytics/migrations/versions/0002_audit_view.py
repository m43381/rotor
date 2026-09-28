"""Сводный журнал аудита (фаза 7b, ADR-0010).

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-28
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
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "audit_view",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("service", sa.String(50), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("actor_name", sa.String(200), nullable=False),
        sa.Column("actor_unit_id", sa.Uuid()),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("scope_unit_id", sa.Uuid()),
        sa.Column("before", jsonb),
        sa.Column("after", jsonb),
        sa.Column("comment", sa.Text()),
        sa.Column("request_id", sa.String(64), nullable=False),
    )
    op.create_index("ix_audit_view_time", "audit_view", ["occurred_at"])
    op.create_index("ix_audit_view_scope_time", "audit_view", ["scope_unit_id", "occurred_at"])
    op.create_index("ix_audit_view_actor_time", "audit_view", ["actor_id", "occurred_at"])
    op.create_index("ix_audit_view_entity", "audit_view", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_table("audit_view")
