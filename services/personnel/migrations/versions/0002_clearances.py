"""Допуски к ролям нарядов и локальная копия типов нарядов и ролей из scheduling (фаза 2b).

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('duty_role_projection',
    sa.Column('duty_role_id', sa.Uuid(), nullable=False),
    sa.Column('duty_type_id', sa.Uuid(), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('sort_order', sa.SmallInteger(), nullable=False),
    sa.Column('min_rank_order', sa.SmallInteger(), nullable=True),
    sa.Column('allowed_position_ids', sa.ARRAY(sa.Uuid()), nullable=True),
    sa.Column('attribute_requirements', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('source_version', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('duty_role_id', name=op.f('pk_duty_role_projection'))
    )
    op.create_index(op.f('ix_duty_role_projection_duty_type_id'), 'duty_role_projection', ['duty_type_id'], unique=False)
    op.create_table('duty_type_projection',
    sa.Column('duty_type_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('short_name', sa.String(length=50), nullable=True),
    sa.Column('owner_unit_id', sa.Uuid(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('source_version', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('duty_type_id', name=op.f('pk_duty_type_projection'))
    )
    op.create_table('clearance',
    sa.Column('person_id', sa.Uuid(), nullable=False),
    sa.Column('duty_role_id', sa.Uuid(), nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=True),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.Column('overrides_requirements', sa.Boolean(), nullable=False),
    sa.Column('override_comment', sa.Text(), nullable=True),
    sa.Column('granted_by', sa.String(length=100), nullable=False),
    sa.Column('granted_by_name', sa.String(length=200), nullable=False),
    sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_by', sa.String(length=100), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.CheckConstraint("NOT overrides_requirements OR length(btrim(coalesce(override_comment, ''))) > 0", name=op.f('ck_clearance_override_comment')),
    sa.CheckConstraint('valid_from IS NULL OR valid_to IS NULL OR valid_to >= valid_from', name=op.f('ck_clearance_dates')),
    sa.ForeignKeyConstraint(['person_id'], ['person.id'], name=op.f('fk_clearance_person_id_person'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_clearance'))
    )
    op.create_index(op.f('ix_clearance_person_id'), 'clearance', ['person_id'], unique=False)
    op.create_index('ix_clearance_role', 'clearance', ['duty_role_id'], unique=False, postgresql_where=sa.text('revoked_at IS NULL'))
    op.create_index('uq_clearance_person_role_active', 'clearance', ['person_id', 'duty_role_id'], unique=True, postgresql_where=sa.text('revoked_at IS NULL'))


def downgrade() -> None:
    op.drop_index('uq_clearance_person_role_active', table_name='clearance', postgresql_where=sa.text('revoked_at IS NULL'))
    op.drop_index('ix_clearance_role', table_name='clearance', postgresql_where=sa.text('revoked_at IS NULL'))
    op.drop_index(op.f('ix_clearance_person_id'), table_name='clearance')
    op.drop_table('clearance')
    op.drop_table('duty_type_projection')
    op.drop_index(op.f('ix_duty_role_projection_duty_type_id'), table_name='duty_role_projection')
    op.drop_table('duty_role_projection')
