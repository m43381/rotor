"""Подключение к БД сервиса, базовый класс моделей и общие колонки."""

import uuid
from collections.abc import AsyncIterator, Iterable
from datetime import datetime
from typing import Any, cast

from fastapi import Request
from sqlalchemy import ColumnElement, DateTime, Integer, MetaData, any_, bindparam, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from dutyflow_common.ids import uuid7

# Предсказуемые имена ограничений — чтобы Alembic autogenerate давал стабильные миграции.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Базовый класс моделей. У каждого сервиса своя БД, но один и тот же базовый класс
    допустим: сервис импортирует только свои модели и общие таблицы."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UuidPkMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VersionedMixin:
    """Оптимистичная блокировка: SQLAlchemy добавляет `WHERE version = :old` к UPDATE."""

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class Database:
    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.engine: AsyncEngine = create_async_engine(url, echo=echo, pool_pre_ping=True)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI-зависимость: сессия БД сервиса на время запроса."""
    db: Database = request.app.state.db
    async with db.sessionmaker() as session:
        yield session


def in_array(column: Any, values: Iterable[Any]) -> ColumnElement[bool]:
    """`column = ANY(:array)` — один параметр вместо развёрнутого IN.

    Для списков в десятки тысяч id (снимки на 50 тыс. человек): обычный `in_()` передаёт
    каждый элемент отдельным параметром и упирается в лимит asyncpg (32 767).
    """
    return cast(
        ColumnElement[bool],
        column == any_(bindparam(None, list(values), type_=ARRAY(column.type))),
    )
