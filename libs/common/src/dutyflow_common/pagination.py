"""Постраничная выдача списков."""

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel


class PageParams(BaseModel):
    limit: int = 50
    offset: int = 0


def page_params(
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
