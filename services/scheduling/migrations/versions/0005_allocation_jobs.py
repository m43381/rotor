"""Фоновые прогоны движка (фаза 5b): id задачи в очереди, статусы «в очереди» и «считается»,
hash решения появляется, когда расчёт готов.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "status IN ('preview_ready', 'applied', 'discarded', 'stale', 'failed')"
NEW = (
    "status IN ('queued', 'running', 'preview_ready', 'applied', 'discarded', 'stale',"
    " 'failed')"
)


def upgrade() -> None:
    op.add_column("allocation_run", sa.Column("job_id", sa.String(length=64), nullable=True))
    op.alter_column("allocation_run", "solution_hash", existing_type=sa.String(64), nullable=True)
    op.drop_constraint(op.f("ck_allocation_run_status"), "allocation_run", type_="check")
    op.create_check_constraint(op.f("ck_allocation_run_status"), "allocation_run", NEW)


def downgrade() -> None:
    op.execute("DELETE FROM allocation_run WHERE status IN ('queued', 'running')")
    op.drop_constraint(op.f("ck_allocation_run_status"), "allocation_run", type_="check")
    op.create_check_constraint(op.f("ck_allocation_run_status"), "allocation_run", OLD)
    op.alter_column("allocation_run", "solution_hash", existing_type=sa.String(64), nullable=False)
    op.drop_column("allocation_run", "job_id")
