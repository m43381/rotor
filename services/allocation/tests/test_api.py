"""HTTP-обёртка движка: внутренний токен, решение, ошибки входа."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from allocation.main import create_app
from allocation.settings import AllocationSettings
from allocation.synthetic import generate_snapshot

TOKEN = "test-internal"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(AllocationSettings(internal_token=TOKEN))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_solve(client: AsyncClient) -> None:
    body = {
        "snapshot": generate_snapshot(people=50, seed=4),
        "config": {"kind": "people", "method": "local_search", "ls_iterations": 1000},
        "seed": 3,
    }
    assert (await client.post("/internal/solve", json=body)).status_code == 401
    r = await client.post("/internal/solve", json=body, headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 200, r.text
    sol = r.json()
    assert sol["solver"] == "greedy-mrv"
    assert sol["seed"] == 3
    assert sol["config"]["half_life_days"] == 30  # из default.yaml
    assert sol["metrics"]["filled"] > 0


async def test_bad_input(client: AsyncClient) -> None:
    headers = {"X-Internal-Token": TOKEN}
    r = await client.post(
        "/internal/solve", json={"snapshot": {"snapshot_version": 2}}, headers=headers
    )
    assert r.status_code == 422
    r = await client.post(
        "/internal/solve",
        json={"snapshot": generate_snapshot(people=10), "config": {"kind": "другое"}},
        headers=headers,
    )
    assert r.status_code == 422
    assert "настройки" in r.json()["message"]
    r = await client.get("/internal/config/defaults", headers=headers)
    assert r.json()["people_weights"]["recency"] == 2.0
