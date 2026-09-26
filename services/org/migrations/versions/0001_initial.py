"""Начальная схема org: дерево подразделений (ltree), справочники, аудит, outbox.

Revision ID: 0001
Revises:
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from dutyflow_common.ltree import Ltree
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS ltree")

    op.create_table(
        "unit_type",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("can_have_children", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_unit_type"),
        sa.UniqueConstraint("code", name="uq_unit_type_code"),
    )

    op.execute("CREATE SEQUENCE unit_node_no_seq START WITH 1")
    op.create_table(
        "unit",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("node_no", sa.BigInteger(),
                  server_default=sa.text("nextval('unit_node_no_seq')"), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("unit_type_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("short_name", sa.String(100), nullable=True),
        sa.Column("path", Ltree(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_unit"),
        sa.ForeignKeyConstraint(["parent_id"], ["unit.id"], name="fk_unit_parent_id_unit"),
        sa.ForeignKeyConstraint(["unit_type_id"], ["unit_type.id"],
                                name="fk_unit_unit_type_id_unit_type"),
        sa.UniqueConstraint("node_no", name="uq_unit_node_no"),
    )
    op.execute("ALTER SEQUENCE unit_node_no_seq OWNED BY unit.node_no")
    op.create_index("ix_unit_parent_id", "unit", ["parent_id"])
    op.create_index("ix_unit_path_gist", "unit", ["path"], postgresql_using="gist")
    op.create_index("uq_unit_parent_name_active", "unit", ["parent_id", "name"], unique=True,
                    postgresql_where=sa.text("is_active"))

    op.create_table(
        "rank",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("short_name", sa.String(50), nullable=True),
        sa.Column("order", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_rank"),
        sa.UniqueConstraint("order", name="uq_rank_order"),
    )

    op.create_table(
        "calendar_day",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("name", sa.String(200), nullable=True),
        sa.PrimaryKeyConstraint("date", name="pk_calendar_day"),
        sa.CheckConstraint("kind IN ('holiday', 'workday', 'preholiday')",
                           name="ck_calendar_day_kind"),
    )

    op.create_table(
        "installation_setting",
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("key", name="pk_installation_setting"),
    )

    # --- общие таблицы libs/common -----------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("actor_name", sa.String(200), nullable=False),
        sa.Column("actor_unit_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("scope_unit_id", sa.Uuid(), nullable=True),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )
    op.create_index("ix_audit_log_entity", "audit_log",
                    ["entity_type", "entity_id", "occurred_at"])
    op.create_index("ix_audit_log_scope", "audit_log", ["scope_unit_id", "occurred_at"])

    op.create_table(
        "outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("aggregate_type", sa.String(50), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_outbox"),
    )
    op.create_index("ix_outbox_unpublished", "outbox", ["id"],
                    postgresql_where=sa.text("published_at IS NULL"))

    op.create_table(
        "processed_event",
        sa.Column("consumer", sa.String(100), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("consumer", "event_id", name="pk_processed_event"),
    )

    # Журнал аудита только дополняется (ADR-0010). Запрет UPDATE/DELETE — триггером, чтобы
    # он действовал независимо от того, под какой ролью БД работает сервис.
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
    for table in ("processed_event", "outbox", "audit_log", "installation_setting",
                  "calendar_day", "rank", "unit", "unit_type"):
        op.drop_table(table)
    op.execute("DROP SEQUENCE IF EXISTS unit_node_no_seq")
