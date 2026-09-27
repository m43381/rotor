"""Начальная схема analytics: факты нарядов (read-model), проекции org, служебные таблицы
событий.

Revision ID: 0001
Revises:
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from dutyflow_common.ltree import Ltree

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS ltree")
    op.create_table(
        "duty_fact",
        sa.Column("assignment_id", sa.Uuid(), primary_key=True),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("person_name", sa.String(200), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("schedule_status", sa.String(10), nullable=False),
        sa.Column("duty_type_id", sa.Uuid(), nullable=False),
        sa.Column("duty_role_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occupied_days", sa.SmallInteger(), nullable=False),
        sa.Column("load", sa.Float(), nullable=False),
        sa.Column("holiday", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(10), nullable=False),
    )
    op.create_index("ix_duty_fact_unit_date", "duty_fact", ["unit_id", "date"])
    op.create_index("ix_duty_fact_schedule", "duty_fact", ["schedule_id"])
    op.create_index("ix_duty_fact_person_date", "duty_fact", ["person_id", "date"])

    op.create_table(
        "unit_projection",
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid()),
        sa.Column("path", Ltree(), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("short_name", sa.String(100)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column(
            "synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("unit_id", name=op.f("pk_unit_projection")),
    )
    op.create_index(
        "ix_unit_projection_path_gist", "unit_projection", ["path"], postgresql_using="gist"
    )
    op.create_table(
        "rank_projection",
        sa.Column("rank_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("short_name", sa.String(50)),
        sa.Column("order", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("rank_id", name=op.f("pk_rank_projection")),
    )
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
        "ix_outbox_unpublished", "outbox", ["id"], postgresql_where=sa.text("published_at IS NULL")
    )
    op.create_table(
        "processed_event",
        sa.Column("consumer", sa.String(100), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("consumer", "event_id", name=op.f("pk_processed_event")),
    )


def downgrade() -> None:
    for table in ("processed_event", "outbox", "rank_projection", "unit_projection", "duty_fact"):
        op.drop_table(table)
