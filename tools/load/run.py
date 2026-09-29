# Шаблон отчёта — длинные строки русского текста в f-строках
# ruff: noqa: E501
"""Смешанная нагрузка активных операторов на наполненном стенде и отчёт.

Каждый виртуальный оператор входит под своей учёткой (password grant, обновление токена)
и по кругу выполняет сценарии интерфейса с паузой «на обдумывание». Замеряется каждый
HTTP-запрос. Параллельно раз в `probe` секунд запускается автораспределение курса на пустом
месяце (предпросмотр и отмена), а `docker stats` снимает CPU и память контейнеров.

Ошибка — сетевой сбой, 5xx или неожиданный 4xx. Отказ бизнес-правила там, где он возможен
(409/422 при назначении, 409 при правке карточки из-за версии), считается отдельно.
"""

import asyncio
import datetime as dt
import json
import multiprocessing
import platform
import random
import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import httpx

from tools.gen.names import MALE_LAST
from tools.load.common import (
    PASSWORD,
    PROJECT,
    ROOT,
    Token,
    client,
    env_values,
    load_state,
    run,
)

READ_TARGET = 1000  # мс, p95 (open-questions №62)
WRITE_TARGET = 1500
REPORT = ROOT / "docs" / "benchmarks" / "load.md"
RAW = ROOT / "docs" / "benchmarks" / "load.json"

# Сценарий: вес для редактора, доступен ли наблюдателю
SCENARIOS = {
    "open_schedule": (18, True),
    "people_list": (12, True),
    "people_search": (8, True),
    "person_card": (14, True),
    "candidates": (14, False),
    "dashboard": (8, True),
    "journal": (3, False),
    "assign": (8, False),
    "person_update": (4, False),
    "print_pdf": (2, False),
}
TITLES = {
    "login": "Вход (password grant / refresh)",
    "schedules_list": "Графики месяца (список)",
    "schedule_table": "Таблица графика месяца",
    "people_list": "Список личного состава",
    "people_search": "Поиск по фамилии",
    "person_card": "Карточка человека",
    "person_clearances": "Допуски человека",
    "candidates": "Кандидаты в ячейку",
    "dashboard": "Дашборд нагрузки",
    "journal": "Журнал аудита",
    "assign": "Назначение в ячейку",
    "unassign": "Снятие назначения",
    "person_update": "Правка карточки",
    "print_pdf": "Печать графика в PDF",
}


@dataclass(slots=True)
class Sample:
    name: str
    kind: str  # read | write | print | auth
    status: int
    ms: float
    at: float
    outcome: str  # ok | rejected | error
    detail: str = ""


@dataclass
class Collector:
    started: float
    samples: list[Sample] = field(default_factory=list)
    probes: list[dict[str, Any]] = field(default_factory=list)
    resources: list[dict[str, Any]] = field(default_factory=list)


class Operator:
    def __init__(
        self, http: httpx.AsyncClient, acc: dict[str, Any], state: dict[str, Any], col: Collector
    ) -> None:
        self.http, self.acc, self.col = http, acc, col
        self.token = Token(http, acc["username"], PASSWORD)
        self.unit = acc["unit_id"]
        self.schedule = state["schedules"][self.unit]
        self.month = dt.date.fromisoformat(state["month"])
        self.viewer = acc["role"] == "viewer"
        self.cells: list[str] = []
        self.people: list[dict[str, Any]] = []
        self.total_people = 0
        self.rng = random.Random(acc["username"])

    async def call(
        self,
        name: str,
        kind: str,
        method: str,
        path: str,
        *,
        allowed: tuple[int, ...] = (),
        **kw: Any,
    ) -> httpx.Response | None:
        try:
            headers = await self.token.headers()
        except httpx.HTTPError as exc:
            self.col.samples.append(
                Sample("login", "auth", 0, 0, time.time(), "error", repr(exc)[:200])
            )
            return None
        t0 = time.perf_counter()
        try:
            r = await self.http.request(method, path, headers=headers, **kw)
        except httpx.HTTPError as exc:
            ms = (time.perf_counter() - t0) * 1000
            self.col.samples.append(
                Sample(name, kind, 0, ms, time.time(), "error", repr(exc)[:200])
            )
            return None
        ms = (time.perf_counter() - t0) * 1000
        if r.status_code < 400:
            outcome, detail = "ok", ""
        elif r.status_code in allowed:
            outcome, detail = "rejected", r.text[:200]
        else:
            outcome, detail = "error", f"{r.status_code} {r.text[:200]}"
        self.col.samples.append(Sample(name, kind, r.status_code, ms, time.time(), outcome, detail))
        return r

    # --- сценарии ---------------------------------------------------------------------------

    async def open_schedule(self) -> None:
        params = {"month": self.month.isoformat(), "unit_id": self.unit}
        await self.call("schedules_list", "read", "GET", "/api/scheduling/schedules", params=params)
        r = await self.call(
            "schedule_table", "read", "GET", f"/api/scheduling/schedules/{self.schedule}/table"
        )
        if r is not None and r.status_code == 200 and not self.cells:
            self.cells = [
                c["id"]
                for row in r.json()["rows"]
                for c in row["cells"]
                if c and c["state"] in ("own", "incoming_active")
            ]

    async def people_list(self) -> None:
        pages = max(1, self.total_people // 50)
        params = {
            "unit_id": self.unit,
            "limit": 50,
            "offset": 50 * self.rng.randrange(min(pages, 20)),
        }
        r = await self.call("people_list", "read", "GET", "/api/personnel/people", params=params)
        if r is not None and r.status_code == 200:
            data = r.json()
            self.total_people = data["total"]
            self.people = data["items"] or self.people

    async def people_search(self) -> None:
        q = self.rng.choice(MALE_LAST)[:4]
        params = {"unit_id": self.unit, "q": q, "limit": 50}
        await self.call("people_search", "read", "GET", "/api/personnel/people", params=params)

    async def person_card(self) -> dict[str, Any] | None:
        if not self.people:
            await self.people_list()
        if not self.people:
            return None
        pid = self.rng.choice(self.people)["id"]
        r = await self.call("person_card", "read", "GET", f"/api/personnel/people/{pid}")
        await self.call(
            "person_clearances", "read", "GET", f"/api/personnel/people/{pid}/clearances"
        )
        return r.json() if r is not None and r.status_code == 200 else None

    async def candidates(self) -> dict[str, Any] | None:
        if not self.cells:
            await self.open_schedule()
        if not self.cells:
            return None
        cell = self.rng.choice(self.cells)
        r = await self.call(
            "candidates", "read", "GET", f"/api/scheduling/day-plans/{cell}/candidates"
        )
        return r.json() if r is not None and r.status_code == 200 else None

    async def dashboard(self) -> None:
        last = (self.month.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(
            days=1
        )
        params = {
            "unit_id": self.unit,
            "date_from": self.month.isoformat(),
            "date_to": last.isoformat(),
        }
        await self.call(
            "dashboard", "read", "GET", "/api/analytics/metrics/overview", params=params
        )

    async def journal(self) -> None:
        await self.call("journal", "read", "GET", "/api/analytics/audit", params={"limit": 50})

    async def assign(self) -> None:
        """Снять и вернуть назначенного или назначить и снять: данные после сценария те же."""
        data = await self.candidates()
        if data is None:
            return
        cell = data["cell"]["id"]
        rejected = (409, 422)
        if data["assigned"]:
            a = data["assigned"][0]
            r = await self.call(
                "unassign",
                "write",
                "DELETE",
                f"/api/scheduling/assignments/{a['id']}",
                allowed=rejected,
            )
            if r is not None and r.status_code == 200:
                body = {"person_id": a["person_id"]}
                await self.call(
                    "assign",
                    "write",
                    "POST",
                    f"/api/scheduling/day-plans/{cell}/assignments",
                    json=body,
                    allowed=rejected,
                )
            return
        clean = [c for c in data["candidates"] if c["eligible"] and not c["violations"]]
        if not clean:
            return
        person = self.rng.choice(clean[:20])["person_id"]
        r = await self.call(
            "assign", "write", "POST", f"/api/scheduling/day-plans/{cell}/assignments",
            json={"person_id": person}, allowed=rejected,
        )  # fmt: skip
        if r is not None and r.status_code == 201:
            mine = [a for a in r.json()["assigned"] if a["person_id"] == person]
            if mine:
                await self.call(
                    "unassign",
                    "write",
                    "DELETE",
                    f"/api/scheduling/assignments/{mine[0]['id']}",
                    allowed=rejected,
                )

    async def person_update(self) -> None:
        card = await self.person_card()
        if card is None:
            return
        body = {
            "version": card["version"],
            "note": f"Проверка нагрузки {self.rng.randrange(10**6)}",
        }
        await self.call(
            "person_update",
            "write",
            "PATCH",
            f"/api/personnel/people/{card['id']}",
            json=body,
            allowed=(409,),
        )

    async def print_pdf(self) -> None:
        await self.call(
            "print_pdf",
            "print",
            "GET",
            f"/api/documents/print/schedules/{self.schedule}",
            params={"format": "pdf"},
        )

    async def loop(self, start_at: float, stop_at: float, think: float) -> None:
        await asyncio.sleep(max(0.0, start_at - time.time()))
        t0 = time.perf_counter()
        try:
            await self.token.headers()
            self.col.samples.append(
                Sample("login", "auth", 200, (time.perf_counter() - t0) * 1000, time.time(), "ok")
            )
        except httpx.HTTPError as exc:
            self.col.samples.append(
                Sample("login", "auth", 0, 0, time.time(), "error", repr(exc)[:200])
            )
            return
        names = [n for n, (_, viewer_ok) in SCENARIOS.items() if viewer_ok or not self.viewer]
        weights = [SCENARIOS[n][0] for n in names]
        while time.time() < stop_at:
            scenario = self.rng.choices(names, weights=weights)[0]
            await getattr(self, scenario)()
            await asyncio.sleep(min(15.0, self.rng.expovariate(1 / think)))


async def probe_loop(
    http: httpx.AsyncClient,
    state: dict[str, Any],
    col: Collector,
    start_at: float,
    stop_at: float,
    every: float,
) -> None:
    env = env_values()
    admin = Token(http, "admin", env["DUTYFLOW_ADMIN_PASSWORD"])
    await asyncio.sleep(max(0.0, start_at - time.time()))
    n = 0
    while time.time() < stop_at - every / 2:
        schedule = state["probes"][n % len(state["probes"])]
        n += 1
        t0 = time.perf_counter()
        try:
            r = await http.post(
                f"/api/scheduling/schedules/{schedule}/allocate",
                json={},
                headers=await admin.headers(),
            )
            r.raise_for_status()
            run_ = r.json()
            while run_["status"] in ("queued", "running"):
                await asyncio.sleep(0.25)
                g = await http.get(
                    f"/api/scheduling/allocation-runs/{run_['id']}", headers=await admin.headers()
                )
                g.raise_for_status()
                run_ = g.json()
            seconds = time.perf_counter() - t0
            await http.post(
                f"/api/scheduling/allocation-runs/{run_['id']}/discard",
                headers=await admin.headers(),
            )
            col.probes.append(
                {
                    "seconds": round(seconds, 2),
                    "status": run_["status"],
                    "method": run_["method"],
                    "places": run_["places"],
                    "filled": run_["filled"],
                }
            )
        except httpx.HTTPError as exc:
            col.probes.append({"seconds": None, "status": "error", "error": repr(exc)[:200]})
        await asyncio.sleep(every)


def docker_stats() -> list[dict[str, Any]]:
    out = run(["docker", "stats", "--no-stream", "--format", "{{json .}}"], capture=True)
    rows = []
    for line in out.splitlines():
        item = json.loads(line)
        name = item["Name"]
        if not name.startswith(f"{PROJECT}-"):
            continue
        used = item["MemUsage"].split("/")[0].strip()
        rows.append(
            {
                "container": name.removeprefix(f"{PROJECT}-").rsplit("-", 1)[0],
                "cpu": float(item["CPUPerc"].rstrip("%") or 0),
                "mem_mib": _mib(used),
            }
        )
    return rows


def _mib(value: str) -> float:
    units = {"KiB": 1 / 1024, "MiB": 1.0, "GiB": 1024.0, "B": 1 / 1024**2}
    for suffix, factor in units.items():
        if value.endswith(suffix):
            return float(value.removesuffix(suffix)) * factor
    return 0.0


async def stats_loop(col: Collector, start_at: float, stop_at: float) -> None:
    await asyncio.sleep(max(0.0, start_at - time.time()))
    while time.time() < stop_at:
        rows = await asyncio.to_thread(docker_stats)
        col.resources.append({"at": time.time(), "rows": rows})
        await asyncio.sleep(15)


# --- отчёт ----------------------------------------------------------------------------------------


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))]


def fmt(x: float, digits: int = 0) -> str:
    return f"{x:,.{digits}f}".replace(",", " ").replace(".", ",")


def machine() -> dict[str, Any]:
    info = json.loads(run(["docker", "info", "--format", "{{json .}}"], capture=True))
    return {
        "host": f"{platform.system()} {platform.release()}, {platform.processor() or platform.machine()}",
        "docker_cpus": info.get("NCPU"),
        "docker_mem_gib": round(info.get("MemTotal", 0) / 1024**3, 1),
    }


def summarize(col: Collector, measure_from: float, measure_to: float) -> dict[str, Any]:
    window = [s for s in col.samples if measure_from <= s.at <= measure_to or s.kind == "auth"]
    by_name: dict[str, list[Sample]] = {}
    for s in window:
        by_name.setdefault(s.name, []).append(s)
    rows = {}
    for name, items in by_name.items():
        ok = [s.ms for s in items if s.outcome != "error"]
        rows[name] = {
            "kind": items[0].kind,
            "count": len(items),
            "errors": sum(s.outcome == "error" for s in items),
            "rejected": sum(s.outcome == "rejected" for s in items),
            "p50": pct(ok, 0.5),
            "p95": pct(ok, 0.95),
            "p99": pct(ok, 0.99),
            "max": max(ok, default=0.0),
            "error_samples": sorted({s.detail for s in items if s.outcome == "error"})[:3],
        }
    kinds = {}
    for kind in ("read", "write", "print"):
        items = [s for s in window if s.kind == kind]
        ok = [s.ms for s in items if s.outcome != "error"]
        kinds[kind] = {
            "count": len(items),
            "errors": sum(s.outcome == "error" for s in items),
            "p50": pct(ok, 0.5),
            "p95": pct(ok, 0.95),
            "p99": pct(ok, 0.99),
        }
    seconds = measure_to - measure_from
    requests = sum(1 for s in window if s.kind != "auth")
    res: dict[str, dict[str, list[float]]] = {}
    for snap in col.resources:
        for row in snap["rows"]:
            r = res.setdefault(row["container"], {"cpu": [], "mem": []})
            r["cpu"].append(row["cpu"])
            r["mem"].append(row["mem_mib"])
    resources = {
        name: {
            "cpu_avg": statistics.fmean(v["cpu"]),
            "cpu_max": max(v["cpu"]),
            "mem_max_mib": max(v["mem"]),
        }
        for name, v in res.items()
        if v["cpu"]
    }
    return {
        "rows": rows,
        "kinds": kinds,
        "rps": requests / seconds if seconds > 0 else 0.0,
        "seconds": seconds,
        "requests": requests,
        "probes": col.probes,
        "resources": resources,
    }


def write_report(result: dict[str, Any], state: dict[str, Any], params: dict[str, Any]) -> None:
    m, s = result["machine"], result["summary"]
    counts, timings = state["counts"], state["timings"]
    read, write = s["kinds"]["read"], s["kinds"]["write"]
    errors = sum(r["errors"] for r in s["rows"].values())
    probes_ok = [p["seconds"] for p in s["probes"] if p.get("status") == "preview_ready"]
    verdict = [
        ("Чтение: p95 ≤ 1 с", read["p95"] <= READ_TARGET, f"{fmt(read['p95'])} мс"),
        ("Изменения: p95 ≤ 1,5 с", write["p95"] <= WRITE_TARGET, f"{fmt(write['p95'])} мс"),
        ("Ошибок нет", errors == 0, f"{errors}"),
        (
            "Автораспределение курса ≤ 3 с (≤ 11 с при дефиците)",
            bool(probes_ok) and max(probes_ok) <= 11,
            f"медиана {fmt(statistics.median(probes_ok), 1)} с, максимум {fmt(max(probes_ok), 1)} с"
            if probes_ok
            else "нет замеров",
        ),
    ]
    lines = [
        "# Нагрузочный прогон",
        "",
        f"> Сгенерировано `just load run` (tools/load), {dt.date.today():%d.%m.%Y}. Отдельный стенд "
        f"`{PROJECT}` (docker compose, HTTPS через шлюз), те же образы, что в поставке. "
        f"Машина: {m['host']}; Docker: {m['docker_cpus']} CPU, {fmt(m['docker_mem_gib'], 1)} ГБ. "
        "Эталон по open-questions №62 — 8 CPU / 16 ГБ.",
        "",
        "## Итог по целям №62",
        "",
        "| Цель | Результат | Выполнена |",
        "|---|---|:---:|",
        *(f"| {name} | {value} | {'да' if ok else '**нет**'} |" for name, ok, value in verdict),
        "",
        "## Данные и нагрузка",
        "",
        f"- Подразделений {fmt(counts['units'])}, людей {fmt(counts['people'])}, освобождений "
        f"{fmt(counts['exemptions'])}, нарядов {fmt(counts['duty_types'])} ({fmt(counts['duty_roles'])} ролей), "
        f"допусков {fmt(counts['clearances'])}, графиков {fmt(counts['schedules'])}, учётных записей операторов "
        f"{fmt(counts['operators'])}.",
        f"- Рабочий месяц {state['month'][:7]}: графики всех владельцев нарядов распределены движком сверху "
        "вниз, применены и опубликованы; наряды попали в read-model аналитики.",
        f"- Одновременно активны {params['users']} операторов (уровни 1–4 дерева; наблюдателей "
        f"{sum(a['role'] == 'viewer' for a in state['active'][: params['users']])}), вход — постепенно за "
        f"{params['ramp']} с, затем {params['duration']} с замера. Пауза между действиями — экспоненциальная, "
        f"в среднем {fmt(params['think'], 1)} с (не больше 15 с). Генератор — {params.get('procs', 1)} процесса "
        "Python на той же машине, что и стенд.",
        f"- Замер: {fmt(s['requests'])} запросов за {fmt(s['seconds'])} с — {fmt(s['rps'], 1)} запросов/с.",
        "",
        "## Задержки по запросам",
        "",
        "Время — от отправки запроса до полного ответа через шлюз (HTTPS), мс. «Отказы» — ожидаемые "
        "ответы бизнес-правил (занято, версия изменилась), не ошибки.",
        "",
        "| Запрос | Вид | Число | p50 | p95 | p99 | Макс. | Ошибки | Отказы |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    kind_title = {"read": "чтение", "write": "изменение", "print": "печать", "auth": "вход"}
    for name in TITLES:
        r = s["rows"].get(name)
        if r is None:
            continue
        lines.append(
            f"| {TITLES[name]} | {kind_title[r['kind']]} | {fmt(r['count'])} | {fmt(r['p50'])} | "
            f"{fmt(r['p95'])} | {fmt(r['p99'])} | {fmt(r['max'])} | {r['errors']} | {r['rejected']} |"
        )
    lines += [
        f"| **Все чтения** | | {fmt(read['count'])} | {fmt(read['p50'])} | **{fmt(read['p95'])}** | "
        f"{fmt(read['p99'])} | | {read['errors']} | |",
        f"| **Все изменения** | | {fmt(write['count'])} | {fmt(write['p50'])} | **{fmt(write['p95'])}** | "
        f"{fmt(write['p99'])} | | {write['errors']} | |",
    ]
    samples = [(n, e) for n, r in s["rows"].items() for e in r["error_samples"]]
    if samples:
        lines += ["", "Примеры ошибок:", "", *(f"- `{n}`: {e}" for n, e in samples)]
    lines += [
        "",
        "## Автораспределение под нагрузкой",
        "",
        f"Каждые {params['probe']} с — предпросмотр распределения курса на пустом месяце "
        f"{state['probe_month'][:7]} (очередь arq, воркер движка) и отмена; время — от запроса до готового "
        "предпросмотра, включая сборку снимка и ожидание в очереди.",
        "",
        "| Замеров | Медиана, с | Максимум, с | Мест (медиана) | Закрыто (медиана) | Методы |",
        "|---:|---:|---:|---:|---:|---|",
    ]
    done = [p for p in s["probes"] if p.get("status") == "preview_ready"]
    if done:
        methods = ", ".join(sorted({str(p["method"]) for p in done}))
        lines.append(
            f"| {len(done)} | {fmt(statistics.median(probes_ok), 2)} | {fmt(max(probes_ok), 2)} | "
            f"{fmt(statistics.median(p['places'] for p in done))} | {fmt(statistics.median(p['filled'] for p in done))} | {methods} |"
        )
    failed = [p for p in s["probes"] if p.get("status") != "preview_ready"]
    if failed:
        lines.append(
            f"\nНе завершились: {len(failed)} ({', '.join(str(p.get('status')) for p in failed[:5])})."
        )
    alloc = state["allocations"]
    by_level: dict[int, list[dict[str, Any]]] = {}
    for a in alloc:
        by_level.setdefault(a["level"], []).append(a)
    lines += [
        "",
        "При наполнении (без параллельной нагрузки) рабочий месяц распределён так:",
        "",
        "| Уровень | Графиков | Людей в поддереве (медиана) | Мест (сумма) | Закрыто | Время, с: медиана / макс. |",
        "|---:|---:|---:|---:|---:|---|",
    ]
    for level, items in sorted(by_level.items()):
        secs = [a["seconds"] for a in items]
        places = sum(a["places"] for a in items)
        filled = sum(a["filled"] for a in items)
        lines.append(
            f"| {level} | {len(items)} | {fmt(statistics.median(a['people'] for a in items))} | {fmt(places)} | "
            f"{fmt(100 * filled / places if places else 0, 1)} % | {fmt(statistics.median(secs), 1)} / {fmt(max(secs), 1)} |"
        )
    lines += [
        "",
        "## Ресурсы контейнеров",
        "",
        "`docker stats` каждые 15 с за время замера; CPU — в процентах одного ядра.",
        "",
        "| Контейнер | CPU, среднее % | CPU, макс. % | Память, макс. МиБ |",
        "|---|---:|---:|---:|",
    ]
    for name, r in sorted(s["resources"].items(), key=lambda kv: -kv[1]["cpu_avg"]):
        lines.append(
            f"| {name} | {fmt(r['cpu_avg'])} | {fmt(r['cpu_max'])} | {fmt(r['mem_max_mib'])} |"
        )
    total_mem = sum(r["mem_max_mib"] for r in s["resources"].values())
    lines += [
        "",
        f"Сумма пиков памяти контейнеров — {fmt(total_mem / 1024, 1)} ГиБ.",
        "",
        "## Наполнение стенда",
        "",
        "Через публичные API под суперадминистратором, как это делал бы оператор (`just load populate`).",
        "",
        "| Шаг | Время, с |",
        "|---|---:|",
        *(f"| {k} | {fmt(v, 1)} |" for k, v in timings.items()),
        "",
        "Шаг «графики» включает ожидание, пока консьюмеры обработают ~1,4 млн событий о "
        "допусках и записей аудита после массовой выдачи.",
        "",
        "## Методика и допущения",
        "",
        "- Темп оператора в №62 не задан. Основной профиль — действие в среднем раз в 10 с "
        "(просмотр таблицы, выбор человека, чтение карточки занимают время). Стрессовый профиль "
        "с паузой 3 с — втрое плотнее — показывает запас: `just load run --think 3 --name load-stress` "
        "→ `docs/benchmarks/load-stress.md`.",
        "- Генератор нагрузки работает на той же машине, что и стенд, и делит с ним процессор; "
        "стенд использует ресурсы Docker целиком, эталон — 8 CPU / 16 ГБ.",
        "- Узкие места, найденные и исправленные этим прогоном, — в плане фазы 7 "
        "(`docs/plans/phase-7.md`, статус шага 7d) и ADR-0004.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _worker(
    args: tuple[list[tuple[int, dict[str, Any]]], dict[str, Any], float, float, float, float, int],
) -> list[Sample]:
    """Процесс генератора: своя доля операторов и свой цикл событий. Один процесс Python на
    300 HTTPS-клиентов сам становится узким местом (разбор JSON, TLS) и завышает задержки."""
    accounts, state, start, stop_at, ramp, think, total = args

    async def go() -> list[Sample]:
        col = Collector(started=start)
        async with client(timeout=120, connections=len(accounts) + 10) as http:
            ops = [(i, Operator(http, acc, state, col)) for i, acc in accounts]
            await asyncio.gather(
                *(op.loop(start + i * ramp / max(1, total), stop_at, think) for i, op in ops)
            )
        return col.samples

    return asyncio.run(go())


async def run_load(
    users: int, duration: int, ramp: int, think: float, probe: int, procs: int
) -> None:
    state = load_state()
    accounts = list(enumerate(state["active"][:users]))
    col = Collector(started=time.time())
    start = time.time() + 10  # процессам — время на запуск
    measure_from, stop_at = start + ramp, start + ramp + duration
    chunks = [accounts[k::procs] for k in range(procs)]
    loop = asyncio.get_running_loop()
    print(
        f"Нагрузка: {len(accounts)} операторов в {procs} процессах, разгон {ramp} с, "
        f"замер {duration} с",
        flush=True,
    )
    with ProcessPoolExecutor(procs, mp_context=multiprocessing.get_context("spawn")) as pool:
        futures = [
            loop.run_in_executor(
                pool, _worker, (chunk, state, start, stop_at, ramp, think, len(accounts))
            )
            for chunk in chunks
        ]
        async with client(timeout=120, connections=10) as http:
            _, _, *parts = await asyncio.gather(
                probe_loop(http, state, col, measure_from, stop_at, probe),
                stats_loop(col, measure_from, stop_at),
                *futures,
            )
    for part in parts:
        assert part is not None
        col.samples.extend(part)
    params = {
        "users": len(accounts),
        "duration": duration,
        "ramp": ramp,
        "think": think,
        "probe": probe,
        "procs": procs,
    }
    result = {
        "params": params,
        "machine": machine(),
        "summary": summarize(col, measure_from, stop_at),
    }
    RAW.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    write_report(result, state, params)
    k = result["summary"]["kinds"]
    print(
        f"Чтение p95 {k['read']['p95']:.0f} мс, изменения p95 {k['write']['p95']:.0f} мс, "
        f"ошибок {sum(r['errors'] for r in result['summary']['rows'].values())} → {REPORT.relative_to(ROOT)}"
    )


def main(
    users: int, duration: int, ramp: int, think: float, probe: int, procs: int, name: str
) -> None:
    global REPORT, RAW
    REPORT, RAW = (ROOT / "docs" / "benchmarks" / f"{name}{ext}" for ext in (".md", ".json"))
    asyncio.run(run_load(users, duration, ramp, think, probe, procs))
