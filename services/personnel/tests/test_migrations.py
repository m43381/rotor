"""Миграция доработана вручную — проверяем, что она совпадает с моделями."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from personnel.models import Base, include_object
from personnel.settings import PersonnelSettings


async def test_models_match_migrations(settings: PersonnelSettings, migrated: str) -> None:
    def diff(conn: Connection) -> list[object]:
        ctx = MigrationContext.configure(
            conn, opts={"compare_type": True, "include_object": include_object}
        )
        return list(compare_metadata(ctx, Base.metadata))

    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        changes = await conn.run_sync(diff)
    await engine.dispose()
    assert changes == []
