"""Проверка, используется ли звание, перед удалением (ADR-0022).

Звание принадлежит org, а ссылаются на него чужие данные: люди (personnel), минимальное
звание ролей нарядов и лимиты по званию (scheduling). org спрашивает владельцев через их
внутренний API — единственное место, где org обращается к нижестоящим сервисам.
"""

import uuid
from collections.abc import Awaitable, Callable

from dutyflow_common.internal import InternalClient
from org.settings import OrgSettings

# Сколько раз звание используется: {"people": 3, "duty_roles": 1, "duty_limits": 0}
type RankUsage = Callable[[uuid.UUID, int], Awaitable[dict[str, int]]]


def http_rank_usage(settings: OrgSettings) -> RankUsage:
    async def usage(rank_id: uuid.UUID, order: int) -> dict[str, int]:
        body = {"rank_id": str(rank_id), "order": order}
        result: dict[str, int] = {}
        for url in (settings.personnel_url, settings.scheduling_url):
            client = InternalClient(url, settings.internal_token, retries=2)
            try:
                result.update(await client.post("/internal/ranks/usage", body))
            finally:
                await client.aclose()
        return result

    return usage
