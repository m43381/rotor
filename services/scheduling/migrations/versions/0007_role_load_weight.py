"""Вес нагрузки — у роли, а не у наряда целиком (ADR-0019, фаза 8).

Каждая роль получает вес своего наряда, колонка наряда удаляется. Нагрузка уже сохранённых
назначений в read-model analytics пересчитывается перестроением (`just analytics-rebuild`).

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "duty_role",
        sa.Column(
            "load_weight",
            sa.Numeric(precision=4, scale=2, asdecimal=False),
            nullable=False,
            server_default="1",
        ),
    )
    op.execute(
        "UPDATE duty_role r SET load_weight = t.load_weight FROM duty_type t"
        " WHERE t.id = r.duty_type_id"
    )
    op.alter_column("duty_role", "load_weight", server_default=None)
    op.create_check_constraint(op.f("ck_duty_role_load_weight"), "duty_role", "load_weight > 0")
    op.drop_constraint(op.f("ck_duty_type_load_weight"), "duty_type", type_="check")
    op.drop_column("duty_type", "load_weight")


def downgrade() -> None:
    op.add_column(
        "duty_type",
        sa.Column(
            "load_weight",
            sa.Numeric(precision=4, scale=2, asdecimal=False),
            nullable=False,
            server_default="1",
        ),
    )
    # Наряду — наибольший вес его ролей
    op.execute(
        "UPDATE duty_type t SET load_weight = w.m FROM"
        " (SELECT duty_type_id, max(load_weight) m FROM duty_role GROUP BY duty_type_id) w"
        " WHERE w.duty_type_id = t.id"
    )
    op.alter_column("duty_type", "load_weight", server_default=None)
    op.create_check_constraint(op.f("ck_duty_type_load_weight"), "duty_type", "load_weight > 0")
    op.drop_constraint(op.f("ck_duty_role_load_weight"), "duty_role", type_="check")
    op.drop_column("duty_role", "load_weight")
