"""Закрепление роли за подразделением и допустимые категории личного состава (ADR-0018, фаза 8).

- `duty_role.assigned_unit_id` заменяет `duty_type.assigned_unit_id`: закрепление наряда
  переносится во все его роли без собственного закрепления, колонка типа удаляется.
- `duty_role.allowed_category_ids`: требования «Категория = / одно из» переводятся в id
  категорий. Id детерминированы (`dutyflow_common.ids.category_id`) и совпадают с теми, что
  заводит миграция personnel 0003, поэтому чужая БД не нужна.
- Изменённые роли получают новую версию, и для всех ролей в outbox пишется
  `duty_role.changed`: локальная копия в personnel получает новые поля штатным путём.

Ячейки уже созданных графиков миграция не перестраивает: цепочки к закреплённому
подразделению строит сервис при следующем изменении роли или создании графика.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-30
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from dutyflow_common.ids import category_id, uuid7

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("duty_role", sa.Column("assigned_unit_id", sa.Uuid(), nullable=True))
    op.add_column("duty_role", sa.Column("allowed_category_ids", sa.ARRAY(sa.Uuid()), nullable=True))
    conn = op.get_bind()
    changed: set[str] = set(
        str(r)
        for r in conn.scalars(
            sa.text(
                """
                UPDATE duty_role r SET assigned_unit_id = t.assigned_unit_id
                FROM duty_type t
                WHERE t.id = r.duty_type_id AND t.assigned_unit_id IS NOT NULL
                RETURNING r.id
                """
            )
        )
    )
    for role_id, requirements in conn.execute(
        sa.text(
            "SELECT id, attribute_requirements FROM duty_role "
            "WHERE attribute_requirements @> '[{\"code\": \"category\"}]'"
        )
    ).all():
        allowed: set[str] = set()
        rest = []
        for r in requirements:
            if r.get("code") != "category":
                rest.append(r)
                continue
            values = r["value"] if r.get("op") == "in" else [r.get("value")]
            allowed |= {str(category_id(v)) for v in values if isinstance(v, str)}
        conn.execute(
            sa.text(
                "UPDATE duty_role SET attribute_requirements = CAST(:rest AS jsonb), "
                "allowed_category_ids = CAST(:allowed AS uuid[]) WHERE id = :id"
            ),
            {"rest": json.dumps(rest, ensure_ascii=False), "allowed": sorted(allowed), "id": role_id},
        )
        changed.add(str(role_id))
    if changed:
        conn.execute(
            sa.text("UPDATE duty_role SET version = version + 1 WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": sorted(changed)},
        )
    op.drop_column("duty_type", "assigned_unit_id")

    rows = conn.execute(
        sa.text(
            """
            SELECT id, duty_type_id, code, name, headcount, sort_order, min_rank_order,
                   allowed_position_ids, attribute_requirements, assigned_unit_id,
                   allowed_category_ids, is_active, version
            FROM duty_role ORDER BY id
            """
        )
    ).mappings().all()
    for r in rows:
        payload = {
            "id": str(r["id"]),
            "duty_type_id": str(r["duty_type_id"]),
            "code": r["code"],
            "name": r["name"],
            "headcount": r["headcount"],
            "sort_order": r["sort_order"],
            "min_rank_order": r["min_rank_order"],
            "allowed_position_ids": (
                sorted(map(str, r["allowed_position_ids"]))
                if r["allowed_position_ids"] is not None
                else None
            ),
            "attribute_requirements": r["attribute_requirements"],
            "assigned_unit_id": str(r["assigned_unit_id"]) if r["assigned_unit_id"] else None,
            "allowed_category_ids": (
                sorted(map(str, r["allowed_category_ids"]))
                if r["allowed_category_ids"] is not None
                else None
            ),
            "is_active": r["is_active"],
            "version": r["version"],
        }
        conn.execute(
            sa.text(
                "INSERT INTO outbox (id, event_type, aggregate_type, aggregate_id, payload) "
                "VALUES (:id, 'duty_role.changed', 'duty_role', :agg, CAST(:payload AS jsonb))"
            ),
            {"id": uuid7(), "agg": r["id"], "payload": json.dumps(payload, ensure_ascii=False)},
        )


def downgrade() -> None:
    op.add_column("duty_type", sa.Column("assigned_unit_id", sa.Uuid(), nullable=True))
    op.drop_column("duty_role", "allowed_category_ids")
    op.drop_column("duty_role", "assigned_unit_id")
