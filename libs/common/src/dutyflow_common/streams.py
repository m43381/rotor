"""Обрезка потоков событий без потери непрочитанного (фаза 7d, ADR-0004).

Раньше релей добавлял события с `MAXLEN ~100000`. Если консьюмер отставал больше чем на
100 тыс. событий (массовая выдача допусков, импорт), Redis удалял ещё не прочитанные
записи, консьюмер получал пустые сообщения и пропускал их — проекции расходились.

Теперь поток обрезается отдельно и только по `MINID`: удаляются записи, которые
одновременно
- старше срока хранения истории (новая группа консьюмеров читает её с начала), и
- уже подтверждены всеми группами (раньше самой старой неподтверждённой записи и
  не дальше последней выданной).
"""

import time
from typing import Any

from redis.asyncio import Redis

RETENTION_MS = 3 * 24 * 3600 * 1000  # история потока — трое суток


def _id(value: bytes | str) -> tuple[int, int]:
    text = value.decode() if isinstance(value, bytes) else value
    ms, _, seq = text.partition("-")
    return int(ms), int(seq or 0)


async def safe_min_id(
    redis: Redis, stream: str, retention_ms: int = RETENTION_MS
) -> tuple[int, int]:
    """Граница обрезки: всё строго раньше неё можно удалить."""
    bound = (int(time.time() * 1000) - retention_ms, 0)
    groups: list[dict[str, Any]] = await redis.xinfo_groups(stream)
    for group in groups:
        name = group["name"]
        # Выданное, но не подтверждённое, нужно консьюмеру после сбоя
        if int(group["pending"]):
            summary = await redis.xpending(stream, name)
            bound = min(bound, _id(summary["min"]))
        else:
            # Следующая за последней выданной — первая непрочитанная
            last = _id(group["last-delivered-id"])
            bound = min(bound, (last[0], last[1] + 1))
    return bound


async def trim_streams(redis: Redis, retention_ms: int = RETENTION_MS) -> int:
    """Обрезает все `events:*` до безопасной границы. Возвращает число удалённых записей."""
    removed = 0
    async for key in redis.scan_iter(match="events:*", _type="STREAM"):
        stream = key.decode() if isinstance(key, bytes) else key
        ms, seq = await safe_min_id(redis, stream, retention_ms)
        if ms > 0:
            removed += int(await redis.xtrim(stream, minid=f"{ms}-{seq}", approximate=False))
    return removed
