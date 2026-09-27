"""Задачи импорта: загрузка → предпросмотр → применение (open-questions №16, №54–55).

`documents` разбирает файл и хранит задачу; проверяет и применяет строки владелец данных
(`personnel`) — вызовом его публичного API от имени оператора (ADR-0014). Задачу видит
только тот, кто её создал; старые задачи вместе с файлами удаляются.
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from documents.models import ImportJob
from documents.sheets import build_report, build_template, parse
from dutyflow_common.context import Operator
from dutyflow_common.errors import NotFoundError, ValidationFailedError
from dutyflow_common.ids import uuid7
from dutyflow_common.upstream import UpstreamClient, UpstreamError

KINDS = ("people", "clearances", "exemptions")
TEMPLATE_NAMES = {
    "people": "Шаблон — личный состав.xlsx",
    "clearances": "Шаблон — допуски.xlsx",
    "exemptions": "Шаблон — освобождения.xlsx",
}


class ImportService:
    def __init__(
        self,
        session: AsyncSession,
        operator: Operator,
        token: str,
        personnel: UpstreamClient,
        ttl_days: int = 7,
    ) -> None:
        self.session = session
        self.operator = operator
        self.token = token
        self.personnel = personnel
        self.ttl_days = ttl_days

    async def _template(self, kind: str) -> dict[str, Any]:
        data: dict[str, Any] = await self.personnel.get(f"/imports/{kind}/template", self.token)
        return data

    async def template_file(self, kind: str) -> tuple[str, bytes]:
        return TEMPLATE_NAMES[kind], build_template(await self._template(kind))

    async def _check(self, kind: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = await self.personnel.post(
            f"/imports/{kind}", self.token, {"rows": rows, "dry_run": True}
        )
        return result

    async def upload(self, kind: str, filename: str, content: bytes) -> ImportJob:
        await self._purge()
        template = await self._template(kind)
        columns = [
            {"key": c["key"], "title": c["title"], "required": c.get("required", False)}
            for c in template["columns"]
        ]
        parsed = parse(filename, content, template["columns"])
        result = await self._check(kind, parsed.rows)
        job = ImportJob(
            id=uuid7(),
            kind=kind,
            status="preview",
            filename=filename[:300],
            content=content,
            columns=columns,
            rows=parsed.rows,
            report=result["rows"],
            summary=result["summary"],
            state_hash=result["state_hash"],
            notes=parsed.notes,
            created_by=self.operator.subject,
            created_by_name=self.operator.full_name or self.operator.username,
        )
        self.session.add(job)
        await self.session.commit()
        return job

    async def get(self, job_id: uuid.UUID) -> ImportJob:
        job = await self.session.get(ImportJob, job_id)
        if job is None or job.created_by != self.operator.subject:
            raise NotFoundError("Импорт не найден")
        return job

    async def list_mine(self, limit: int = 20) -> list[ImportJob]:
        rows = await self.session.scalars(
            select(ImportJob)
            .where(ImportJob.created_by == self.operator.subject)
            .order_by(ImportJob.created_at.desc())
            .limit(limit)
        )
        return list(rows)

    async def recheck(self, job_id: uuid.UUID) -> ImportJob:
        """Проверить те же строки заново — например, после изменения данных в системе."""
        job = await self._open(job_id)
        result = await self._check(job.kind, job.rows)
        job.report, job.summary, job.state_hash = (
            result["rows"],
            result["summary"],
            result["state_hash"],
        )
        await self.session.commit()
        return job

    async def apply(self, job_id: uuid.UUID, skip_invalid: bool) -> ImportJob:
        job = await self._open(job_id)
        try:
            result = await self.personnel.post(
                f"/imports/{job.kind}",
                self.token,
                {
                    "rows": job.rows,
                    "dry_run": False,
                    "skip_invalid": skip_invalid,
                    "expected_hash": job.state_hash,
                },
            )
        except UpstreamError as exc:
            if exc.code == "import_stale":
                # Данные изменились: показываем свежую проверку, применить можно заново
                await self.recheck(job_id)
            raise
        job.status = "applied"
        job.applied_at = dt.datetime.now(dt.UTC)
        job.applied_rows = result["summary"]["create"] + result["summary"]["update"]
        await self.session.commit()
        return job

    async def discard(self, job_id: uuid.UUID) -> ImportJob:
        job = await self._open(job_id)
        job.status = "discarded"
        await self.session.commit()
        return job

    async def report_file(self, job_id: uuid.UUID) -> tuple[str, bytes]:
        job = await self.get(job_id)
        stem = job.filename.rsplit(".", 1)[0]
        return f"{stem} — результат проверки.xlsx", build_report(job.columns, job.rows, job.report)

    async def _open(self, job_id: uuid.UUID) -> ImportJob:
        job = await self.get(job_id)
        if job.status != "preview":
            raise ValidationFailedError("Этот импорт уже применён или отменён")
        return job

    async def _purge(self) -> None:
        cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=self.ttl_days)
        await self.session.execute(delete(ImportJob).where(ImportJob.created_at < cutoff))
