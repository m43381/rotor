"""Общее для нагрузочного прогона: отдельный compose-проект, адрес, токены, состояние."""

import asyncio
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / "deploy" / ".env.load"
STATE_FILE = ROOT / "tools" / "load" / ".state" / "state.json"
PROJECT = "dutyflow-load"
HTTPS_PORT = 9443
BASE_URL = f"https://localhost:{HTTPS_PORT}"
# Пароль рабочих учёток нагрузочного стенда (отдельные тома, данные синтетические)
PASSWORD = "loadpass2026"  # noqa: S105
CA = ROOT / "deploy" / "certs" / "ca.crt"


def env_values(path: Path = ENV_FILE) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def compose_cmd(*args: str) -> list[str]:
    return [
        "docker",
        "compose",
        "-p",
        PROJECT,
        "-f",
        str(ROOT / "deploy" / "docker-compose.yml"),
        "--env-file",
        str(ENV_FILE),
        *args,
    ]


def run(cmd: list[str], *, capture: bool = False) -> str:
    # Команды — только docker с фиксированными аргументами
    result = subprocess.run(cmd, check=True, capture_output=capture, text=True, encoding="utf-8")  # noqa: S603
    return result.stdout if capture else ""


def client(timeout: float = 60.0, connections: int = 20) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BASE_URL,
        verify=str(CA),
        timeout=timeout,
        limits=httpx.Limits(max_connections=connections, max_keepalive_connections=connections),
    )


class Token:
    """Токен оператора (client `dutyflow-cli`, password grant) с обновлением до истечения."""

    def __init__(self, http: httpx.AsyncClient, username: str, password: str) -> None:
        self.http, self.username, self.password = http, username, password
        self.access = ""
        self.refresh = ""
        self.expires = 0.0
        self._lock = asyncio.Lock()

    async def _grant(self, data: dict[str, str]) -> None:
        r = await self.http.post(
            "/auth/realms/dutyflow/protocol/openid-connect/token",
            data={"client_id": "dutyflow-cli", **data},
        )
        r.raise_for_status()
        body = r.json()
        self.access, self.refresh = body["access_token"], body.get("refresh_token", "")
        self.expires = time.monotonic() + float(body["expires_in"])

    async def headers(self) -> dict[str, str]:
        async with self._lock:
            if time.monotonic() > self.expires - 30:
                if self.refresh:
                    try:
                        await self._grant(
                            {"grant_type": "refresh_token", "refresh_token": self.refresh}
                        )
                    except httpx.HTTPStatusError:
                        self.refresh = ""
                if not self.refresh or time.monotonic() > self.expires - 30:
                    await self._grant(
                        {
                            "grant_type": "password",
                            "username": self.username,
                            "password": self.password,
                        }
                    )
        return {"Authorization": f"Bearer {self.access}"}


async def keycloak_admin(http: httpx.AsyncClient, env: dict[str, str]) -> dict[str, str]:
    r = await http.post(
        "/auth/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": env["KEYCLOAK_ADMIN"],
            "password": env["KEYCLOAK_ADMIN_PASSWORD"],
        },
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def check(r: httpx.Response) -> Any:
    if r.is_error:
        raise SystemExit(f"{r.request.method} {r.request.url} → {r.status_code}: {r.text[:500]}")
    return r.json() if r.content else None


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        raise SystemExit("Нет состояния наполнения — сначала `just load populate`")
    return dict(json.loads(STATE_FILE.read_text(encoding="utf-8")))
