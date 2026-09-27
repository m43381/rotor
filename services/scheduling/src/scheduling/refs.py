"""Справочники personnel, на которые ссылаются требования ролей: должности и характеристики.

Владелец — personnel; scheduling их не хранит, а проверяет ссылки при записи роли через
внутренний API владельца (`docs/data-model.md` §1, «Ссылки между сервисами»).
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from dutyflow_common.internal import InternalClient
from scheduling.settings import SchedulingSettings


@dataclass(frozen=True, slots=True)
class AttributeDef:
    code: str
    name: str
    value_type: str
    enum_options: list[str] | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class PersonnelRefs:
    # id должности → действует ли она
    positions: dict[uuid.UUID, bool] = field(default_factory=dict)
    attributes: dict[str, AttributeDef] = field(default_factory=dict)


type RefsLoader = Callable[[], Awaitable[PersonnelRefs]]


def http_refs_loader(settings: SchedulingSettings) -> RefsLoader:
    async def load() -> PersonnelRefs:
        client = InternalClient(settings.personnel_url, settings.internal_token, retries=2)
        try:
            data = await client.post("/internal/references", {})
        finally:
            await client.aclose()
        return PersonnelRefs(
            positions={uuid.UUID(p["id"]): bool(p["is_active"]) for p in data["positions"]},
            attributes={
                a["code"]: AttributeDef(
                    a["code"], a["name"], a["value_type"], a.get("enum_options"), a["is_active"]
                )
                for a in data["attributes"]
            },
        )

    return load
