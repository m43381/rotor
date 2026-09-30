"""Бенчмарк импорта (фаза 6a): разбор файла в documents и проверка / применение строк в
personnel на 1 000 / 5 000 / 20 000 строк (20 000 — верхний предел файла).

Замеряется настоящий код: разбор xlsx и csv (`documents.sheets`), пакетный импорт
`POST /imports/people` — FastAPI-приложение personnel в процессе, httpx ASGITransport,
PostgreSQL 16 в контейнере; сеть между documents и personnel не входит.

    just bench-import        # → docs/benchmarks/import.md
"""

import asyncio
import io
import os
import platform
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import httpx
from alembic import command
from alembic.config import Config
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.gen.names import fio  # noqa: E402

OUT = ROOT / "docs" / "benchmarks" / "import.md"
SIZES = (1_000, 5_000, 20_000)
ROOT_UNIT = uuid.UUID("00000000-0000-7000-8000-000000000001")
COURSES = 20
COLUMNS: list[dict[str, Any]] = [
    {"key": "personal_no", "title": "Личный номер"},
    {"key": "last_name", "title": "Фамилия", "required": True},
    {"key": "first_name", "title": "Имя", "required": True},
    {"key": "middle_name", "title": "Отчество"},
    {"key": "unit", "title": "Подразделение", "required": True},
    {"key": "category", "title": "Категория", "required": True},
]


def matrix(n: int) -> list[list[Any]]:
    import random

    rng = random.Random(n)
    rows: list[list[Any]] = [[c["title"] for c in COLUMNS]]
    for k in range(n):
        f = fio(rng)
        rows.append(
            [f"B-{n}-{k}", f.last, f.first, f.middle, f"Академия / Курс {k % COURSES}", "Курсант"]
        )
    return rows


def as_xlsx(rows: list[list[Any]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Данные"
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def prepare(url: str) -> None:
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(
            "TRUNCATE person, person_attribute, unit_projection, audit_log, outbox CASCADE"
        )
        await conn.executemany(
            "INSERT INTO unit_projection (unit_id, parent_id, path, name, is_active,"
            " source_version) VALUES ($1, $2, $3::ltree, $4, true, 1)",
            [(ROOT_UNIT, None, "1", "Академия")]
            + [
                (uuid.uuid5(uuid.NAMESPACE_OID, f"c{i}"), ROOT_UNIT, f"1.{i + 2}", f"Курс {i}")
                for i in range(COURSES)
            ],
        )
    finally:
        await conn.close()


async def measure(url: str, pg_url: str) -> list[dict[str, Any]]:
    from documents.sheets import parse
    from dutyflow_common.testing import TestIssuer
    from personnel.main import create_app
    from personnel.settings import PersonnelSettings

    settings = PersonnelSettings(database_url=url)
    issuer = TestIssuer(settings)
    app = create_app(settings, token_verifier=issuer.verifier)
    token = issuer.token(unit_id=ROOT_UNIT, roles=["superadmin"], username="bench")
    results = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://bench",
        headers={"Authorization": f"Bearer {token}"},
        timeout=600,
    ) as client:
        for n in SIZES:
            await prepare(pg_url)
            data = matrix(n)
            xlsx = as_xlsx(data)
            csv = "\n".join(";".join(str(v) for v in r) for r in data).encode("utf-8")
            t = time.perf_counter()
            parsed = parse("people.xlsx", xlsx, COLUMNS)
            parse_xlsx = time.perf_counter() - t
            t = time.perf_counter()
            parse("people.csv", csv, COLUMNS)
            parse_csv = time.perf_counter() - t
            body = {"rows": parsed.rows, "dry_run": True}
            t = time.perf_counter()
            r = await client.post("/imports/people", json=body)
            preview = time.perf_counter() - t
            assert r.status_code == 200, r.text
            state_hash = r.json()["state_hash"]
            assert r.json()["summary"]["create"] == n
            t = time.perf_counter()
            r = await client.post(
                "/imports/people", json={**body, "dry_run": False, "expected_hash": state_hash}
            )
            apply = time.perf_counter() - t
            assert r.status_code == 200, r.text
            # Повтор того же файла: все строки находятся по личному номеру — «без изменений»
            t = time.perf_counter()
            r = await client.post("/imports/people", json=body)
            recheck = time.perf_counter() - t
            assert r.json()["summary"]["unchanged"] == n
            results.append(
                {
                    "rows": n,
                    "xlsx_kb": len(xlsx) / 1024,
                    "parse_xlsx": parse_xlsx,
                    "parse_csv": parse_csv,
                    "preview": preview,
                    "apply": apply,
                    "recheck": recheck,
                }
            )
            print(f"  {n}: предпросмотр {preview:.1f} с, применение {apply:.1f} с", flush=True)
    return results


def render(results: list[dict[str, Any]]) -> str:
    def s(x: float) -> str:
        return f"{x:.2f}".replace(".", ",")

    lines = [
        "# Бенчмарк импорта",
        "",
        "> Сгенерировано `just bench-import` (tools/bench/imports.py). "
        f"{platform.system()} {platform.machine()}, Python {platform.python_version()}, "
        "PostgreSQL 16 в контейнере. Импорт личного состава: личный номер, ФИО, подразделение, "
        "характеристика «Категория». Код personnel — в процессе (ASGI), без сети.",
        "",
        "| Строк | Размер xlsx, КБ | Разбор xlsx, с | Разбор csv, с | Предпросмотр, с | "
        "Применение, с | Повторная проверка, с |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        lines.append(
            f"| {r['rows']:,} | {r['xlsx_kb']:.0f} | {s(r['parse_xlsx'])} | {s(r['parse_csv'])} | "
            f"{s(r['preview'])} | {s(r['apply'])} | {s(r['recheck'])} |".replace(",", " ", 1)
        )
    lines += [
        "",
        "Применение — одна транзакция: люди, характеристики, запись аудита и событие на каждого. "
        "«Повторная проверка» — тот же файл после применения: все строки находятся по личному "
        "номеру и оказываются без изменений.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        url = pg.get_connection_url()
        cfg = Config(str(ROOT / "services" / "personnel" / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "services" / "personnel" / "migrations"))
        os.environ["DATABASE_URL"] = url
        command.upgrade(cfg, "head")
        results = asyncio.run(measure(url, url.replace("postgresql+asyncpg", "postgresql")))
    OUT.write_text(render(results), encoding="utf-8", newline="\n")
    print(f"Результаты: {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
