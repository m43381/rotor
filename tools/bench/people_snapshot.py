"""Бенчмарк batch-снимка личного состава и списков personnel (критерий фазы 2).

Замеряется настоящий код сервиса (FastAPI-приложение в процессе, httpx ASGITransport,
PostgreSQL 16 в контейнере) — сериализация и запросы к БД включены, сеть — нет.

- `POST /internal/people/batch` — снимок для движка распределения: люди поддерева
  с характеристиками, освобождениями и допусками за месяц;
- `GET /people` — страница списка в scope оператора (виртуальный скролл UI) и поиск по ФИО.

    just bench-people        # → docs/benchmarks/people-snapshot.md
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
from pathlib import Path
from typing import Any

import asyncpg
import httpx
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.bench.hierarchy import generate_tree  # noqa: E402
from tools.gen.names import fio  # noqa: E402

OUT = ROOT / "docs" / "benchmarks" / "people-snapshot.md"
SIZES = (5_000, 20_000, 50_000)
UNITS = 5_000
RUNS = 10
SEED = 20260926
MONTH_FROM, MONTH_TO = dt.date(2026, 11, 1), dt.date(2026, 11, 30)
INTERNAL = "bench-token"
ROLES = 20  # ролей нарядов в организации
CLEARANCES_PER_PERSON = 5  # оценка объёма `docs/data-model.md` §8: ~250 тыс. на 50 тыс. человек


async def load(url: str, people: int) -> dict[str, Any]:
    """Дерево (проекция) + люди + характеристика «категория» + освобождения у ~15%
    + допуски (~5 ролей на человека, у части — со сроком действия)."""
    rng = random.Random(SEED + people)
    tree = generate_tree(UNITS, rng)
    unit_ids = [uuid.uuid5(uuid.NAMESPACE_OID, f"unit-{i}") for i in range(len(tree.parent))]
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(
            "TRUNCATE person, person_attribute, exemption, clearance, unit_projection, audit_log,"
            " outbox CASCADE"
        )
        # ltree нельзя передать бинарным COPY — вставляем пачками через executemany
        await conn.executemany(
            "INSERT INTO unit_projection"
            " (unit_id, parent_id, path, name, is_active, source_version)"
            " VALUES ($1, $2, $3::ltree, $4, true, 1)",
            [
                (unit_ids[i], unit_ids[p] if p >= 0 else None, tree.path[i], f"Подразделение {i}")
                for i, p in enumerate(tree.parent)
            ],
        )
        leaves = [i for i, d in enumerate(tree.depth) if d >= max(tree.depth) - 1]
        category_id = await conn.fetchval(
            "SELECT id FROM attribute_definition WHERE code = 'category'"
        )
        reason_id = await conn.fetchval("SELECT id FROM exemption_reason WHERE code = 'leave'")
        now = dt.datetime.now(dt.UTC)
        roles = [uuid.uuid5(uuid.NAMESPACE_OID, f"role-{i}") for i in range(ROLES)]
        person_rows, attr_rows, ex_rows, cl_rows = [], [], [], []
        for k in range(people):
            pid = uuid.uuid5(uuid.NAMESPACE_OID, f"person-{people}-{k}")
            f = fio(rng)
            person_rows.append(
                (pid, unit_ids[rng.choice(leaves)], f.last, f.first, f.middle, True, now, now, 1)
            )
            attr_rows.append((pid, category_id, '{"v": "Курсант"}'))
            for role in rng.sample(roles, CLEARANCES_PER_PERSON):
                valid_to = MONTH_FROM + dt.timedelta(days=rng.randint(-30, 60))
                cl_rows.append(
                    (
                        uuid.uuid4(),
                        pid,
                        role,
                        valid_to if rng.random() < 0.2 else None,
                        False,
                        "bench",
                        "bench",
                        now,
                        now,
                        now,
                        1,
                    )
                )
            if rng.random() < 0.15:
                start = MONTH_FROM + dt.timedelta(days=rng.randint(-10, 25))
                ex_rows.append(
                    (
                        uuid.uuid4(),
                        pid,
                        reason_id,
                        start,
                        start + dt.timedelta(days=rng.randint(1, 14)),
                        "bench",
                        now,
                        now,
                        1,
                    )
                )
        await conn.copy_records_to_table(
            "person",
            records=person_rows,
            columns=[
                "id",
                "unit_id",
                "last_name",
                "first_name",
                "middle_name",
                "is_active",
                "created_at",
                "updated_at",
                "version",
            ],
        )
        await conn.executemany(
            "INSERT INTO person_attribute (person_id, definition_id, value)"
            " VALUES ($1, $2, $3::jsonb)",
            attr_rows,
        )
        await conn.copy_records_to_table(
            "exemption",
            records=ex_rows,
            columns=[
                "id",
                "person_id",
                "reason_id",
                "date_from",
                "date_to",
                "created_by",
                "created_at",
                "updated_at",
                "version",
            ],
        )
        await conn.copy_records_to_table(
            "clearance",
            records=cl_rows,
            columns=[
                "id",
                "person_id",
                "duty_role_id",
                "valid_to",
                "overrides_requirements",
                "granted_by",
                "granted_by_name",
                "granted_at",
                "created_at",
                "updated_at",
                "version",
            ],
        )
        await conn.execute("ANALYZE")
        faculty = next(i for i, d in enumerate(tree.depth) if d == 1)
        return {"root": unit_ids[0], "faculty": unit_ids[faculty], "sample": person_rows[0][2]}
    finally:
        await conn.close()


async def timed(
    client: httpx.AsyncClient, method: str, url: str, **kw: Any
) -> tuple[float, int, Any]:
    await client.request(method, url, **kw)  # прогрев
    times, size, body = [], 0, None
    for _ in range(RUNS):
        t0 = time.perf_counter()
        r = await client.request(method, url, **kw)
        times.append((time.perf_counter() - t0) * 1000)
        r.raise_for_status()
        size, body = len(r.content), r.json()
    return statistics.median(times), size, body


async def bench(url: str) -> tuple[list[dict[str, Any]], str]:
    sys.path.insert(0, str(ROOT / "services" / "personnel" / "src"))
    from asgi_lifespan import LifespanManager

    from dutyflow_common.testing import TestIssuer
    from personnel.main import create_app
    from personnel.settings import PersonnelSettings

    settings = PersonnelSettings(database_url=url, internal_token=INTERNAL, log_level="WARNING")
    issuer = TestIssuer(settings)
    app = create_app(settings, token_verifier=issuer.verifier)
    rows: list[dict[str, Any]] = []
    version = ""
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://bench", timeout=120
        ) as http:
            for n in SIZES:
                ids = await load(url.replace("+asyncpg", ""), n)
                internal = {"X-Internal-Token": INTERNAL}
                period = {"date_from": str(MONTH_FROM), "date_to": str(MONTH_TO)}
                for scope, unit in (
                    ("вся организация", ids["root"]),
                    ("факультет", ids["faculty"]),
                ):
                    ms, size, body = await timed(
                        http,
                        "POST",
                        "/internal/people/batch",
                        headers=internal,
                        json={"unit_ids": [str(unit)], **period},
                    )
                    rows.append(
                        {
                            "n": n,
                            "op": f"batch-снимок: {scope}",
                            "count": len(body),
                            "ms": ms,
                            "kb": size / 1024,
                        }
                    )
                token = issuer.token(unit_id=ids["root"], roles=["operator"])
                auth = {"Authorization": f"Bearer {token}"}
                ms, size, body = await timed(
                    http, "GET", "/people", headers=auth, params={"limit": 100, "offset": n // 2}
                )
                rows.append(
                    {
                        "n": n,
                        "op": "список: страница 100 из середины",
                        "count": body["total"],
                        "ms": ms,
                        "kb": size / 1024,
                    }
                )
                q = ids["sample"][:4].lower()
                ms, size, body = await timed(
                    http, "GET", "/people", headers=auth, params={"limit": 100, "q": q}
                )
                rows.append(
                    {
                        "n": n,
                        "op": f"поиск по ФИО «{q}»",
                        "count": body["total"],
                        "ms": ms,
                        "kb": size / 1024,
                    }
                )
                print(f"  {n} человек: готово", flush=True)
            conn = await asyncpg.connect(url.replace("+asyncpg", ""))
            version = await conn.fetchval("SHOW server_version")
            await conn.close()
    return rows, version


def render(rows: list[dict[str, Any]], version: str) -> str:
    def num(x: int) -> str:
        return f"{x:,}".replace(",", " ")

    lines = [
        "# Бенчмарк снимка личного состава (фаза 2)",
        "",
        "> Сгенерировано `just bench-people` (tools/bench/people_snapshot.py). "
        f"PostgreSQL {version}, "
        f"{platform.system()} {platform.machine()}, Python {platform.python_version()}. "
        f"Код сервиса personnel в процессе (ASGI, без сети), медиана {RUNS} прогонов, мс. "
        f"Дерево — {num(UNITS)} подразделений, у ~15% людей освобождения, "
        f"{CLEARANCES_PER_PERSON} допусков на человека ({ROLES} ролей), период снимка — "
        f"{MONTH_FROM:%d.%m}–{MONTH_TO:%d.%m.%Y}. Seed {SEED}.",
        "",
        "| Людей в БД | Операция | Записей | Время, мс | Ответ, КБ |",
        "|---:|---|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {num(r['n'])} | {r['op']} | {num(r['count'])} | {r['ms']:.1f} | {r['kb']:.0f} |"
        )
    lines += [
        "",
        "Критерий фазы 2 (`docs/plans/phase-2.md`): снимок 5 000 человек — не дольше 1 с.",
        "",
        "Время страницы списка растёт с объёмом из-за подсчёта `total` (count по JOIN со scope) "
        "и OFFSET; сама выборка страницы идёт по индексу сортировки. Если на реальных данных это "
        "станет заметно, total можно считать приблизительно или кэшировать.",
        "",
        "С фазы 2b снимок включает допуски (~5 на человека): они дают около половины объёма "
        "ответа и основную часть времени на 20–50 тыс. человек (до 2b снимок 50 000 человек "
        "занимал 1,4 с и 10 МБ). Допуски агрегируются в БД по человеку. Компактный формат снимка "
        "(словарь ролей вместо повторяющихся UUID или Arrow, `docs/architecture.md` §4) — задача "
        "фазы 3, когда снимок начнёт собирать scheduling; движок работает с поддеревом "
        "подразделения, а не со всей организацией.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    url = os.environ.get("BENCH_DATABASE_URL")

    def run(db_url: str) -> tuple[list[dict[str, Any]], str]:
        cfg = Config(str(ROOT / "services" / "personnel" / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "services" / "personnel" / "migrations"))
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
