"""Удаление только неиспользуемых записей (ADR-0022, ADR-0023).

Запись принадлежит одному сервису, а ссылаются на неё данные других. Перед удалением владелец
спрашивает у каждого из них `POST /internal/usage/{kind}` — сколько ссылок на запись в его БД
(`{"people": 2, "duty_roles": 0}`). Сервис отвечает только по тем видам, о которых знает,
на остальные — пустым словарём. Если хоть один счётчик не ноль, удаление отклоняется
с перечнем, где запись используется; если сервис не ответил — 503, запись остаётся.
"""

import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from dutyflow_common.errors import ConflictError
from dutyflow_common.internal import InternalClient

# Вид записи и тело запроса → счётчики ссылок по всем опрошенным сервисам
type UsageCheck = Callable[[str, dict[str, Any]], Awaitable[dict[str, int]]]


class UsageIn(BaseModel):
    """Тело `POST /internal/usage/{kind}`. `order` — для званий (минимальное звание роли
    хранится числом старшинства), `code` — для характеристик (требования ролей ссылаются
    на код)."""

    id: uuid.UUID
    order: int | None = None
    code: str | None = None


# Подписи счётчиков в сообщении об отказе: ключи одинаковы во всех сервисах
LABELS: dict[str, str] = {
    "people": "людей (включая архивных)",
    "person_values": "значений у людей",
    "exemptions": "освобождений",
    "units": "подразделений этого типа",
    "child_units": "дочерних подразделений (включая расформированные)",
    "duty_types": "типов нарядов этого подразделения",
    "duty_roles": "ролей нарядов (требования или закрепление)",
    "duty_limits": "лимитов нарядов",
    "schedules": "графиков",
    "day_plans": "ячеек графиков",
    "published_cells": "ячеек в опубликованных и архивных графиках",
    "assignments": "назначений в наряды",
    "operators": "операторов",
}


def http_usage(urls: Sequence[str], token: str) -> UsageCheck:
    async def check(kind: str, body: dict[str, Any]) -> dict[str, int]:
        result: dict[str, int] = {}
        for url in urls:
            client = InternalClient(url, token, retries=2)
            try:
                for key, count in (await client.post(f"/internal/usage/{kind}", body)).items():
                    result[key] = result.get(key, 0) + int(count)
            finally:
                await client.aclose()
        return result

    return check


def ensure_unused(
    what: str, usage: Mapping[str, int], hint: str = "Её можно только выключить."
) -> None:
    """ConflictError с перечнем, где используется запись `what` («Звание «Майор»»)."""
    used = [f"{LABELS.get(key, key)}: {n}" for key, n in usage.items() if n]
    if used:
        raise ConflictError(f"{what} используется — {'; '.join(used)}. {hint}".strip())
