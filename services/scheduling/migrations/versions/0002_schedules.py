"""Графики подразделений на месяц, ячейки «дата × роль» с делегированием, проекция
производственного календаря org (фаза 3a).

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('calendar_projection',
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=True),
    sa.PrimaryKeyConstraint('date', name=op.f('pk_calendar_projection'))
    )
    op.create_table('schedule',
    sa.Column('unit_id', sa.Uuid(), nullable=False),
    sa.Column('month', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('published_by', sa.String(length=200), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.CheckConstraint("status IN ('draft', 'published', 'archived')", name=op.f('ck_schedule_status')),
    sa.CheckConstraint('extract(day FROM month) = 1', name=op.f('ck_schedule_month_first_day')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_schedule')),
    sa.UniqueConstraint('unit_id', 'month', name=op.f('uq_schedule_unit_id_month'))
    )
    op.create_table('day_plan',
    sa.Column('schedule_id', sa.Uuid(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('duty_type_id', sa.Uuid(), nullable=False),
    sa.Column('duty_role_id', sa.Uuid(), nullable=False),
    sa.Column('origin', sa.String(length=10), nullable=False),
    sa.Column('parent_day_plan_id', sa.Uuid(), nullable=True),
    sa.Column('executor_unit_id', sa.Uuid(), nullable=False),
    sa.Column('delegation_status', sa.String(length=10), nullable=False),
    sa.Column('is_pinned', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.CheckConstraint("(origin = 'own') = (parent_day_plan_id IS NULL)", name=op.f('ck_day_plan_incoming_has_parent')),
    sa.CheckConstraint("delegation_status IN ('none', 'pending', 'accepted')", name=op.f('ck_day_plan_delegation_status')),
    sa.CheckConstraint("origin IN ('own', 'incoming')", name=op.f('ck_day_plan_origin')),
    sa.ForeignKeyConstraint(['duty_role_id'], ['duty_role.id'], name=op.f('fk_day_plan_duty_role_id_duty_role')),
    sa.ForeignKeyConstraint(['duty_type_id'], ['duty_type.id'], name=op.f('fk_day_plan_duty_type_id_duty_type')),
    sa.ForeignKeyConstraint(['parent_day_plan_id'], ['day_plan.id'], name=op.f('fk_day_plan_parent_day_plan_id_day_plan'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['schedule_id'], ['schedule.id'], name=op.f('fk_day_plan_schedule_id_schedule'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_day_plan')),
    sa.UniqueConstraint('parent_day_plan_id', name=op.f('uq_day_plan_parent_day_plan_id')),
    sa.UniqueConstraint('schedule_id', 'date', 'duty_role_id', name=op.f('uq_day_plan_schedule_id_date_duty_role_id'))
    )
    op.create_index(op.f('ix_day_plan_duty_role_id'), 'day_plan', ['duty_role_id'], unique=False)
    op.create_index('ix_day_plan_pending', 'day_plan', ['schedule_id'], unique=False, postgresql_where=sa.text("delegation_status = 'pending'"))


def downgrade() -> None:
    op.drop_index('ix_day_plan_pending', table_name='day_plan', postgresql_where=sa.text("delegation_status = 'pending'"))
    op.drop_index(op.f('ix_day_plan_duty_role_id'), table_name='day_plan')
    op.drop_table('day_plan')
    op.drop_table('schedule')
    op.drop_table('calendar_projection')
