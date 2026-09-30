"""Разрезы аналитики (фаза 8, ADR-0020): названия наряда и роли в факте, проекция людей
(категория, звание) и справочник категорий личного состава.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("duty_fact", sa.Column("duty_type_name", sa.String(200), nullable=True))
    op.add_column("duty_fact", sa.Column("role_name", sa.String(200), nullable=True))
    op.create_table(
        "person_dim",
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("rank_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("person_id", name=op.f("pk_person_dim")),
    )
    op.create_table(
        "category_dim",
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("category_id", name=op.f("pk_category_dim")),
    )


def downgrade() -> None:
    op.drop_table("category_dim")
    op.drop_table("person_dim")
    op.drop_column("duty_fact", "role_name")
    op.drop_column("duty_fact", "duty_type_name")
