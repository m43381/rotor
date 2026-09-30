"""Категория личного состава — справочник и поле человека; закрепление и категории ролей
в локальной копии (ADR-0018, фаза 8).

Характеристика «Категория» (`attribute_definition.code = 'category'`) переносится:
варианты перечисления становятся записями справочника с детерминированными id
(`dutyflow_common.ids.category_id`), значения людей — `person.category_id`, характеристика
выводится из действия. Требования «Категория = / одно из» в локальной копии ролей переводятся
в `allowed_category_ids` тем же способом, что и в scheduling; окончательные значения (вместе
с закреплением) придут событиями `duty_role.changed`, которые пишет миграция scheduling.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from dutyflow_common.ids import category_id

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KNOWN_CODES = {"Курсант": "cadet", "Слушатель": "listener", "Постоянный состав": "permanent"}
DEFAULT_CATEGORIES = list(KNOWN_CODES)


def upgrade() -> None:
    op.create_table(
        'person_category',
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('sort_order', sa.SmallInteger(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_person_category')),
        sa.UniqueConstraint('code', name=op.f('uq_person_category_code')),
        sa.UniqueConstraint('name', name=op.f('uq_person_category_name')),
    )
    op.add_column('person', sa.Column('category_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_person_category_id'), 'person', ['category_id'], unique=False)
    op.create_foreign_key(
        op.f('fk_person_category_id_person_category'), 'person', 'person_category', ['category_id'], ['id']
    )
    op.add_column('duty_role_projection', sa.Column('assigned_unit_id', sa.Uuid(), nullable=True))
    op.add_column('duty_role_projection', sa.Column('allowed_category_ids', sa.ARRAY(sa.Uuid()), nullable=True))

    conn = op.get_bind()
    options = conn.scalar(
        sa.text("SELECT enum_options FROM attribute_definition WHERE code = 'category'")
    )
    names = list(options or DEFAULT_CATEGORIES)
    category = sa.table(
        'person_category',
        sa.column('id', sa.Uuid()),
        sa.column('code', sa.String()),
        sa.column('name', sa.String()),
        sa.column('sort_order', sa.SmallInteger()),
        sa.column('is_active', sa.Boolean()),
    )
    op.bulk_insert(
        category,
        [
            {
                "id": category_id(name),
                "code": KNOWN_CODES.get(name, f"category{i + 1}"),
                "name": name,
                "sort_order": i,
                "is_active": True,
            }
            for i, name in enumerate(names)
        ],
    )
    if options is None:
        return
    for name in names:
        conn.execute(
            sa.text(
                """
                UPDATE person p SET category_id = :cid
                FROM person_attribute pa JOIN attribute_definition d ON d.id = pa.definition_id
                WHERE pa.person_id = p.id AND d.code = 'category' AND pa.value->>'v' = :name
                """
            ),
            {"cid": category_id(name), "name": name},
        )
    conn.execute(
        sa.text(
            """
            DELETE FROM person_attribute pa USING attribute_definition d
            WHERE d.id = pa.definition_id AND d.code = 'category'
            """
        )
    )
    conn.execute(
        sa.text("UPDATE attribute_definition SET is_active = false WHERE code = 'category'")
    )
    _convert_role_requirements(conn)


def _convert_role_requirements(conn: sa.Connection) -> None:
    """`category eq/in` в требованиях ролей → `allowed_category_ids` (как в scheduling)."""
    rows = conn.execute(
        sa.text(
            "SELECT duty_role_id, attribute_requirements FROM duty_role_projection "
            "WHERE attribute_requirements @> '[{\"code\": \"category\"}]'"
        )
    ).all()
    for role_id, requirements in rows:
        allowed: list[str] = []
        rest = []
        for r in requirements:
            if r.get("code") != "category":
                rest.append(r)
                continue
            values = r["value"] if r.get("op") == "in" else [r.get("value")]
            allowed += [str(category_id(v)) for v in values if isinstance(v, str)]
        conn.execute(
            sa.text(
                "UPDATE duty_role_projection SET attribute_requirements = :rest, "
                "allowed_category_ids = CAST(:allowed AS uuid[]) WHERE duty_role_id = :id"
            ).bindparams(sa.bindparam("rest", type_=postgresql.JSONB)),
            {"rest": rest, "allowed": sorted(set(allowed)), "id": role_id},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE attribute_definition SET is_active = true WHERE code = 'category'")
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO person_attribute (person_id, definition_id, value)
            SELECT p.id, d.id, jsonb_build_object('v', c.name)
            FROM person p
            JOIN person_category c ON c.id = p.category_id
            JOIN attribute_definition d ON d.code = 'category'
            ON CONFLICT DO NOTHING
            """
        )
    )
    op.drop_column('duty_role_projection', 'allowed_category_ids')
    op.drop_column('duty_role_projection', 'assigned_unit_id')
    op.drop_constraint(op.f('fk_person_category_id_person_category'), 'person', type_='foreignkey')
    op.drop_index(op.f('ix_person_category_id'), table_name='person')
    op.drop_column('person', 'category_id')
    op.drop_table('person_category')
