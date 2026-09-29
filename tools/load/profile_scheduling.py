"""Профиль запросов scheduling внутри контейнера сервиса (ASGI в процессе, cProfile).

    docker compose -p dutyflow-load ... run --rm --no-deps -v ./tools:/srv/tools:ro \\
        -e PROFILE_USER=... -e PROFILE_PASSWORD=... -e PROFILE_PATHS=/day-plans/<id>/candidates \\
        scheduling python /srv/tools/load/profile_scheduling.py
"""

import asyncio
import cProfile
import io
import os
import pstats

import httpx

from scheduling.main import create_app
from scheduling.settings import SchedulingSettings


async def main() -> None:
    async with httpx.AsyncClient() as kc:
        r = await kc.post(
            "http://keycloak:8080/auth/realms/dutyflow/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "dutyflow-cli",
                "username": os.environ["PROFILE_USER"],
                "password": os.environ["PROFILE_PASSWORD"],
            },
        )
        r.raise_for_status()
        token = r.json()["access_token"]
    app = create_app(SchedulingSettings())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c,
    ):
        headers = {"Authorization": f"Bearer {token}"}
        paths = os.environ["PROFILE_PATHS"].split(",")
        for path in paths:  # прогрев
            (await c.get(path, headers=headers)).raise_for_status()
        profile = cProfile.Profile()
        profile.enable()
        for _ in range(5):
            for path in paths:
                await c.get(path, headers=headers)
        profile.disable()
    out = io.StringIO()
    pstats.Stats(profile, stream=out).sort_stats("cumulative").print_stats(35)
    print(out.getvalue())


asyncio.run(main())
