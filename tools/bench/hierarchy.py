"""Бенчмарк хранения иерархии (ADR-0003): ltree против рекурсивного CTE и legacy-обхода.

Сравниваются три способа получить поддерево подразделения и посчитать людей в нём:
- `ltree`         — один индексный предикат `path <@ :root` (решение ADR-0003);
- `recursive CTE` — `WITH RECURSIVE` по `parent_id` (альтернатива из ADR-0003);
- `legacy N+1`    — обход в Python с одним запросом на узел, как `Unit.get_descendants_ids`
                    в старой системе (`docs/legacy-analysis.md` §4.3).

Плюс стоимость переноса поддерева одним UPDATE (ltree). Данные синтетические и
детерминированные (seed), PostgreSQL 16 поднимается через testcontainers
(или берётся из BENCH_DATABASE_URL).

    just bench                       # результаты → docs/benchmarks/hierarchy.md
"""

import asyncio
import os
import platform
import random
import statistics
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "benchmarks" / "hierarchy.md"

SIZES = (1_000, 5_000, 20_000)  # подразделений
PEOPLE = 50_000  # верхняя граница НФТ по личному составу
DEPTH = 7  # уровней, включая корень (профиль «6+ уровней», open-questions №4)
RUNS = 30
LEGACY_RUNS = 5  # legacy-обход медленный, меньше повторов
SEED = 20260926


@dataclass
class Tree:
    parent: list[int]  # parent[i] — индекс родителя, -1 у корня
    depth: list[int]
    path: list[str]


def generate_tree(n: int, rng: random.Random) -> Tree:
    """Дерево из n узлов глубиной DEPTH: ветвление подбирается так, чтобы нижний уровень
    заполнялся последним; внутри уровня число детей немного варьируется."""
    branching = max(2, round(n ** (1 / (DEPTH - 1))))
    parent, depth, path = [-1], [0], ["1"]
    frontier = [0]
    while len(parent) < n and frontier:
        next_frontier: list[int] = []
        for p in frontier:
            if depth[p] >= DEPTH - 1:
                continue
            for _ in range(max(1, branching + rng.randint(-1, 1))):
                if len(parent) >= n:
                    break
                i = len(parent)
                parent.append(p)
                depth.append(depth[p] + 1)
                path.append(f"{path[p]}.{i + 1}")
                next_frontier.append(i)
        frontier = next_frontier
    return Tree(parent, depth, path)


async def load(conn: asyncpg.Connection, tree: Tree, rng: random.Random) -> None:
    await conn.execute(
        """
        DROP TABLE IF EXISTS person, unit;
        CREATE EXTENSION IF NOT EXISTS ltree;
        CREATE TABLE unit (
            id bigint PRIMARY KEY, parent_id bigint REFERENCES unit, path text NOT NULL
        );
        CREATE TABLE person (id bigint PRIMARY KEY, unit_id bigint NOT NULL REFERENCES unit);
        """
    )
    await conn.copy_records_to_table(
        "unit",
        records=[
            (i + 1, (p + 1) if p >= 0 else None, tree.path[i]) for i, p in enumerate(tree.parent)
        ],
        columns=["id", "parent_id", "path"],
    )
    # Люди — в листьях и на предпоследнем уровне (группы и курсы), как в реальной структуре.
    max_depth = max(tree.depth)
    holders = [i for i, d in enumerate(tree.depth) if d >= max_depth - 1] or [0]
    await conn.copy_records_to_table(
        "person",
        records=[(k + 1, rng.choice(holders) + 1) for k in range(PEOPLE)],
        columns=["id", "unit_id"],
    )
    # COPY в бинарном формате не знает ltree — путь грузится текстом и конвертируется.
    await conn.execute(
        """
        ALTER TABLE unit ALTER COLUMN path TYPE ltree USING path::ltree;
        CREATE INDEX ix_unit_path ON unit USING gist (path);
        CREATE INDEX ix_unit_parent ON unit (parent_id);
        CREATE INDEX ix_person_unit ON person (unit_id);
        ANALYZE unit; ANALYZE person;
        """
    )


LTREE_SUBTREE = "SELECT id FROM unit WHERE path <@ $1::ltree"
CTE_SUBTREE = """
    WITH RECURSIVE t AS (
        SELECT id FROM unit WHERE id = $1
        UNION ALL
        SELECT u.id FROM unit u JOIN t ON u.parent_id = t.id
    ) SELECT id FROM t
"""
LTREE_PEOPLE = """
    SELECT count(*) FROM person p JOIN unit u ON u.id = p.unit_id WHERE u.path <@ $1::ltree
"""
CTE_PEOPLE = """
    WITH RECURSIVE t AS (
        SELECT id FROM unit WHERE id = $1
        UNION ALL
        SELECT u.id FROM unit u JOIN t ON u.parent_id = t.id
    ) SELECT count(*) FROM person p JOIN t ON t.id = p.unit_id
"""


async def legacy_subtree(conn: asyncpg.Connection, root_id: int) -> list[int]:
    """Как legacy `get_descendants_ids`: один запрос детей на каждый узел."""
    result, stack = [root_id], [root_id]
    while stack:
        node = stack.pop()
        children = [
            r["id"] for r in await conn.fetch("SELECT id FROM unit WHERE parent_id = $1", node)
        ]
        result.extend(children)
        stack.extend(children)
    return result


async def measure(fn: Callable[[], Awaitable[object]], runs: int) -> float:
    await fn()  # прогрев кэша
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        await fn()
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.median(times)


async def move_subtree(conn: asyncpg.Connection, node: int, new_parent: int) -> int:
    """Перенос поддерева одним UPDATE, как в сервисе org; откатывается, чтобы не менять данные."""
    tr = conn.transaction()
    await tr.start()
    try:
        old = await conn.fetchval("SELECT path::text FROM unit WHERE id = $1", node)
        new_prefix = await conn.fetchval("SELECT path::text FROM unit WHERE id = $1", new_parent)
        status = await conn.execute(
            """
            UPDATE unit SET path = CASE WHEN path = $1::ltree THEN $2::ltree
                                        ELSE $2::ltree || subpath(path, nlevel($1::ltree)) END
            WHERE path <@ $1::ltree
            """,
            old,
            f"{new_prefix}.{node}",
        )
        return int(status.split()[-1])
    finally:
        await tr.rollback()


@dataclass
class Row:
    units: int
    scope: str
    subtree_size: int
    people: int
    ltree_ms: float
    cte_ms: float
    legacy_ms: float


async def bench(url: str) -> tuple[list[Row], list[tuple[int, int, float]], str]:
    conn = await asyncpg.connect(url)
    rows: list[Row] = []
    moves: list[tuple[int, int, float]] = []
    version = await conn.fetchval("SHOW server_version")
    try:
        for n in SIZES:
            rng = random.Random(SEED + n)
            tree = generate_tree(n, rng)
            await load(conn, tree, rng)
            # Узлы для замера: корень (весь контур), «факультет» (уровень 1), «курс» (уровень 2).
            picks = {
                "вся организация (корень)": 0,
                "факультет (уровень 1)": next(i for i, d in enumerate(tree.depth) if d == 1),
                "курс (уровень 2)": next(i for i, d in enumerate(tree.depth) if d == 2),
            }
            for scope, idx in picks.items():
                node_id, node_path = idx + 1, tree.path[idx]
                size = len(await conn.fetch(LTREE_SUBTREE, node_path))
                people = await conn.fetchval(LTREE_PEOPLE, node_path)
                assert len(await conn.fetch(CTE_SUBTREE, node_id)) == size
                assert len(await legacy_subtree(conn, node_id)) == size
                ltree_ms = await measure(partial(conn.fetch, LTREE_SUBTREE, node_path), RUNS)
                cte_ms = await measure(partial(conn.fetch, CTE_SUBTREE, node_id), RUNS)
                legacy_ms = await measure(partial(legacy_subtree, conn, node_id), LEGACY_RUNS)
                rows.append(Row(n, scope, size, people, ltree_ms, cte_ms, legacy_ms))

                ltree_people = await measure(partial(conn.fetchval, LTREE_PEOPLE, node_path), RUNS)
                cte_people = await measure(partial(conn.fetchval, CTE_PEOPLE, node_id), RUNS)
                rows.append(
                    Row(
                        n,
                        f"{scope}: люди в scope",
                        size,
                        people,
                        ltree_people,
                        cte_people,
                        float("nan"),
                    )
                )
            # Перенос «курса» под другой «факультет»
            course = picks["курс (уровень 2)"]
            other_faculty = [i for i, d in enumerate(tree.depth) if d == 1][-1]
            moved = await move_subtree(conn, course + 1, other_faculty + 1)
            move_ms = await measure(
                partial(move_subtree, conn, course + 1, other_faculty + 1), RUNS
            )
            moves.append((n, moved, move_ms))
            print(f"  {n} подразделений: готово", flush=True)
    finally:
        await conn.close()
    return rows, moves, version


def render(rows: list[Row], moves: list[tuple[int, int, float]], version: str) -> str:
    def ms(x: float) -> str:
        return "—" if x != x else f"{x:.2f}"  # NaN → прочерк

    def num(x: int) -> str:
        return f"{x:,}".replace(",", " ")  # разряды — пробелом, как принято в русском тексте

    lines = [
        "# Бенчмарк хранения иерархии (ADR-0003)",
        "",
        f"> Сгенерировано `just bench` ({Path(__file__).relative_to(ROOT).as_posix()}). "
        f"PostgreSQL {version}, {platform.system()} {platform.machine()}, "
        f"Python {platform.python_version()}. Медиана {RUNS} прогонов "
        f"(legacy — {LEGACY_RUNS}), время на стороне клиента, мс. "
        f"Глубина дерева — {DEPTH} уровней, "
        f"личный состав — {num(PEOPLE)} человек. Seed {SEED}.",
        "",
        "## Поддерево и люди в scope",
        "",
        "| Подразделений | Scope | Узлов в поддереве | Людей "
        "| ltree | recursive CTE | legacy N+1 |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {num(r.units)} | {r.scope} | {num(r.subtree_size)} | {num(r.people)} "
            f"| {ms(r.ltree_ms)} | {ms(r.cte_ms)} | {ms(r.legacy_ms)} |"
        )
    lines += [
        "",
        "## Перенос поддерева «курса» под другой «факультет» (один UPDATE, ltree)",
        "",
        "| Подразделений | Переписано путей | Время, мс |",
        "|---:|---:|---:|",
    ]
    for n, moved, t in moves:
        lines.append(f"| {num(n)} | {num(moved)} | {t:.2f} |")
    lines += [
        "",
        "Строки «люди в scope» — типичный запрос списка с фильтром по зоне ответственности "
        "оператора "
        "(JOIN с таблицей личного состава). Legacy-обход для них не замерялся: в старой системе "
        "сначала собирался список id поддерева (столбец legacy N+1 в строке выше), а потом "
        "выполнялся `IN (...)`.",
        "",
        "Legacy-обход включает сетевой round-trip на каждый узел — именно это и есть его проблема: "
        "время растёт линейно с размером поддерева и умножается на задержку до БД.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    url = os.environ.get("BENCH_DATABASE_URL")
    if url:
        rows, moves, version = asyncio.run(bench(url))
    else:
        from testcontainers.community.postgres import PostgresContainer

        with PostgresContainer("postgres:16-alpine", driver=None) as pg:
            rows, moves, version = asyncio.run(bench(pg.get_connection_url()))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(rows, moves, version), encoding="utf-8", newline="\n")
    print(f"Результаты: {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
