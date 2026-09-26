"""Первичная инициализация: корневое подразделение, если дерево пустое.

Id корня фиксирован настройкой `ROOT_UNIT_ID` — тот же id указан суперадминистратору
в Keycloak, иначе после первого запуска никто не смог бы войти (курица и яйцо).
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dutyflow_common import audit
from dutyflow_common.outbox import add_event
from org.models import Unit, UnitType, unit_node_no_seq
from org.settings import OrgSettings

log = logging.getLogger(__name__)


async def ensure_root(
    sessionmaker: async_sessionmaker[AsyncSession], settings: OrgSettings
) -> None:
    async with sessionmaker() as session, session.begin():
        # Advisory-lock: несколько реплик org не создадут два корня одновременно.
        await session.execute(select(func.pg_advisory_xact_lock(0x0_D0_7F_10_01)))
        if await session.scalar(select(func.count()).select_from(Unit)):
            return
        unit_type = await session.scalar(
            select(UnitType).where(UnitType.code == settings.root_unit_type_code)
        )
        if unit_type is None:
            unit_type = UnitType(
                code=settings.root_unit_type_code,
                name=settings.root_unit_type_name,
                level=0,
                can_have_children=True,
            )
            session.add(unit_type)
            await session.flush()
        node_no = await session.scalar(select(unit_node_no_seq.next_value()))
        root = Unit(
            id=settings.root_unit_id,
            node_no=node_no,
            parent_id=None,
            unit_type_id=unit_type.id,
            name=settings.root_unit_name,
            path=str(node_no),
            sort_order=0,
            is_active=True,
        )
        session.add(root)
        await session.flush()
        audit.record(
            session,
            action="unit.create",
            entity_type="unit",
            entity_id=root.id,
            scope_unit_id=root.id,
            after=root.snapshot(),
            comment="bootstrap",
        )
        add_event(
            session,
            "unit.created",
            "unit",
            root.id,
            {
                "unit_id": root.id,
                "parent_id": None,
                "path": root.path,
                "name": root.name,
                "unit_type_id": unit_type.id,
                "short_name": None,
                "is_active": True,
                "version": root.version,
            },
        )
        log.info("Создано корневое подразделение %s (%s)", root.name, root.id)
