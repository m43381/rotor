"""Наполнение нагрузочного стенда через публичные API, как это делали бы операторы.

Организация — генератор экспериментального стенда фазы 5 (`tools.experiment.org`):
7 уровней, неравные ветви, люди в листьях, наряды у узлов уровней 0…4, допуски к нарядам
своей цепочки, освобождения. Шаги:

1. типы подразделений и дерево (org);
2. люди и освобождения — пакетным импортом (personnel, по 20 000 строк);
3. наряды с ролями (scheduling) и допуски — массовой выдачей (personnel);
4. графики на следующий месяц у всех владельцев нарядов, автораспределение сверху вниз
   с применением и публикацией — это «рабочий» месяц нагрузки, с назначениями и фактами
   для дашборда; пустые графики ещё на месяц вперёд — для замеров автораспределения;
5. 5 000 операторов через auth-admin; 300 из них получают постоянный пароль для входа.

Время каждого шага попадает в состояние и в отчёт.
"""

import asyncio
import datetime as dt
import random
import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

import httpx

from tools.experiment.org import PEOPLE_LEVEL, cleared_by_role, generate_org
from tools.gen.names import fio
from tools.load.common import (
    PASSWORD,
    Token,
    check,
    client,
    compose_cmd,
    env_values,
    keycloak_admin,
    run,
    save_state,
)

SEED = 20260929
IMPORT_CHUNK = 20_000
LEVEL_TYPES = ("Факультет", "Отделение", "Курс-блок", "Курс", "Взвод", "Группа")
# Где работают операторы и какие у них роли
OPERATOR_LEVELS = {1: 0.05, 2: 0.10, 3: 0.20, 4: 0.40, 5: 0.25}
OPERATOR_ROLES = {"unit_admin": 0.10, "operator": 0.70, "viewer": 0.20}
PROBES = 20


def next_month(today: dt.date) -> dt.date:
    return (today.replace(day=28) + dt.timedelta(days=5)).replace(day=1)


async def limited[T](items: Iterable[T], fn: Callable[[T], Awaitable[Any]], limit: int) -> None:
    sem = asyncio.Semaphore(limit)

    async def one(item: T) -> None:
        async with sem:
            await fn(item)

    await asyncio.gather(*(one(i) for i in items))


def stream_lag() -> int:
    """Непрочитанные события всех групп консьюмеров (redis-cli в контейнере Redis)."""
    raw = run(
        compose_cmd("exec", "-T", "redis", "redis-cli", "--scan", "--pattern", "events:*"),
        capture=True,
    )
    total = 0
    for stream in raw.split():
        out = run(
            compose_cmd("exec", "-T", "redis", "redis-cli", "XINFO", "GROUPS", stream), capture=True
        )
        lines = out.split()
        for i, word in enumerate(lines[:-1]):
            if word in ("lag", "pending") and lines[i + 1].lstrip("-").isdigit():
                total += int(lines[i + 1])
    return total


async def wait_events(what: str, limit_s: float = 4 * 3600) -> None:
    deadline = time.monotonic() + limit_s
    while (lag := await asyncio.to_thread(stream_lag)) > 0:
        if time.monotonic() > deadline:
            raise SystemExit(f"События не обработаны за {limit_s:.0f} с ({what}), осталось {lag}")
        await asyncio.sleep(3)


class Populator:
    def __init__(self, http: httpx.AsyncClient, env: dict[str, str]) -> None:
        self.http = http
        self.env = env
        self.admin = Token(http, "admin", env["DUTYFLOW_ADMIN_PASSWORD"])
        self.timings: dict[str, float] = {}
        self.counts: dict[str, int] = {}

    async def get(self, path: str, **params: Any) -> Any:
        return check(await self.http.get(path, params=params, headers=await self.admin.headers()))

    async def post(self, path: str, body: Any) -> Any:
        return check(await self.http.post(path, json=body, headers=await self.admin.headers()))

    def step(self, name: str, started: float) -> None:
        self.timings[name] = round(time.monotonic() - started, 1)
        print(f"  {name}: {self.timings[name]} с", flush=True)


async def populate(people: int, operators: int, active: int, resume: bool = False) -> None:
    env = env_values()
    month = next_month(dt.date.today())
    probe_month = next_month(month)
    rng = random.Random(SEED)
    org = generate_org(people, SEED, month)
    print(
        f"Организация: {len(org.units)} подразделений, {len(org.people)} человек, "
        f"{len(org.type_names)} нарядов, {len(org.roles)} ролей",
        flush=True,
    )
    async with client(timeout=900, connections=32) as http:
        p = Populator(http, env)

        if not resume:
            # --- 1. дерево ---------------------------------------------------------------------
            t = time.monotonic()
            units = await p.get("/api/org/units")
            if len(units) > 1:
                raise SystemExit("Стенд уже наполнен — `just load down`, затем `just load up`")
            root = units[0]
            types = await p.get("/api/org/unit-types")
            base = next(ut["level"] for ut in types if ut["id"] == root["unit_type_id"])
            type_ids = {}
            for level, name in enumerate(LEVEL_TYPES, start=1):
                existing = next((ut for ut in types if ut["code"] == f"load_l{level}"), None)
                type_ids[level] = (
                    existing
                    or await p.post(
                        "/api/org/unit-types",
                        {"code": f"load_l{level}", "name": name, "level": base + level},
                    )
                )["id"]
            ids: dict[int, str] = {0: root["id"]}
            for level in range(1, len(LEVEL_TYPES) + 1):

                async def create(i: int, level: int = level) -> None:
                    u = org.units[i]
                    assert u.parent is not None
                    ids[i] = (
                        await p.post(
                            "/api/org/units",
                            {
                                "parent_id": ids[u.parent],
                                "unit_type_id": type_ids[level],
                                "name": u.name,
                                "sort_order": i,
                            },
                        )
                    )["id"]

                await limited(org.at_level(level), create, 12)
            p.counts["units"] = len(org.units)
            p.step("подразделения", t)

            # --- 2. люди и освобождения ------------------------------------------------------
            t = time.monotonic()
            await wait_events("подразделения")
            template = await p.get("/api/personnel/imports/people/template")
            options = next(c["options"] for c in template["columns"] if c["key"] == "unit")
            label = {o.split(" / ")[-1]: o for o in options}
            rows = []
            for n, person in enumerate(org.people):
                full = fio(rng)
                rows.append(
                    {
                        "row": n + 2,
                        "values": {
                            "personal_no": f"L{n:06d}",
                            "last_name": full.last,
                            "first_name": full.first,
                            "middle_name": full.middle,
                            "unit": label[org.units[person.unit].name],
                        },
                    }
                )
            for i in range(0, len(rows), IMPORT_CHUNK):
                result = await p.post(
                    "/api/personnel/imports/people",
                    {"rows": rows[i : i + IMPORT_CHUNK], "dry_run": False},
                )
                print(f"    импорт людей {i + IMPORT_CHUNK}: {result['summary']}", flush=True)
            p.counts["people"] = len(rows)
            p.step("личный состав (импорт)", t)

            t = time.monotonic()
            person_ids: dict[int, str] = {}
            total = (await p.get("/api/personnel/people", limit=1))["total"]

            async def page(offset: int) -> None:
                data = await p.get("/api/personnel/people", limit=500, offset=offset)
                for item in data["items"]:
                    if item["personal_no"] and item["personal_no"].startswith("L"):
                        person_ids[int(item["personal_no"][1:])] = item["id"]

            await limited(range(0, total, 500), page, 8)
            reason = (await p.get("/api/personnel/exemption-reasons"))[0]["name"]
            ex_rows: list[dict[str, Any]] = []
            for n, person in enumerate(org.people):
                for a, b in person.exemptions:
                    values = {"personal_no": f"L{n:06d}", "reason": reason}
                    values |= {"date_from": a.isoformat(), "date_to": b.isoformat()}
                    ex_rows.append({"row": len(ex_rows) + 2, "values": values})
            for i in range(0, len(ex_rows), IMPORT_CHUNK):
                await p.post(
                    "/api/personnel/imports/exemptions",
                    {"rows": ex_rows[i : i + IMPORT_CHUNK], "dry_run": False},
                )
            p.counts["exemptions"] = len(ex_rows)
            p.step("освобождения (импорт)", t)

            # --- 3. наряды и допуски -------------------------------------------------------------
            t = time.monotonic()
            role_ids: dict[int, str] = {}
            by_type: dict[int, list[int]] = {}
            for r, role in enumerate(org.roles):
                by_type.setdefault(role.type_index, []).append(r)

            async def duty_type(type_index: int) -> None:
                members = by_type[type_index]
                first = org.roles[members[0]]
                created = await p.post(
                    "/api/scheduling/duty-types",
                    {
                        "name": org.type_names[type_index],
                        "owner_unit_id": ids[first.owner],
                        "start_time": first.start[:5],
                        "duration_minutes": first.duration,
                        "rest_hours": first.rest,
                        "load_weight": first.weight,
                        "roles": [
                            {
                                "name": org.roles[r].name,
                                "headcount": org.roles[r].headcount,
                                "sort_order": k,
                            }
                            for k, r in enumerate(members)
                        ],
                    },
                )
                ordered = sorted(created["roles"], key=lambda x: x["sort_order"])
                for r, out in zip(members, ordered, strict=True):
                    role_ids[r] = out["id"]

            await limited(sorted(by_type), duty_type, 8)
            p.counts["duty_types"] = len(by_type)
            p.counts["duty_roles"] = len(role_ids)
            p.step("наряды", t)

            t = time.monotonic()
            await wait_events("наряды")
            granted = 0
            batches = [
                (role_ids[r], [person_ids[x] for x in cleared[i : i + 1000]])
                for r, cleared in enumerate(cleared_by_role(org))
                for i in range(0, len(cleared), 1000)
            ]

            async def grant(batch: tuple[str, list[str]]) -> None:
                nonlocal granted
                role, persons = batch
                result = await p.post(
                    "/api/personnel/clearances/bulk",
                    {"person_ids": persons, "duty_role_ids": [role]},
                )
                granted += result["done"]

            await limited(batches, grant, 6)
            p.counts["clearances"] = granted
            p.step("допуски", t)

        else:
            # Продолжение после сбоя на шагах 4–5: подразделения, люди, наряды и допуски уже
            # есть. Имена узлов генератора уникальны; генератор ФИО прокручивается так же.
            by_name = {u["name"]: u["id"] for u in await p.get("/api/org/units")}
            ids = {i: by_name[u.name] for i, u in enumerate(org.units) if i}
            ids[0] = next(u["id"] for u in await p.get("/api/org/units") if u["parent_id"] is None)
            for _ in org.people:
                fio(rng)
            p.counts |= {
                "units": len(org.units),
                "people": len(org.people),
                "exemptions": sum(len(x.exemptions) for x in org.people),
                "duty_types": len(org.type_names),
                "duty_roles": len(org.roles),
                "clearances": sum(len(c) for c in cleared_by_role(org)),
            }

        # --- 4. графики и автораспределение ---------------------------------------------------
        t = time.monotonic()
        await wait_events("допуски")
        owners = sorted({role.owner for role in org.roles}, key=lambda u: (org.units[u].level, u))
        schedules: dict[int, str] = {}

        async def schedule(u: int) -> None:
            created = await p.post(
                "/api/scheduling/schedules", {"unit_id": ids[u], "month": month.isoformat()}
            )
            schedules[u] = created["id"]

        await limited(owners, schedule, 8)
        courses = [u for u in owners if org.units[u].level == PEOPLE_LEVEL]
        probe_units = rng.sample(courses, min(PROBES, len(courses)))
        probes: list[str] = []

        async def probe(u: int) -> None:
            created = await p.post(
                "/api/scheduling/schedules", {"unit_id": ids[u], "month": probe_month.isoformat()}
            )
            probes.append(created["id"])

        await limited(probe_units, probe, 8)
        p.counts["schedules"] = len(schedules) + len(probes)
        p.step("графики", t)

        t = time.monotonic()
        allocations: list[dict[str, Any]] = []

        async def allocate(u: int) -> None:
            started = time.monotonic()
            run_ = await p.post(f"/api/scheduling/schedules/{schedules[u]}/allocate", {})
            while run_["status"] in ("queued", "running"):
                await asyncio.sleep(1)
                run_ = await p.get(f"/api/scheduling/allocation-runs/{run_['id']}")
            computed = time.monotonic() - started
            if run_["status"] == "preview_ready":
                applied = await p.post(f"/api/scheduling/allocation-runs/{run_['id']}/apply", {})
                status = applied["status"]
            else:
                status = run_["status"]
            allocations.append(
                {
                    "level": org.units[u].level,
                    "people": len(org.subtree_people[u]),
                    "places": run_["places"],
                    "filled": run_["filled"],
                    "method": run_["method"],
                    "seconds": round(computed, 2),
                    "status": status,
                    "error": run_.get("error"),
                }
            )

        for level in range(PEOPLE_LEVEL + 1):
            await limited([u for u in owners if org.units[u].level == level], allocate, 3)
            print(f"    уровень {level}: распределено", flush=True)
        p.step("автораспределение месяца", t)

        t = time.monotonic()

        async def publish(u: int) -> None:
            s = await p.get(f"/api/scheduling/schedules/{schedules[u]}")
            await p.post(
                f"/api/scheduling/schedules/{schedules[u]}/publish", {"version": s["version"]}
            )

        await limited(owners, publish, 8)
        p.step("публикация", t)

        # --- 5. операторы ---------------------------------------------------------------------
        t = time.monotonic()
        by_level = {lv: org.at_level(lv) for lv in OPERATOR_LEVELS}
        accounts: list[dict[str, Any]] = []
        for n in range(operators):
            level = rng.choices(list(OPERATOR_LEVELS), weights=list(OPERATOR_LEVELS.values()))[0]
            op_role = rng.choices(list(OPERATOR_ROLES), weights=list(OPERATOR_ROLES.values()))[0]
            full = fio(rng)
            accounts.append(
                {
                    "username": f"load{n:04d}",
                    "last_name": full.last,
                    "first_name": full.first,
                    "role": op_role,
                    "node": rng.choice(by_level[level]),
                }
            )

        async def operator(acc: dict[str, Any]) -> None:
            body = {k: acc[k] for k in ("username", "last_name", "first_name", "role")}
            created = await p.post(
                "/api/auth-admin/operators", {**body, "unit_id": ids[acc["node"]]}
            )
            acc["id"] = created["id"]

        await limited(accounts, operator, 8)
        p.counts["operators"] = len(accounts)
        p.step("операторы", t)

        t = time.monotonic()
        with_schedule = [a for a in accounts if a["node"] in schedules]
        editors = [a for a in with_schedule if a["role"] != "viewer"]
        viewers = [a for a in with_schedule if a["role"] == "viewer"]
        n_view = min(len(viewers), round(active * 0.15))
        chosen = rng.sample(editors, min(len(editors), active - n_view)) + rng.sample(
            viewers, n_view
        )
        kc: dict[str, str] = {}
        kc_at = 0.0

        async def activate(acc: dict[str, Any]) -> None:
            nonlocal kc, kc_at
            if time.monotonic() - kc_at > 30:  # токен admin-cli живёт минуту
                kc, kc_at = await keycloak_admin(http, env), time.monotonic()
            base = f"/auth/admin/realms/dutyflow/users/{acc['id']}"
            check(
                await http.put(
                    f"{base}/reset-password",
                    headers=kc,
                    json={"type": "password", "value": PASSWORD, "temporary": False},
                )
            )
            check(await http.put(base, headers=kc, json={"requiredActions": []}))

        await limited(chosen, activate, 1)
        p.step("пароли активных операторов", t)

    level_of = {ids[u]: org.units[u].level for u in ids}
    save_state(
        {
            "month": month.isoformat(),
            "probe_month": probe_month.isoformat(),
            "counts": p.counts,
            "timings": p.timings,
            "allocations": allocations,
            "probes": probes,
            "schedules": {ids[u]: s for u, s in schedules.items()},
            "active": [
                {
                    "username": a["username"],
                    "role": a["role"],
                    "unit_id": ids[a["node"]],
                    "level": level_of[ids[a["node"]]],
                }
                for a in chosen
            ],
        }
    )
    print(f"Готово: {p.counts}")


def main(people: int, operators: int, active: int, resume: bool = False) -> None:
    asyncio.run(populate(people, operators, active, resume))
