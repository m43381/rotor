"""Тип PostgreSQL `ltree` для SQLAlchemy и операции над путями (ADR-0003)."""

from typing import Any

from sqlalchemy import Boolean, ColumnElement, SQLColumnExpression, cast, func, literal
from sqlalchemy.dialects.postgresql import base as postgresql_base
from sqlalchemy.types import UserDefinedType


class Ltree(UserDefinedType[str]):
    cache_ok = True

    def get_col_spec(self, **_: Any) -> str:
        return "LTREE"


class Lquery(UserDefinedType[str]):
    cache_ok = True

    def get_col_spec(self, **_: Any) -> str:
        return "LQUERY"


def is_descendant_or_self(path: SQLColumnExpression[str], ancestor: str) -> ColumnElement[bool]:
    """`path <@ ancestor` — узел в поддереве `ancestor`, включая его самого."""
    return path.op("<@", return_type=Boolean())(cast(literal(ancestor), Ltree()))


def matches(path: SQLColumnExpression[str], query: str) -> ColumnElement[bool]:
    """`path ~ lquery`."""
    return path.op("~", return_type=Boolean())(cast(literal(query), Lquery()))


def nlevel(path: SQLColumnExpression[str]) -> ColumnElement[int]:
    return func.nlevel(path)


# Чтобы рефлексия схемы (Alembic autogenerate, проверка миграций) узнавала колонки ltree.
postgresql_base.ischema_names["ltree"] = Ltree
