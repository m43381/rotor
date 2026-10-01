"""Учётные записи операторов демо-снимка (deploy/demo/snapshot/operators.json).

Базы Keycloak в снимке нет — в ней пароли конкретной инсталляции. Поэтому операторы хранятся
списком (логин, ФИО, роль, подразделение, заблокирован ли) и пересоздаются через API с паролем
DEMO_PASSWORD (по умолчанию demo-password-1).

    python operators.py export   # со стенда в snapshot/operators.json (`dutyflow.sh demo-snapshot`)
    python operators.py load     # недостающих — на стенд (контейнер demo-operators при `up`)
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from demo import DEMO_PASSWORD, Api, set_demo_passwords

# Экспорт пишет в каталог из DEMO_SNAPSHOT_DIR: каталог /demo в контейнере только для чтения
SNAPSHOT = (
    Path(os.environ.get("DEMO_SNAPSHOT_DIR") or Path(__file__).resolve().parent / "snapshot")
    / "operators.json"
)


async def all_operators(api: Api) -> list[dict]:
    items: list[dict] = []
    while True:
        page = await api.get("/api/auth-admin/operators", limit=200, offset=len(items))
        items += page["items"]
        if len(items) >= page["total"] or not page["items"]:
            return items


async def export(api: Api) -> None:
    ops = [
        {
            "username": o["username"],
            "last_name": o["last_name"],
            "first_name": o["first_name"],
            "role": o["role"],
            "unit_id": o["unit_id"],
            "enabled": o["enabled"],
        }
        for o in await all_operators(api)
        if o["username"] != "admin"  # создаётся при установке со своим паролем
    ]
    ops.sort(key=lambda o: o["username"])
    SNAPSHOT.write_text(json.dumps(ops, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Операторов в снимке: {len(ops)}")


async def load(api: Api) -> None:
    if not SNAPSHOT.exists():
        print("Снимка операторов нет — пропускаю")
        return
    wanted = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    have = {o["username"] for o in await all_operators(api)}
    units = {u["id"] for u in await api.get("/api/org/units", include_inactive="true")}
    new: list[str] = []
    blocked: list[str] = []
    for o in wanted:
        if o["username"] in have or o["unit_id"] not in units:
            continue
        body = {k: o[k] for k in ("username", "last_name", "first_name", "role", "unit_id")}
        uid = (await api.post("/api/auth-admin/operators", body))["id"]
        new.append(uid)
        if not o.get("enabled", True):
            blocked.append(uid)
    if new:
        await set_demo_passwords(
            api.http,
            new,
            os.environ.get("KEYCLOAK_ADMIN", ""),
            os.environ.get("KEYCLOAK_ADMIN_PASSWORD", ""),
        )
    for uid in blocked:
        await api.post(f"/api/auth-admin/operators/{uid}/block", {})
    print(f"Операторы демо-снимка: создано {len(new)} (пароль {DEMO_PASSWORD})")


async def wait_ready(api: Api) -> None:
    """Контейнер стартует вместе со стендом: ждём, пока поднимутся Keycloak и auth-admin."""
    login = {
        "grant_type": "password",
        "client_id": "dutyflow-cli",
        "username": "admin",
        "password": api.password,
    }
    for _ in range(90):
        try:
            health = await api.http.get("/api/auth-admin/health")
            token = await api.http.post(
                "/auth/realms/dutyflow/protocol/openid-connect/token", data=login
            )
            if health.status_code == 200 and token.status_code == 200:
                return
        except httpx.TransportError:  # шлюз ещё не принимает подключения
            pass
        await asyncio.sleep(5)
    raise SystemExit("Стенд не поднялся за 7 минут — операторы демо-снимка не созданы")


async def main(mode: str) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if mode == "load" and os.environ.get("DEMO_DATA", "false").lower() not in ("true", "1", "yes"):
        print("DEMO_DATA выключен — операторы демо-снимка не создаются")
        return 0
    api = Api(
        os.environ.get("DEMO_BASE_URL", "http://gateway"), os.environ["DUTYFLOW_ADMIN_PASSWORD"]
    )
    try:
        if mode == "load":
            await wait_ready(api)
            await load(api)
        else:
            await export(api)
    finally:
        await api.http.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "load")))
