"""Фоновые расчёты: очередь arq на настоящем Redis (testcontainers), воркер в процессе."""

from collections.abc import AsyncIterator, Iterator

import pytest
from arq.connections import RedisSettings
from arq.worker import Worker
from httpx import ASGITransport, AsyncClient
from testcontainers.community.redis import RedisContainer

from allocation.main import create_app
from allocation.settings import AllocationSettings
from allocation.synthetic import generate_snapshot
from allocation.worker import solve_job

TOKEN = "test-internal"
HEADERS = {"X-Internal-Token": TOKEN}


@pytest.fixture(scope="module")
def redis_url() -> Iterator[str]:
    with RedisContainer("redis:7-alpine") as r:
        yield f"redis://{r.get_container_host_ip()}:{r.get_exposed_port(6379)}/0"


@pytest.fixture
async def client(redis_url: str) -> AsyncIterator[AsyncClient]:
    app = create_app(AllocationSettings(internal_token=TOKEN, redis_url=redis_url))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def run_worker(redis_url: str) -> None:
    worker = Worker(
        functions=[solve_job], redis_settings=RedisSettings.from_dsn(redis_url), burst=True
    )
    try:
        await worker.main()
    finally:
        await worker.close()


async def test_job_lifecycle(client: AsyncClient, redis_url: str) -> None:
    body = {
        "snapshot": generate_snapshot(people=60, seed=2),
        "config": {"method": "local_search", "ls_iterations": 500},
        "seed": 4,
    }
    r = await client.post("/internal/jobs", json=body, headers=HEADERS)
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    assert (await client.get(f"/internal/jobs/{job_id}", headers=HEADERS)).json()[
        "status"
    ] == "queued"

    await run_worker(redis_url)
    r = await client.get(f"/internal/jobs/{job_id}", headers=HEADERS)
    body_out = r.json()
    assert body_out["status"] == "done"
    assert body_out["result"]["method"] == "local_search"
    assert body_out["result"]["metrics"]["filled"] > 0


async def test_job_errors(client: AsyncClient, redis_url: str) -> None:
    bad = {"snapshot": generate_snapshot(people=10), "config": {"method": "другой"}}
    assert (await client.post("/internal/jobs", json=bad, headers=HEADERS)).status_code == 422
    assert (await client.get("/internal/jobs/нет-такой", headers=HEADERS)).status_code == 404
    # Сломанный снимок падает в воркере — задача завершается со статусом failed
    r = await client.post(
        "/internal/jobs", json={"snapshot": {"snapshot_version": 9}}, headers=HEADERS
    )
    job_id = r.json()["job_id"]
    await run_worker(redis_url)
    r = await client.get(f"/internal/jobs/{job_id}", headers=HEADERS)
    assert r.json()["status"] == "failed"
    assert "версия" in r.json()["error"]
