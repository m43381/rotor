"""Люди из personnel для проверок назначения: batch-запрос `POST /internal/people/batch`.

scheduling не хранит копию личного состава (`docs/architecture.md` §3.3): данные берутся
у владельца одним запросом на операцию. В тестах загрузчик подменяется.
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any, Protocol

from dutyflow_common.internal import InternalClient
from scheduling.checks import PersonInfo
from scheduling.settings import SchedulingSettings


class PeopleLoader(Protocol):
    async def __call__(
        self,
        *,
        date_from: dt.date,
        date_to: dt.date,
        unit_ids: Sequence[uuid.UUID] = (),
        person_ids: Sequence[uuid.UUID] = (),
    ) -> list[PersonInfo]: ...


def _date(value: Any) -> dt.date | None:
    return dt.date.fromisoformat(value) if value else None


def parse_person(item: dict[str, Any]) -> PersonInfo:
    return PersonInfo(
        id=uuid.UUID(item["id"]),
        unit_id=uuid.UUID(item["unit_id"]),
        is_active=bool(item.get("is_active", True)),
        rank_id=uuid.UUID(item["rank_id"]) if item.get("rank_id") else None,
        position_id=uuid.UUID(item["position_id"]) if item.get("position_id") else None,
        last_name=item.get("last_name") or "",
        first_name=item.get("first_name") or "",
        middle_name=item.get("middle_name"),
        rank_name=item.get("rank_name"),
        clearances=tuple(
            (uuid.UUID(role), _date(start), _date(end)) for role, start, end in item["clearances"]
        ),
        exemptions=tuple(
            (dt.date.fromisoformat(start), dt.date.fromisoformat(end))
            for start, end in item["exemptions"]
        ),
    )


def http_people_loader(settings: SchedulingSettings) -> PeopleLoader:
    async def load(
        *,
        date_from: dt.date,
        date_to: dt.date,
        unit_ids: Sequence[uuid.UUID] = (),
        person_ids: Sequence[uuid.UUID] = (),
    ) -> list[PersonInfo]:
        client = InternalClient(settings.personnel_url, settings.internal_token, timeout=30.0)
        try:
            data = await client.post(
                "/internal/people/batch",
                {
                    "unit_ids": [str(u) for u in unit_ids],
                    "person_ids": [str(p) for p in person_ids],
                    "date_from": str(date_from),
                    "date_to": str(date_to),
                    "include_names": True,
                },
            )
        finally:
            await client.aclose()
        return [parse_person(item) for item in data]

    return load
