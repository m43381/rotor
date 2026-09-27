"""Начальная схема scheduling (фаза 2b): типы нарядов, роли с требованиями, проекции org,
аудит, outbox.

Сгенерировано autogenerate и доработано вручную: расширения, append-only триггер аудита.

Revision ID: 0001
Revises:
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

import dutyflow_common.ltree

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS ltree")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table('audit_log',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('actor_id', sa.String(length=100), nullable=False),
    sa.Column('actor_name', sa.String(length=200), nullable=False),
    sa.Column('actor_unit_id', sa.Uuid(), nullable=True),
    sa.Column('request_id', sa.String(length=64), nullable=False),
    sa.Column('action', sa.String(length=100), nullable=False),
    sa.Column('entity_type', sa.String(length=50), nullable=False),
    sa.Column('entity_id', sa.Uuid(), nullable=False),
    sa.Column('scope_unit_id', sa.Uuid(), nullable=True),
    sa.Column('before', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('after', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_log'))
    )
    op.create_index('ix_audit_log_entity', 'audit_log', ['entity_type', 'entity_id', 'occurred_at'], unique=False)
    op.create_index('ix_audit_log_scope', 'audit_log', ['scope_unit_id', 'occurred_at'], unique=False)
    op.create_table('duty_type',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('short_name', sa.String(length=50), nullable=True),
    sa.Column('owner_unit_id', sa.Uuid(), nullable=False),
    sa.Column('assigned_unit_id', sa.Uuid(), nullable=True),
    sa.Column('start_time', sa.Time(), nullable=False),
    sa.Column('duration_minutes', sa.Integer(), nullable=False),
    sa.Column('rest_hours', sa.SmallInteger(), nullable=False),
    sa.Column('load_weight', sa.Numeric(precision=4, scale=2, asdecimal=False), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.CheckConstraint('duration_minutes BETWEEN 60 AND 10080', name=op.f('ck_duty_type_duration')),
    sa.CheckConstraint('load_weight > 0', name=op.f('ck_duty_type_load_weight')),
    sa.CheckConstraint('rest_hours BETWEEN 0 AND 720', name=op.f('ck_duty_type_rest_hours')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_duty_type'))
    )
    op.create_index(op.f('ix_duty_type_owner_unit_id'), 'duty_type', ['owner_unit_id'], unique=False)
    op.create_index('uq_duty_type_owner_name_active', 'duty_type', ['owner_unit_id', 'name'], unique=True, postgresql_where=sa.text('is_active'))
    op.create_table('outbox',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('event_type', sa.String(length=100), nullable=False),
    sa.Column('aggregate_type', sa.String(length=50), nullable=False),
    sa.Column('aggregate_id', sa.Uuid(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_outbox'))
    )
    op.create_index('ix_outbox_unpublished', 'outbox', ['id'], unique=False, postgresql_where=sa.text('published_at IS NULL'))
    op.create_table('processed_event',
    sa.Column('consumer', sa.String(length=100), nullable=False),
    sa.Column('event_id', sa.Uuid(), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('consumer', 'event_id', name=op.f('pk_processed_event'))
    )
    op.create_table('rank_projection',
    sa.Column('rank_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('short_name', sa.String(length=50), nullable=True),
    sa.Column('order', sa.SmallInteger(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('rank_id', name=op.f('pk_rank_projection'))
    )
    op.create_table('unit_projection',
    sa.Column('unit_id', sa.Uuid(), nullable=False),
    sa.Column('parent_id', sa.Uuid(), nullable=True),
    sa.Column('path', dutyflow_common.ltree.Ltree(), nullable=False),
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('short_name', sa.String(length=100), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('source_version', sa.Integer(), nullable=False),
    sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('unit_id', name=op.f('pk_unit_projection'))
    )
    op.create_index('ix_unit_projection_path_gist', 'unit_projection', ['path'], unique=False, postgresql_using='gist')
    op.create_table('duty_role',
    sa.Column('duty_type_id', sa.Uuid(), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('headcount', sa.SmallInteger(), nullable=False),
    sa.Column('sort_order', sa.SmallInteger(), nullable=False),
    sa.Column('min_rank_order', sa.SmallInteger(), nullable=True),
    sa.Column('allowed_position_ids', sa.ARRAY(sa.Uuid()), nullable=True),
    sa.Column('attribute_requirements', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.CheckConstraint('headcount BETWEEN 1 AND 100', name=op.f('ck_duty_role_headcount')),
    sa.ForeignKeyConstraint(['duty_type_id'], ['duty_type.id'], name=op.f('fk_duty_role_duty_type_id_duty_type')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_duty_role')),
    sa.UniqueConstraint('duty_type_id', 'code', name=op.f('uq_duty_role_duty_type_id_code'))
    )
    op.create_index(op.f('ix_duty_role_duty_type_id'), 'duty_role', ['duty_type_id'], unique=False)

    # Журнал аудита только дополняется (ADR-0010).
    op.execute(
        """
        CREATE FUNCTION audit_log_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER audit_log_no_update BEFORE UPDATE OR DELETE ON audit_log"
        " FOR EACH ROW EXECUTE FUNCTION audit_log_immutable()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_immutable()")
    op.drop_index(op.f('ix_duty_role_duty_type_id'), table_name='duty_role')
    op.drop_table('duty_role')
    op.drop_index('ix_unit_projection_path_gist', table_name='unit_projection', postgresql_using='gist')
    op.drop_table('unit_projection')
    op.drop_table('rank_projection')
    op.drop_table('processed_event')
    op.drop_index('ix_outbox_unpublished', table_name='outbox', postgresql_where=sa.text('published_at IS NULL'))
    op.drop_table('outbox')
    op.drop_index('uq_duty_type_owner_name_active', table_name='duty_type', postgresql_where=sa.text('is_active'))
    op.drop_index(op.f('ix_duty_type_owner_unit_id'), table_name='duty_type')
    op.drop_table('duty_type')
    op.drop_index('ix_audit_log_scope', table_name='audit_log')
    op.drop_index('ix_audit_log_entity', table_name='audit_log')
    op.drop_table('audit_log')
