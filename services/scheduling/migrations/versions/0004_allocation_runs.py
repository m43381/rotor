"""Прогоны движка распределения и объяснения решений (фаза 4b): предпросмотр → применение.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('allocation_run',
    sa.Column('schedule_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('mode', sa.String(length=10), nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('seed', sa.Integer(), nullable=False),
    sa.Column('snapshot_hash', sa.String(length=64), nullable=False),
    sa.Column('snapshot', postgresql.BYTEA(), nullable=False),
    sa.Column('solution_hash', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_by', sa.String(length=100), nullable=False),
    sa.Column('created_by_name', sa.String(length=200), nullable=False),
    sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('applied_by_name', sa.String(length=200), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('people', 'units')", name=op.f('ck_allocation_run_kind')),
    sa.CheckConstraint("mode IN ('fill', 'rebuild')", name=op.f('ck_allocation_run_mode')),
    sa.CheckConstraint("status IN ('preview_ready', 'applied', 'discarded', 'stale', 'failed')", name=op.f('ck_allocation_run_status')),
    sa.ForeignKeyConstraint(['schedule_id'], ['schedule.id'], name=op.f('fk_allocation_run_schedule_id_schedule'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_allocation_run'))
    )
    op.create_index('ix_allocation_run_schedule', 'allocation_run', ['schedule_id', 'created_at'], unique=False)
    op.create_table('allocation_decision',
    sa.Column('run_id', sa.Uuid(), nullable=False),
    sa.Column('day_plan_id', sa.Uuid(), nullable=False),
    sa.Column('chosen_id', sa.Uuid(), nullable=False),
    sa.Column('chosen_name', sa.String(length=300), nullable=False),
    sa.Column('rank', sa.SmallInteger(), nullable=False),
    sa.Column('cost', sa.Numeric(precision=12, scale=6, asdecimal=False), nullable=False),
    sa.Column('candidates', sa.Integer(), nullable=False),
    sa.Column('features', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('alternatives', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('rejected_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['run_id'], ['allocation_run.id'], name=op.f('fk_allocation_decision_run_id_allocation_run'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('run_id', 'day_plan_id', 'chosen_id', name=op.f('pk_allocation_decision'))
    )
    op.add_column('assignment', sa.Column('allocation_run_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_assignment_allocation_run_id'), 'assignment', ['allocation_run_id'], unique=False)
    op.create_foreign_key(op.f('fk_assignment_allocation_run_id_allocation_run'), 'assignment', 'allocation_run', ['allocation_run_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint(op.f('fk_assignment_allocation_run_id_allocation_run'), 'assignment', type_='foreignkey')
    op.drop_index(op.f('ix_assignment_allocation_run_id'), table_name='assignment')
    op.drop_column('assignment', 'allocation_run_id')
    op.drop_table('allocation_decision')
    op.drop_index('ix_allocation_run_schedule', table_name='allocation_run')
    op.drop_table('allocation_run')
