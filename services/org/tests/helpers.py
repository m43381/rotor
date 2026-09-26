"""Построение тестового дерева через API."""

import uuid
from dataclasses import dataclass

from httpx import AsyncClient

TYPES = [
    ("faculty", "Факультет", 1),
    ("course", "Курс", 2),
    ("group", "Учебная группа", 3),
]


@dataclass
class Tree:
    root: uuid.UUID
    types: dict[str, uuid.UUID]
    faculty1: uuid.UUID
    faculty2: uuid.UUID
    course11: uuid.UUID
    course12: uuid.UUID
    group111: uuid.UUID


async def create_types(admin: AsyncClient) -> dict[str, uuid.UUID]:
    result = {}
    for code, name, level in TYPES:
        r = await admin.post("/unit-types", json={"code": code, "name": name, "level": level})
        assert r.status_code == 201, r.text
        result[code] = uuid.UUID(r.json()["id"])
    return result


async def create_unit(
    client: AsyncClient, parent: uuid.UUID, type_id: uuid.UUID, name: str
) -> uuid.UUID:
    r = await client.post(
        "/units", json={"parent_id": str(parent), "unit_type_id": str(type_id), "name": name}
    )
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["id"])


async def build_tree(admin: AsyncClient, root: uuid.UUID) -> Tree:
    """Академия → Ф1 (Курс 1.1 → Группа 111; Курс 1.2), Ф2."""
    types = await create_types(admin)
    f1 = await create_unit(admin, root, types["faculty"], "Факультет 1")
    f2 = await create_unit(admin, root, types["faculty"], "Факультет 2")
    c11 = await create_unit(admin, f1, types["course"], "Курс 1.1")
    c12 = await create_unit(admin, f1, types["course"], "Курс 1.2")
    g111 = await create_unit(admin, c11, types["group"], "Группа 111")
    return Tree(root, types, f1, f2, c11, c12, g111)


async def get_unit(client: AsyncClient, unit_id: uuid.UUID) -> dict[str, object]:
    r = await client.get(f"/units/{unit_id}")
    assert r.status_code == 200, r.text
    data: dict[str, object] = r.json()
    return data
