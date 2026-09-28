"""Проверка покрытия аудита (ADR-0010, фаза 7b): каждое изменение данных пишет журнал.

Во время прогона тестов сервиса перехватываются ответы тестовых клиентов. Для каждого
успешного изменяющего запроса (POST, PUT, PATCH, DELETE, кроме `/internal/*`) по его
`X-Request-Id` проверяется, появилась ли запись аудита. В конце полного прогона каждый
изменяющий маршрут приложения должен:
- быть вызван тестами хотя бы раз успешно;
- хотя бы раз оставить запись аудита.

Маршруты, которые данных не меняют или меняют только служебное состояние (расчёт
предпросмотра, задача импорта до применения), перечисляются в `exempt` с причиной.
"""

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from dutyflow_common.audit import AuditLog

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


class AuditCoverage:
    def __init__(self, exempt: dict[str, str] | None = None) -> None:
        self.exempt = exempt or {}
        self.app: FastAPI | None = None
        self.called: set[str] = set()
        self.audited: dict[str, bool] = defaultdict(bool)
        self._routes: dict[str, re.Pattern[str]] | None = None

    def bind(self, app: FastAPI) -> None:
        self.app = app

    def routes(self) -> dict[str, re.Pattern[str]]:
        """Изменяющие маршруты по OpenAPI-схеме приложения (в ней все публичные маршруты;
        `app.routes` в новых FastAPI держит подключённые роутеры обёртками)."""
        assert self.app is not None
        if self._routes is None:
            result: dict[str, re.Pattern[str]] = {}
            for path, ops in self.app.openapi().get("paths", {}).items():
                if path.startswith("/internal"):
                    continue
                pattern = re.compile("^" + re.sub(r"\{[^/}]+\}", "[^/]+", path) + "$")
                for method in ops:
                    if method.upper() in MUTATING:
                        result[f"{method.upper()} {path}"] = pattern
            self._routes = result
        return self._routes

    def _match(self, method: str, path: str) -> str | None:
        for key, pattern in self.routes().items():
            if key.startswith(method + " ") and pattern.match(path):
                return key
        return None

    async def hook(self, response: httpx.Response) -> None:
        request = response.request
        if request.method not in MUTATING or response.status_code >= 300 or self.app is None:
            return
        key = self._match(request.method, request.url.path)
        if key is None:
            return
        self.called.add(key)
        request_id = response.headers.get("X-Request-Id")
        if not request_id or self.audited[key]:
            return
        async with self.app.state.db.sessionmaker() as session:
            written = await session.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.request_id == request_id)
            )
        if written:
            self.audited[key] = True

    def report(self) -> tuple[list[str], list[str]]:
        """(не вызваны успешно, вызваны, но журнал не писали) — без исключений."""
        keys = sorted(k for k in self.routes() if k not in self.exempt)
        return (
            [k for k in keys if k not in self.called],
            [k for k in keys if k in self.called and not self.audited[k]],
        )

    def check(self, request: pytest.FixtureRequest, tests_dir: Path) -> None:
        run = {Path(str(item.fspath)).name for item in request.session.items}
        every = {p.name for p in tests_dir.glob("test_*.py")}
        if not every <= run:
            pytest.skip("Покрытие аудита проверяется только при полном прогоне тестов сервиса")
        routes = self.routes()
        assert routes, "Учёт покрытия не привязан к приложению или нет изменяющих маршрутов"
        assert self.called, "Хук тестовых клиентов не сработал ни разу — учёт не подключён"
        unknown = sorted(set(self.exempt) - set(self.routes()))
        not_called, silent = self.report()
        problems: list[str] = []
        if silent:
            problems.append("Изменяют данные без записи аудита:\n  " + "\n  ".join(silent))
        if not_called:
            problems.append(
                "Не проверены тестами (нет успешного вызова):\n  " + "\n  ".join(not_called)
            )
        if unknown:
            problems.append(
                "В исключениях есть несуществующие маршруты:\n  " + "\n  ".join(unknown)
            )
        assert not problems, "\n".join(problems)


def event_hooks(coverage: AuditCoverage) -> dict[str, Any]:
    return {"response": [coverage.hook]}
