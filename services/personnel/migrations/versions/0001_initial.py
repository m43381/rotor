"""Начальная схема personnel: личный состав, должности, характеристики, освобождения,
проекции org, аудит, outbox.

Сгенерировано autogenerate и доработано вручную: расширения, триграммный индекс ФИО,
exclusion-ограничение освобождений, начальные справочники, append-only триггер аудита.

Revision ID: 0001
Revises:
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from dutyflow_common.ltree import Ltree

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Фиксированные id начальных записей справочников — чтобы на всех стендах они совпадали.
REASONS = [
    ("00000000-0000-7000-8000-00000000e001", "illness", "Болезнь"),
    ("00000000-0000-7000-8000-00000000e002", "leave", "Отпуск"),
    ("00000000-0000-7000-8000-00000000e003", "trip", "Командировка"),
    ("00000000-0000-7000-8000-00000000e004", "other", "Прочее"),
]
CATEGORY_ID = "00000000-0000-7000-8000-00000000a001"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS ltree")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table('attribute_definition',
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('value_type', sa.String(length=10), nullable=False),
    sa.Column('enum_options', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('is_required', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.SmallInteger(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("value_type IN ('bool', 'int', 'enum', 'date', 'string')", name=op.f('ck_attribute_definition_value_type')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_attribute_definition')),
    sa.UniqueConstraint('code', name=op.f('uq_attribute_definition_code'))
    )
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
    op.create_table('exemption_reason',
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_exemption_reason')),
    sa.UniqueConstraint('code', name=op.f('uq_exemption_reason_code'))
    )
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
    op.create_table('position',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('sort_order', sa.SmallInteger(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_position')),
    sa.UniqueConstraint('name', name=op.f('uq_position_name'))
    )
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
    sa.Column('path', Ltree(), nullable=False),
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('short_name', sa.String(length=100), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('source_version', sa.Integer(), nullable=False),
    sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('unit_id', name=op.f('pk_unit_projection'))
    )
    op.create_index('ix_unit_projection_path_gist', 'unit_projection', ['path'], unique=False, postgresql_using='gist')
    op.create_table('person',
    sa.Column('unit_id', sa.Uuid(), nullable=False),
    sa.Column('last_name', sa.String(length=100), nullable=False),
    sa.Column('first_name', sa.String(length=100), nullable=False),
    sa.Column('middle_name', sa.String(length=100), nullable=True),
    sa.Column('rank_id', sa.Uuid(), nullable=True),
    sa.Column('position_id', sa.Uuid(), nullable=True),
    sa.Column('personal_no', sa.String(length=50), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['position_id'], ['position.id'], name=op.f('fk_person_position_id_position')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_person')),
    sa.UniqueConstraint('personal_no', name=op.f('uq_person_personal_no'))
    )
    op.execute(
        "CREATE INDEX ix_person_fio_trgm ON person USING gin "
        "(lower(last_name || ' ' || first_name || ' ' || coalesce(middle_name, '')) gin_trgm_ops)"
    )
    op.create_index('ix_person_sort', 'person', ['last_name', 'first_name', 'middle_name', 'id'], unique=False)
    op.create_index('ix_person_unit_active', 'person', ['unit_id'], unique=False, postgresql_where=sa.text('is_active'))
    op.create_table('exemption',
    sa.Column('person_id', sa.Uuid(), nullable=False),
    sa.Column('reason_id', sa.Uuid(), nullable=False),
    sa.Column('date_from', sa.Date(), nullable=False),
    sa.Column('date_to', sa.Date(), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('created_by', sa.String(length=100), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    postgresql.ExcludeConstraint((sa.column('person_id'), '='), (sa.text("daterange(date_from, date_to, '[]')"), '&&'), using='gist', name='ex_exemption_no_overlap'),
    sa.CheckConstraint('date_to >= date_from', name=op.f('ck_exemption_dates')),
    sa.ForeignKeyConstraint(['person_id'], ['person.id'], name=op.f('fk_exemption_person_id_person'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reason_id'], ['exemption_reason.id'], name=op.f('fk_exemption_reason_id_exemption_reason')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_exemption'))
    )
    op.create_index(op.f('ix_exemption_person_id'), 'exemption', ['person_id'], unique=False)
    op.create_table('person_attribute',
    sa.Column('person_id', sa.Uuid(), nullable=False),
    sa.Column('definition_id', sa.Uuid(), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.ForeignKeyConstraint(['definition_id'], ['attribute_definition.id'], name=op.f('fk_person_attribute_definition_id_attribute_definition')),
    sa.ForeignKeyConstraint(['person_id'], ['person.id'], name=op.f('fk_person_attribute_person_id_person'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('person_id', 'definition_id', name=op.f('pk_person_attribute'))
    )
    op.create_index('ix_person_attribute_value', 'person_attribute', ['value'], unique=False, postgresql_using='gin')

    # --- начальные справочники (open-questions №6, №30) ---
    reason = sa.table(
        "exemption_reason",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(
        reason,
        [{"id": i, "code": c, "name": n, "is_active": True} for i, c, n in REASONS],
    )
    attr = sa.table(
        "attribute_definition",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("value_type", sa.String()),
        sa.column("enum_options", postgresql.JSONB()),
        sa.column("is_required", sa.Boolean()),
        sa.column("sort_order", sa.SmallInteger()),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(
        attr,
        [
            {
                "id": CATEGORY_ID,
                "code": "category",
                "name": "Категория",
                "value_type": "enum",
                "enum_options": ["Курсант", "Слушатель", "Постоянный состав"],
                "is_required": False,
                "sort_order": 0,
                "is_active": True,
            }
        ],
    )

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
    op.drop_index('ix_person_attribute_value', table_name='person_attribute', postgresql_using='gin')
    op.drop_table('person_attribute')
    op.drop_index(op.f('ix_exemption_person_id'), table_name='exemption')
    op.drop_table('exemption')
    op.drop_index('ix_person_unit_active', table_name='person', postgresql_where=sa.text('is_active'))
    op.drop_index('ix_person_sort', table_name='person')
    op.execute('DROP INDEX IF EXISTS ix_person_fio_trgm')
    op.drop_table('person')
    op.drop_index('ix_unit_projection_path_gist', table_name='unit_projection', postgresql_using='gist')
    op.drop_table('unit_projection')
    op.drop_table('rank_projection')
    op.drop_table('processed_event')
    op.drop_table('position')
    op.drop_index('ix_outbox_unpublished', table_name='outbox', postgresql_where=sa.text('published_at IS NULL'))
    op.drop_table('outbox')
    op.drop_table('exemption_reason')
    op.drop_index('ix_audit_log_scope', table_name='audit_log')
    op.drop_index('ix_audit_log_entity', table_name='audit_log')
    op.drop_table('audit_log')
    op.drop_table('attribute_definition')
