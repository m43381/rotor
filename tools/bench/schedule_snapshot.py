"""Бенчмарк графика подразделения (фаза 3): таблица месяца и сборка снимка задачи.

Замеряется настоящий код scheduling (FastAPI в процессе, httpx ASGITransport, PostgreSQL 16
в контейнере). Подразделение — факультет синтетического дерева; у него 20 нарядов × 3 роли
(≈60 строк × 31 день), графики за месяц и три предыдущих, ячейки заполнены людьми.
Людей поддерева отдаёт подставной загрузчик (личный состав замерен отдельно в
`docs/benchmarks/people-snapshot.md`), поэтому здесь — только сторона scheduling.

    just bench-schedule        # → docs/benchmarks/schedule.md
"""

import asyncio
import datetime as dt
import os
import platform
import random
import statistics
import sys
import time
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import asyncpg
import httpx
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.bench.hierarchy import generate_tree  # noqa: E402

OUT = ROOT / "docs" / "benchmarks" / "schedule.md"
UNITS = 2_000
TYPES, ROLES_PER_TYPE = 20, 3
PEOPLE = (5_000, 50_000)
RUNS = 10
SEED = 20260927
INTERNAL = "bench-token"
MONTH = dt.date(2026, 11, 1)
HISTORY_MONTHS = 3


def months_back(n: int) -> list[dt.date]:
    result, m = [], MONTH
    for _ in range(n + 1):
        result.append(m)
        m = (m - dt.timedelta(days=1)).replace(day=1)
    return list(reversed(result))


async def timed(client: httpx.AsyncClient, url: str, **kw: Any) -> tuple[float, int, Any]:
    await client.get(url, **kw)  # прогрев
    times, size, body = [], 0, None
    for _ in range(RUNS):
        t0 = time.perf_counter()
        r = await client.get(url, **kw)
        times.append((time.perf_counter() - t0) * 1000)
        r.raise_for_status()
        size, body = len(r.content), r
    return statistics.median(times), size, body


async def bench(url: str) -> tuple[list[dict[str, Any]], str]:
    sys.path.insert(0, str(ROOT / "services" / "scheduling" / "src"))
    from asgi_lifespan import LifespanManager

    from dutyflow_common.testing import TestIssuer
    from scheduling.checks import PersonInfo
    from scheduling.main import create_app
    from scheduling.refs import PersonnelRefs
    from scheduling.settings import SchedulingSettings

    rng = random.Random(SEED)
    tree = generate_tree(UNITS, rng)
    unit_ids = [uuid.uuid5(uuid.NAMESPACE_OID, f"unit-{i}") for i in range(len(tree.parent))]
    faculty = max(
        (i for i, d in enumerate(tree.depth) if d == 1),
        key=lambda i: sum(p.startswith(tree.path[i] + ".") for p in tree.path),
    )
    subtree = [
        i
        for i, p in enumerate(tree.path)
        if p == tree.path[faculty] or p.startswith(tree.path[faculty] + ".")
    ]
    people: list[PersonInfo] = []

    async def load_people(
        *,
        date_from: Any,
        date_to: Any,
        unit_ids: Sequence[Any] = (),
        person_ids: Sequence[Any] = (),
        duty_role_ids: Sequence[Any] = (),
    ) -> list[PersonInfo]:
        return people

    async def load_refs() -> PersonnelRefs:
        return PersonnelRefs()

    raw = url.replace("+asyncpg", "")
    conn = await asyncpg.connect(raw)
    await conn.executemany(
        "INSERT INTO unit_projection (unit_id, parent_id, path, name, is_active, source_version)"
        " VALUES ($1, $2, $3::ltree, $4, true, 1)",
        [
            (unit_ids[i], unit_ids[p] if p >= 0 else None, tree.path[i], f"Подразделение {i}")
            for i, p in enumerate(tree.parent)
        ],
    )
    await conn.close()

    settings = SchedulingSettings(database_url=url, internal_token=INTERNAL, log_level="WARNING")
    issuer = TestIssuer(settings)
    app = create_app(
        settings, token_verifier=issuer.verifier, refs_loader=load_refs, people_loader=load_people
    )
    rows: list[dict[str, Any]] = []
    async with LifespanManager(app):
        token = issuer.token(unit_id=unit_ids[0], roles=["superadmin"])
        auth = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://bench",
            timeout=300,
            headers=auth,
        ) as http:
            role_ids: list[str] = []
            for t in range(TYPES):
                r = await http.post(
                    "/duty-types",
                    json={
                        "name": f"Наряд {t + 1}",
                        "owner_unit_id": str(unit_ids[faculty]),
                        "start_time": f"{8 + t % 12:02d}:00",
                        "duration_minutes": 24 * 60 if t % 3 else 6 * 60,
                        "roles": [
                            {"name": f"Роль {k + 1}", "headcount": 1 + k % 2}
                            for k in range(ROLES_PER_TYPE)
                        ],
                    },
                )
                r.raise_for_status()
                role_ids += [x["id"] for x in r.json()["roles"]]
            schedules = {}
            for m in months_back(HISTORY_MONTHS):
                r = await http.post(
                    "/schedules", json={"unit_id": str(unit_ids[faculty]), "month": str(m)}
                )
                r.raise_for_status()
                schedules[m] = r.json()["id"]

            for n in PEOPLE:
                people.clear()
                for k in range(n):
                    people.append(
                        PersonInfo(
                            id=uuid.uuid5(uuid.NAMESPACE_OID, f"p-{n}-{k}"),
                            unit_id=unit_ids[subtree[k % len(subtree)]],
                            is_active=True,
                            last_name=f"Фамилия{k}",
                            first_name="Имя",
                            clearances=tuple(
                                (uuid.UUID(r), None, None) for r in rng.sample(role_ids, 5)
                            ),
                            exemptions=(),
                        )
                    )
                await fill_assignments(raw, n, [p.id for p in people])
                table_ms, table_size, table = await timed(
                    http, f"/schedules/{schedules[MONTH]}/table"
                )
                body = table.json()
                cells = sum(1 for row in body["rows"] for c in row["cells"] if c)
                rows.append(
                    {
                        "n": n,
                        "op": f"таблица месяца: {len(body['rows'])} ролей",
                        "count": cells,
                        "ms": table_ms,
                        "kb": table_size / 1024,
                    }
                )
                snap_ms, snap_size, snap = await timed(
                    http, f"/schedules/{schedules[MONTH]}/snapshot"
                )
                data = snap.json()
                rows.append(
                    {
                        "n": n,
                        "op": "снимок задачи (люди, ячейки, назначения за 3 мес.)",
                        "count": len(data["people"]),
                        "ms": snap_ms,
                        "kb": snap_size / 1024,
                        "extra": (
                            f"{len(data['cells'])} ячеек, {len(data['assignments'])} назначений"
                        ),
                    }
                )
                print(f"  {n} человек: готово", flush=True)
    conn = await asyncpg.connect(raw)
    version = await conn.fetchval("SHOW server_version")
    await conn.close()
    return rows, version


async def fill_assignments(url: str, n: int, person_ids: list[uuid.UUID]) -> None:
    """Все ячейки графиков заполнены людьми по кругу — пересечений по суткам нет."""
    conn = await asyncpg.connect(url)
    try:
        await conn.execute("TRUNCATE assignment")
        cells = await conn.fetch(
            "SELECT dp.id, dp.date, dt.start_time, dt.duration_minutes, dr.headcount"
            " FROM day_plan dp JOIN duty_type dt ON dt.id = dp.duty_type_id"
            " JOIN duty_role dr ON dr.id = dp.duty_role_id ORDER BY dp.date, dp.id"
        )
        now = dt.datetime.now(dt.UTC)
        records, k = [], 0
        tz = dt.timezone(dt.timedelta(hours=3))
        for c in cells:
            start = dt.datetime.combine(c["date"], c["start_time"], tzinfo=tz)
            end = start + dt.timedelta(minutes=c["duration_minutes"])
            last = (end - dt.timedelta(microseconds=1)).date()
            for _ in range(c["headcount"]):
                person = person_ids[k % len(person_ids)]
                k += 1
                records.append(
                    (
                        uuid.uuid4(),
                        c["id"],
                        person,
                        "Фамилия И. О.",
                        start,
                        end,
                        asyncpg.Range(c["date"], last + dt.timedelta(days=1)),
                        "manual",
                        False,
                        False,
                        False,
                        "bench",
                        "bench",
                        now,
                        now,
                        now,
                    )
                )
        await conn.copy_records_to_table(
            "assignment",
            records=records,
            columns=[
                "id",
                "day_plan_id",
                "person_id",
                "person_name",
                "start_at",
                "end_at",
                "occupied_days",
                "source",
                "is_pinned",
                "rest_override",
                "limit_override",
                "assigned_by",
                "assigned_by_name",
                "assigned_at",
                "created_at",
                "updated_at",
            ],
        )
        await conn.execute("ANALYZE")
    finally:
        await conn.close()


def render(rows: list[dict[str, Any]], version: str) -> str:
    def num(x: int) -> str:
        return f"{x:,}".replace(",", " ")

    lines = [
        "# Бенчмарк графика подразделения (фаза 3)",
        "",
        "> Сгенерировано `just bench-schedule` (tools/bench/schedule_snapshot.py). "
        f"PostgreSQL {version}, {platform.system()} {platform.machine()}, "
        f"Python {platform.python_version()}. Код scheduling в процессе (ASGI, без сети), "
        f"медиана {RUNS} прогонов, мс. Факультет синтетического дерева из {num(UNITS)} "
        f"подразделений, {TYPES} нарядов × {ROLES_PER_TYPE} роли, графики на "
        f"{MONTH:%m.%Y} и {HISTORY_MONTHS} предыдущих месяца, все ячейки заполнены людьми. "
        f"Люди поддерева — из подставного загрузчика (5 допусков на человека). Seed {SEED}.",
        "",
        "| Людей в поддереве | Операция | Записей | Время, мс | Ответ, КБ | Примечание |",
        "|---:|---|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| {num(r['n'])} | {r['op']} | {num(r['count'])} | {r['ms']:.1f} | "
            f"{r['kb']:.0f} | {r.get('extra', '')} |"
        )
    lines += [
        "",
        "Критерий фазы 3 (`docs/plans/phase-3.md`): таблица месяца крупного подразделения "
        "(≈ 60 ролей × 31 день) — не дольше 300 мс.",
        "",
        "Снимок — формат ADR-0013 (словари и индексы). Время сборки снимка без запроса в "
        "personnel; его стоимость — в `docs/benchmarks/people-snapshot.md`.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    url = os.environ.get("BENCH_DATABASE_URL")

    def run(db_url: str) -> tuple[list[dict[str, Any]], str]:
        cfg = Config(str(ROOT / "services" / "scheduling" / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "services" / "scheduling" / "migrations"))
        os.environ["DATABASE_URL"] = db_url
        command.upgrade(cfg, "head")
        return asyncio.run(bench(db_url))

    if url:
        rows, version = run(url)
    else:
        from testcontainers.community.postgres import PostgresContainer

        with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
            rows, version = run(pg.get_connection_url())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(rows, version), encoding="utf-8", newline="\n")
    print(f"Результаты: {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
