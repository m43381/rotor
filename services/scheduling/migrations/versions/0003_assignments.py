"""Назначения людей в ячейки (exclusion-ограничение «не больше одного наряда в сутки»)
и лимиты нарядов на месяц (фаза 3b).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('duty_limit',
    sa.Column('unit_id', sa.Uuid(), nullable=False),
    sa.Column('applies_to_subtree', sa.Boolean(), nullable=False),
    sa.Column('rank_id', sa.Uuid(), nullable=True),
    sa.Column('position_id', sa.Uuid(), nullable=True),
    sa.Column('max_duties', sa.SmallInteger(), nullable=True),
    sa.Column('max_holiday_duties', sa.SmallInteger(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.CheckConstraint('max_duties IS NOT NULL OR max_holiday_duties IS NOT NULL', name=op.f('ck_duty_limit_has_limit')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_duty_limit'))
    )
    op.create_index(op.f('ix_duty_limit_unit_id'), 'duty_limit', ['unit_id'], unique=False)
    op.create_table('assignment',
    sa.Column('day_plan_id', sa.Uuid(), nullable=False),
    sa.Column('person_id', sa.Uuid(), nullable=False),
    sa.Column('person_name', sa.String(length=200), nullable=False),
    sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('occupied_days', postgresql.DATERANGE(), nullable=False),
    sa.Column('source', sa.String(length=10), nullable=False),
    sa.Column('is_pinned', sa.Boolean(), nullable=False),
    sa.Column('rest_override', sa.Boolean(), nullable=False),
    sa.Column('limit_override', sa.Boolean(), nullable=False),
    sa.Column('override_comment', sa.Text(), nullable=True),
    sa.Column('conflict', sa.Text(), nullable=True),
    sa.Column('assigned_by', sa.String(length=100), nullable=False),
    sa.Column('assigned_by_name', sa.String(length=200), nullable=False),
    sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    postgresql.ExcludeConstraint((sa.column('person_id'), '='), (sa.column('occupied_days'), '&&'), using='gist', name='ex_assignment_one_per_day'),
    sa.CheckConstraint("NOT (rest_override OR limit_override) OR length(btrim(coalesce(override_comment, ''))) > 0", name=op.f('ck_assignment_override_comment')),
    sa.CheckConstraint("source IN ('manual', 'auto')", name=op.f('ck_assignment_source')),
    sa.CheckConstraint('end_at > start_at', name=op.f('ck_assignment_interval')),
    sa.ForeignKeyConstraint(['day_plan_id'], ['day_plan.id'], name=op.f('fk_assignment_day_plan_id_day_plan'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_assignment')),
    sa.UniqueConstraint('day_plan_id', 'person_id', name=op.f('uq_assignment_day_plan_id_person_id'))
    )
    op.create_index('ix_assignment_person_start', 'assignment', ['person_id', 'start_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_assignment_person_start', table_name='assignment')
    op.drop_table('assignment')
    op.drop_index(op.f('ix_duty_limit_unit_id'), table_name='duty_limit')
    op.drop_table('duty_limit')
