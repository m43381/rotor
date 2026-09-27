"""Печать (фаза 6b): формы, реквизиты подразделений, загружаемые шаблоны.

- **Данные форм** берутся у `scheduling` от имени оператора (ADR-0014): права — как на
  чтение графика.
- **Реквизиты** (open-questions №52) хранятся здесь по подразделениям; при печати берутся
  у подразделения или у ближайшего вышестоящего. Задаёт их администратор подразделения —
  scope проверяется по пути подразделения из `org` и общей политике.
- **Шаблоны** PDF-форм (№51) заменяет суперадминистратор: загруженный шаблон проверяется
  отрисовкой на демо-данных, версии сохраняются, «вернуть встроенный» — снятие активности.
  Все изменения — в журнале аудита сервиса.
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from documents.forms import (
    FORMS,
    daily_context,
    load_context,
    sample_context,
    schedule_context,
)
from documents.models import DocumentSettings, PrintTemplate
from documents.render import (
    MEDIA,
    builtin_template,
    daily_docx,
    html_to_pdf,
    load_xlsx,
    render_html,
    schedule_xlsx,
)
from dutyflow_common import audit
from dutyflow_common.context import Operator
from dutyflow_common.errors import ConflictError, ForbiddenError, ValidationFailedError
from dutyflow_common.ids import uuid7
from dutyflow_common.policy import Policy, default_policy
from dutyflow_common.scope import in_scope
from dutyflow_common.upstream import UpstreamClient


@dataclass(frozen=True, slots=True)
class Document:
    filename: str
    content: bytes
    media_type: str


class PrintService:
    def __init__(
        self,
        session: AsyncSession,
        operator: Operator,
        token: str,
        *,
        scheduling: UpstreamClient,
        org: UpstreamClient,
        tz: ZoneInfo,
        analytics: UpstreamClient | None = None,
        policy: Policy = default_policy,
    ) -> None:
        self.session = session
        self.operator = operator
        self.token = token
        self.scheduling = scheduling
        self.org = org
        self.analytics = analytics
        self.tz = tz
        self.policy = policy

    # --- реквизиты -----------------------------------------------------------------------------

    async def _chain(self, unit_id: uuid.UUID) -> list[dict[str, Any]]:
        """Подразделение и его вышестоящие — от ближнего к корню. Чтение подразделения
        проверяет `org`: чужое для оператора — 404."""
        unit = await self.org.get(f"/units/{unit_id}", self.token)
        ancestors = await self.org.get(f"/units/{unit_id}/ancestors", self.token)
        return [unit, *reversed(ancestors)]

    async def requisites(self, unit_id: uuid.UUID) -> tuple[dict[str, Any] | None, str | None]:
        """Действующие реквизиты и имя подразделения, у которого они заданы."""
        chain = await self._chain(unit_id)
        ids = [uuid.UUID(u["id"]) for u in chain]
        rows = {
            s.unit_id: s
            for s in await self.session.scalars(
                select(DocumentSettings).where(DocumentSettings.unit_id.in_(ids))
            )
        }
        for u in chain:
            found = rows.get(uuid.UUID(u["id"]))
            if found is not None:
                return found.snapshot(), u["name"]
        return None, None

    async def settings_view(self, unit_id: uuid.UUID) -> dict[str, Any]:
        chain = await self._chain(unit_id)
        own = await self.session.get(DocumentSettings, unit_id)
        effective, source = await self.requisites(unit_id)
        return {
            "unit_id": unit_id,
            "unit_name": chain[0]["name"],
            "own": own.snapshot() if own else None,
            "version": own.version if own else None,
            "effective": effective,
            "inherited_from": source if own is None else None,
            "can_edit": await self._can_edit(chain[0]),
        }

    async def _can_edit(self, unit: dict[str, Any]) -> bool:
        me = await self.org.get("/me", self.token)
        scope = self.policy.scope_for(self.operator.roles, "document_settings", "update")
        return in_scope(unit["path"], me["unit"]["path"], scope)

    async def save_settings(
        self, unit_id: uuid.UUID, values: dict[str, str | None], version: int | None
    ) -> dict[str, Any]:
        chain = await self._chain(unit_id)
        if not await self._can_edit(chain[0]):
            raise ForbiddenError("Реквизиты подразделения задаёт его администратор")
        row = await self.session.get(DocumentSettings, unit_id)
        before = row.snapshot() if row else None
        name = self.operator.full_name or self.operator.username
        clean = {k: (v or "").strip() or None for k, v in values.items()}
        if row is None:
            row = DocumentSettings(unit_id=unit_id, updated_by_name=name, **clean)
            self.session.add(row)
        else:
            if version is not None and version != row.version:
                raise ConflictError(
                    "Реквизиты уже изменены другим пользователем. Обновите страницу."
                )
            for k, v in clean.items():
                setattr(row, k, v)
            row.updated_by_name = name
        try:
            await self.session.flush()
        except StaleDataError as exc:
            raise ConflictError("Реквизиты уже изменены другим пользователем") from exc
        audit.record(
            self.session,
            action="document_settings.update",
            entity_type="document_settings",
            entity_id=unit_id,
            scope_unit_id=unit_id,
            before=before,
            after=row.snapshot(),
        )
        await self.session.commit()
        return await self.settings_view(unit_id)

    async def clear_settings(self, unit_id: uuid.UUID) -> dict[str, Any]:
        chain = await self._chain(unit_id)
        if not await self._can_edit(chain[0]):
            raise ForbiddenError("Реквизиты подразделения задаёт его администратор")
        row = await self.session.get(DocumentSettings, unit_id)
        if row is not None:
            audit.record(
                self.session,
                action="document_settings.clear",
                entity_type="document_settings",
                entity_id=unit_id,
                scope_unit_id=unit_id,
                before=row.snapshot(),
            )
            await self.session.delete(row)
            await self.session.commit()
        return await self.settings_view(unit_id)

    # --- шаблоны -------------------------------------------------------------------------------

    async def _custom(self, form: str) -> PrintTemplate | None:
        result: PrintTemplate | None = await self.session.scalar(
            select(PrintTemplate)
            .where(PrintTemplate.form == form, PrintTemplate.is_active)
            .order_by(PrintTemplate.created_at.desc())
            .limit(1)
        )
        return result

    async def template_body(self, form: str) -> str:
        custom = await self._custom(form)
        return custom.body if custom else builtin_template(form)

    async def templates(self) -> list[dict[str, Any]]:
        result = []
        for form in FORMS.values():
            custom = await self._custom(form.code)
            result.append(
                {
                    "form": form.code,
                    "title": form.title,
                    "formats": list(form.formats),
                    "custom": custom is not None,
                    "updated_at": custom.created_at if custom else None,
                    "updated_by_name": custom.created_by_name if custom else None,
                    "comment": custom.comment if custom else None,
                }
            )
        return result

    async def template(self, form: str) -> dict[str, Any]:
        custom = await self._custom(form)
        return {
            "form": form,
            "title": FORMS[form].title,
            "body": custom.body if custom else builtin_template(form),
            "builtin": builtin_template(form),
            "custom": custom is not None,
            "variables": FORMS[form].variables,
        }

    def _require_superadmin(self) -> None:
        if not self.operator.is_superadmin:
            raise ForbiddenError("Шаблоны печатных форм меняет только суперадминистратор")

    def preview(self, form: str, body: str | None) -> Document:
        self._require_superadmin()
        html = render_html(body or builtin_template(form), sample_context(form))
        return Document(f"{FORMS[form].title} — предпросмотр.pdf", html_to_pdf(html), MEDIA["pdf"])

    async def save_template(self, form: str, body: str, comment: str | None) -> dict[str, Any]:
        self._require_superadmin()
        if not body.strip():
            raise ValidationFailedError("Шаблон пустой")
        render_html(body, sample_context(form))  # ошибки шаблона — до сохранения
        await self.session.execute(
            update(PrintTemplate).where(PrintTemplate.form == form).values(is_active=False)
        )
        row = PrintTemplate(
            id=uuid7(),
            form=form,
            body=body,
            comment=(comment or "").strip() or None,
            is_active=True,
            created_by_name=self.operator.full_name or self.operator.username,
        )
        self.session.add(row)
        audit.record(
            self.session,
            action="print_template.upload",
            entity_type="print_template",
            entity_id=row.id,
            scope_unit_id=None,
            after={"form": form, "size": len(body)},
            comment=row.comment,
        )
        await self.session.commit()
        return await self.template(form)

    async def reset_template(self, form: str) -> dict[str, Any]:
        self._require_superadmin()
        custom = await self._custom(form)
        if custom is not None:
            await self.session.execute(
                update(PrintTemplate).where(PrintTemplate.form == form).values(is_active=False)
            )
            audit.record(
                self.session,
                action="print_template.reset",
                entity_type="print_template",
                entity_id=custom.id,
                scope_unit_id=None,
                before={"form": form, "custom": True},
                after={"form": form, "custom": False},
            )
            await self.session.commit()
        return await self.template(form)

    # --- формы ---------------------------------------------------------------------------------

    async def schedule(self, schedule_id: uuid.UUID, fmt: str) -> Document:
        if fmt not in FORMS["schedule_month"].formats:
            raise ValidationFailedError("График печатается в PDF или XLSX")
        data = await self.scheduling.get(f"/schedules/{schedule_id}/print", self.token)
        unit_id = uuid.UUID(data["schedule"]["unit_id"])
        req, _ = await self.requisites(unit_id)
        ctx = schedule_context(data, req)
        month = dt.date.fromisoformat(data["schedule"]["month"])
        name = f"График нарядов — {ctx['unit']['name']} — {month:%m.%Y}.{fmt}"
        if fmt == "xlsx":
            return Document(name, schedule_xlsx(ctx), MEDIA["xlsx"])
        html = render_html(await self.template_body("schedule_month"), ctx)
        return Document(name, html_to_pdf(html), MEDIA["pdf"])

    async def daily(self, unit_id: uuid.UUID, date: dt.date, form: str, fmt: str) -> Document:
        if form not in ("daily_roster", "daily_order"):
            raise ValidationFailedError("Неизвестная форма")
        if fmt not in FORMS[form].formats:
            raise ValidationFailedError("Суточный наряд печатается в PDF или DOCX")
        data = await self.scheduling.get(
            "/rosters/daily", self.token, params={"unit_id": str(unit_id), "date": str(date)}
        )
        req, _ = await self.requisites(unit_id)
        ctx = daily_context(data, req, self.tz)
        title = "Приказ о суточном наряде" if form == "daily_order" else "Суточный наряд"
        name = f"{title} — {ctx['unit']['name']} — {date:%d.%m.%Y}.{fmt}"
        if fmt == "docx":
            return Document(name, daily_docx(ctx, form), MEDIA["docx"])
        html = render_html(await self.template_body(form), ctx)
        return Document(name, html_to_pdf(html), MEDIA["pdf"])

    async def load_report(
        self, unit_id: uuid.UUID, date_from: dt.date, date_to: dt.date, drafts: bool, fmt: str
    ) -> Document:
        if fmt not in FORMS["load_report"].formats:
            raise ValidationFailedError("Отчёт по нагрузке печатается в PDF или XLSX")
        ctx = await self._load_context(unit_id, date_from, date_to, drafts)
        name = f"Нагрузка — {ctx['unit']['name']} — {date_from:%d.%m.%Y}–{date_to:%d.%m.%Y}.{fmt}"
        if fmt == "xlsx":
            return Document(name, load_xlsx(ctx), MEDIA["xlsx"])
        html = render_html(await self.template_body("load_report"), ctx)
        return Document(name, html_to_pdf(html), MEDIA["pdf"])

    async def _load_context(
        self, unit_id: uuid.UUID, date_from: dt.date, date_to: dt.date, drafts: bool
    ) -> dict[str, Any]:
        if self.analytics is None:  # pragma: no cover — всегда задан в приложении
            raise ValidationFailedError("Аналитика не подключена")
        params: dict[str, Any] = {
            "unit_id": str(unit_id),
            "date_from": str(date_from),
            "date_to": str(date_to),
            "drafts": str(drafts).lower(),
        }
        overview = await self.analytics.get("/metrics/overview", self.token, params=params)
        people: list[dict[str, Any]] = []
        while True:
            page = await self.analytics.get(
                "/metrics/people",
                self.token,
                params={**params, "limit": 5_000, "offset": len(people)},
            )
            people += page["items"]
            if len(people) >= page["total"] or not page["items"]:
                break
        req, _ = await self.requisites(unit_id)
        return load_context(overview, people, req)

    async def html(self, form: str, **kwargs: Any) -> str:
        """HTML формы без перевода в PDF — для тестов и отладки шаблонов."""
        if form == "load_report":
            ctx = await self._load_context(
                kwargs["unit_id"], kwargs["date_from"], kwargs["date_to"], kwargs["drafts"]
            )
            return render_html(await self.template_body(form), ctx)
        if form == "schedule_month":
            data = await self.scheduling.get(
                f"/schedules/{kwargs['schedule_id']}/print", self.token
            )
            req, _ = await self.requisites(uuid.UUID(data["schedule"]["unit_id"]))
            return render_html(await self.template_body(form), schedule_context(data, req))
        data = await self.scheduling.get(
            "/rosters/daily",
            self.token,
            params={"unit_id": str(kwargs["unit_id"]), "date": str(kwargs["date"])},
        )
        req, _ = await self.requisites(kwargs["unit_id"])
        return render_html(await self.template_body(form), daily_context(data, req, self.tz))
