"""Одиночные замеры тяжёлых запросов без нагрузки: база для поиска узких мест.

uv run python -m tools.load.probe
"""

import asyncio
import random
import statistics
import time
from collections import defaultdict
from typing import Any

from tools.load.common import PASSWORD, Token, client, load_state


async def main() -> None:
    state = load_state()
    rng = random.Random(1)
    accounts = [a for a in state["active"] if a["role"] != "viewer"]
    by_level: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for a in accounts:
        by_level[a["level"]].append(a)
    async with client(timeout=300) as http:
        for level in sorted(by_level):
            acc = rng.choice(by_level[level])
            token = Token(http, acc["username"], PASSWORD)
            h = await token.headers()
            sid = state["schedules"][acc["unit_id"]]
            times: dict[str, list[float]] = defaultdict(list)
            cells: list[str] = []
            for _ in range(3):
                t = time.perf_counter()
                r = await http.get(f"/api/scheduling/schedules/{sid}/table", headers=h)
                times["table"].append(time.perf_counter() - t)
                data = r.json()
                cells = [c["id"] for row in data["rows"] for c in row["cells"] if c]
                t = time.perf_counter()
                await http.get(
                    "/api/scheduling/schedules",
                    params={"month": state["month"], "unit_id": acc["unit_id"]},
                    headers=h,
                )
                times["list"].append(time.perf_counter() - t)
            for cell in rng.sample(cells, min(3, len(cells))):
                t = time.perf_counter()
                r = await http.get(f"/api/scheduling/day-plans/{cell}/candidates", headers=h)
                times["candidates"].append(time.perf_counter() - t)
                n = len(r.json().get("candidates", []))
            summary = ", ".join(
                f"{k} {statistics.median(v) * 1000:.0f} мс" for k, v in times.items()
            )
            print(
                f"уровень {level}: строк {len(data['rows'])}, ячеек {len(cells)}, "
                f"кандидатов ~{n}: {summary}",
                flush=True,
            )


if __name__ == "__main__":
    asyncio.run(main())
