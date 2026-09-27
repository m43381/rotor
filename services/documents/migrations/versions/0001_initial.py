"""Начальная схема documents: задачи импорта.

Revision ID: 0001
Revises:
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "import_job",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("filename", sa.String(300), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("columns", jsonb, nullable=False),
        sa.Column("rows", jsonb, nullable=False),
        sa.Column("report", jsonb, nullable=False),
        sa.Column("summary", jsonb, nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("notes", jsonb, nullable=False),
        sa.Column("applied_rows", sa.Integer()),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("created_by_name", sa.String(200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('preview', 'applied', 'discarded')", name=op.f("ck_import_job_status")
        ),
        sa.CheckConstraint(
            "kind IN ('people', 'clearances', 'exemptions')", name=op.f("ck_import_job_kind")
        ),
    )
    op.create_index("ix_import_job_owner", "import_job", ["created_by", "created_at"])


def downgrade() -> None:
    op.drop_table("import_job")
