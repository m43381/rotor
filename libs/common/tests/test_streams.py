"""Обрезка потоков не удаляет непрочитанное и неподтверждённое (фаза 7d)."""

from collections.abc import AsyncIterator, Iterator

import pytest
from redis.asyncio import Redis
from testcontainers.community.redis import RedisContainer

from dutyflow_common.streams import trim_streams


@pytest.fixture(scope="module")
def redis_url() -> Iterator[str]:
    with RedisContainer("redis:7-alpine") as r:
        yield f"redis://{r.get_container_host_ip()}:{r.get_exposed_port(6379)}/0"


@pytest.fixture
async def redis(redis_url: str) -> AsyncIterator[Redis]:
    client = Redis.from_url(redis_url)
    await client.flushall()
    yield client
    await client.aclose()


async def test_keeps_unread_and_pending(redis: Redis) -> None:
    stream = "events:test"
    ids = [await redis.xadd(stream, {"n": str(i)}) for i in range(10)]
    await redis.xgroup_create(stream, "fast", id="0")
    await redis.xgroup_create(stream, "slow", id="0")
    # fast прочитал и подтвердил всё; slow прочитал 6, подтвердил 4 (5-я и 6-я — pending)
    for msg_id in [
        i for _, msgs in await redis.xreadgroup("fast", "c", {stream: ">"}) for i, _ in msgs
    ]:
        await redis.xack(stream, "fast", msg_id)
    got = await redis.xreadgroup("slow", "c", {stream: ">"}, count=6)
    for msg_id, _ in got[0][1][:4]:
        await redis.xack(stream, "slow", msg_id)

    # Срок хранения истории — ноль: держит только чтение групп
    assert await trim_streams(redis, retention_ms=0) == 4
    left = [i for i, _ in await redis.xrange(stream)]
    assert left == ids[4:]

    # slow дочитал и подтвердил — поток можно обрезать до конца
    for msg_id, _ in got[0][1][4:]:
        await redis.xack(stream, "slow", msg_id)
    for _, msgs in await redis.xreadgroup("slow", "c", {stream: ">"}):
        for msg_id, _ in msgs:
            await redis.xack(stream, "slow", msg_id)
    await trim_streams(redis, retention_ms=0)
    assert await redis.xlen(stream) == 0


async def test_retention_keeps_recent_history(redis: Redis) -> None:
    stream = "events:recent"
    for i in range(5):
        await redis.xadd(stream, {"n": str(i)})
    await redis.xgroup_create(stream, "g", id="$")  # группа начинает с конца — всё «прочитано»
    assert await trim_streams(redis) == 0  # история моложе трёх суток сохраняется
    assert await redis.xlen(stream) == 5
