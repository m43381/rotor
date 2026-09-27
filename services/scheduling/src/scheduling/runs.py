"""Автораспределение: предпросмотр → применение (фаза 4b, `docs/allocation-design.md`).

- **Предпросмотр:** scheduling собирает снимок (ADR-0013), allocation считает решение, прогон и
  объяснения по каждой ячейке сохраняются. В графике ничего не меняется.
- **Применение:** снимок собирается заново. Если его hash отличается от сохранённого, данные
  изменились — прогон устарел, применение отклоняется (open-questions №45). Иначе в одной
  транзакции снимаются пересматриваемые автоматические назначения и ставятся новые
  (`source = auto`) либо делегируются ячейки — тем же механизмом, что вручную.
- Запускать и применять может тот, кто может менять график (№44).
"""

import datetime as dt
import json
import uuid
import zlib
from collections import defaultdict
from typing import Any
from zoneinfo import ZoneInfo

from pydantic_core import to_json
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import Range, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from dutyflow_common import audit
from dutyflow_common.context import Operator
from dutyflow_common.errors import AppError, ConflictError, NotFoundError, ValidationFailedError
from dutyflow_common.ids import uuid7
from dutyflow_common.outbox import add_event
from dutyflow_common.projections import UnitProjection
from scheduling.checks import interval
from scheduling.models import (
    AllocationDecision,
    AllocationRun,
    Assignment,
    DayPlan,
    DutyRole,
    DutyType,
)
from scheduling.people import PeopleLoader
from scheduling.schedules import ScheduleService
from scheduling.schemas import AllocateIn, DecisionOut, RunBrief, RunOut
from scheduling.snapshot import build_snapshot
from scheduling.solver import Solver


class RunStaleError(AppError):
    """Данные изменились после предпросмотра — нужен пересчёт."""

    status_code = 409
    code = "run_stale"


def _normalize(value: dict[str, Any]) -> dict[str, Any]:
    """UUID, даты и время — в строки JSON: так снимок уходит в allocation и хранится."""
    result: dict[str, Any] = json.loads(to_json(value))
    return result


class AllocationRunService:
    def __init__(
        self,
        session: AsyncSession,
        operator: Operator,
        people: PeopleLoader,
        solver: Solver,
        timezone: str,
        snapshot_days: int = 90,
    ) -> None:
        self.session = session
        self.operator = operator
        self.people = people
        self.solver = solver
        self.timezone = timezone
        self.snapshot_days = snapshot_days
        self.schedules = ScheduleService(session, operator)

    # --- предпросмотр ------------------------------------------------------------------------

    async def allocate(self, schedule_id: uuid.UUID, data: AllocateIn) -> AllocationRun:
        schedule, unit = await self.schedules.access(schedule_id, "update")
        snapshot = _normalize(
            await build_snapshot(self.session, self.people, schedule, unit, timezone=self.timezone)
        )
        config = {
            **data.config,
            "kind": data.kind,
            "mode": data.mode,
            "cell_ids": [str(c) for c in data.cell_ids] if data.cell_ids else None,
        }
        solution = await self.solver(snapshot, config, data.seed)

        run = AllocationRun(
            id=uuid7(),
            schedule_id=schedule.id,
            kind=data.kind,
            mode=data.mode,
            config=solution["config"],
            seed=data.seed,
            snapshot_hash=snapshot["hash"],
            snapshot=zlib.compress(to_json(snapshot), 6),
            solution_hash=solution["solution_hash"],
            status="preview_ready",
            metrics={
                **solution["metrics"],
                "deficits": solution["deficits"],
                "unfilled": solution["unfilled"],
                "removed": solution["removed"],
                "engine_version": solution["engine_version"],
                "solver": solution["solver"],
            },
            created_by=self.operator.subject,
            created_by_name=self.operator.full_name or self.operator.username,
        )
        self.session.add(run)
        await self.session.flush()
        await self._save_decisions(run, solution)
        await self._purge_old_snapshots()
        audit.record(
            self.session,
            action="allocation.preview",
            entity_type="allocation_run",
            entity_id=run.id,
            scope_unit_id=unit.unit_id,
            after={
                "kind": run.kind,
                "mode": run.mode,
                "seed": run.seed,
                "filled": run.metrics["filled"],
                "places": run.metrics["places"],
            },
        )
        await self.session.commit()
        return run

    async def _save_decisions(self, run: AllocationRun, solution: dict[str, Any]) -> None:
        items = solution["assignments"] if run.kind == "people" else solution["delegations"]
        key = "person" if run.kind == "people" else "unit"
        ids = {uuid.UUID(i[key]) for i in items} | {
            uuid.UUID(a[key]) for i in items for a in i["alternatives"]
        }
        names = await self._names(run.kind, ids, run)
        rows = [
            {
                "run_id": run.id,
                "day_plan_id": uuid.UUID(i["cell"]),
                "chosen_id": uuid.UUID(i[key]),
                "chosen_name": names.get(uuid.UUID(i[key]), i[key]),
                "rank": i["rank"],
                "cost": i["cost"],
                "candidates": i["candidates"],
                "features": i["features"],
                "alternatives": [
                    {**a, "name": names.get(uuid.UUID(a[key]), a[key])} for a in i["alternatives"]
                ],
                "rejected_summary": i.get("rejected")
                or (
                    {"capacity": i["capacity"], "keep": i["keep"]} if run.kind == "units" else None
                ),
            }
            for i in items
        ]
        for chunk in range(0, len(rows), 1000):
            await self.session.execute(
                insert(AllocationDecision).values(rows[chunk : chunk + 1000])
            )

    async def _names(
        self, kind: str, ids: set[uuid.UUID], run: AllocationRun
    ) -> dict[uuid.UUID, str]:
        if not ids:
            return {}
        if kind == "units":
            return dict(
                (
                    await self.session.execute(
                        select(UnitProjection.unit_id, UnitProjection.name).where(
                            UnitProjection.unit_id.in_(ids)
                        )
                    )
                ).all()
            )
        today = dt.date.today()
        people = await self.people(person_ids=list(ids), date_from=today, date_to=today)
        return {p.id: p.short_name for p in people}

    async def _purge_old_snapshots(self) -> None:
        """Снимки хранятся ограниченное время (`allocation_snapshot_days`)."""
        border = dt.datetime.now(dt.UTC) - dt.timedelta(days=self.snapshot_days)
        await self.session.execute(
            update(AllocationRun)
            .where(AllocationRun.created_at < border, AllocationRun.snapshot != b"")
            .values(snapshot=b"")
            .execution_options(synchronize_session=False)
        )

    # --- чтение -----------------------------------------------------------------------------

    async def _run(self, run_id: uuid.UUID, action: str) -> AllocationRun:
        run = await self.session.get(AllocationRun, run_id)
        if run is None:
            raise NotFoundError("Прогон не найден")
        await self.schedules.access(run.schedule_id, action)
        return run

    @staticmethod
    def brief(run: AllocationRun) -> RunBrief:
        return RunBrief(
            id=run.id,
            schedule_id=run.schedule_id,
            kind=run.kind,
            mode=run.mode,
            status=run.status,
            seed=run.seed,
            created_by_name=run.created_by_name,
            created_at=run.created_at,
            applied_at=run.applied_at,
            applied_by_name=run.applied_by_name,
            filled=int(run.metrics.get("filled", 0)),
            places=int(run.metrics.get("places", 0)),
        )

    async def get(self, run_id: uuid.UUID) -> RunOut:
        run = await self._run(run_id, "read")
        rows = await self.session.execute(
            select(AllocationDecision, DayPlan.date, DutyType.name, DutyRole.name)
            .outerjoin(DayPlan, DayPlan.id == AllocationDecision.day_plan_id)
            .outerjoin(DutyRole, DutyRole.id == DayPlan.duty_role_id)
            .outerjoin(DutyType, DutyType.id == DayPlan.duty_type_id)
            .where(AllocationDecision.run_id == run.id)
            .order_by(DayPlan.date, DutyType.name, DutyRole.name)
        )
        return RunOut(
            **self.brief(run).model_dump(),
            config=run.config,
            metrics=run.metrics,
            decisions=[
                DecisionOut(
                    day_plan_id=d.day_plan_id,
                    date=date,
                    duty_type_name=type_name,
                    role_name=role_name,
                    chosen_id=d.chosen_id,
                    chosen_name=d.chosen_name,
                    cost=d.cost,
                    candidates=d.candidates,
                    features=d.features,
                    alternatives=d.alternatives,
                    rejected=d.rejected_summary,
                )
                for d, date, type_name, role_name in rows
            ],
        )

    async def list_runs(self, schedule_id: uuid.UUID) -> list[RunBrief]:
        await self.schedules.access(schedule_id, "read")
        runs = await self.session.scalars(
            select(AllocationRun)
            .where(AllocationRun.schedule_id == schedule_id)
            .order_by(AllocationRun.created_at.desc())
            .limit(20)
        )
        return [self.brief(r) for r in runs]

    # --- применение и отмена ------------------------------------------------------------------

    async def discard(self, run_id: uuid.UUID) -> AllocationRun:
        run = await self._run(run_id, "update")
        if run.status != "preview_ready":
            raise ValidationFailedError("Отменить можно только непримененный предпросмотр")
        run.status = "discarded"
        await self.session.commit()
        return run

    async def apply(self, run_id: uuid.UUID) -> AllocationRun:
        run = await self.session.get(AllocationRun, run_id, with_for_update=True)
        if run is None:
            raise NotFoundError("Прогон не найден")
        schedule, unit = await self.schedules.access(run.schedule_id, "update")
        if run.status != "preview_ready":
            raise ValidationFailedError("Этот прогон уже применён, отменён или устарел")
        fresh = _normalize(
            await build_snapshot(self.session, self.people, schedule, unit, timezone=self.timezone)
        )
        if fresh["hash"] != run.snapshot_hash:
            run.status = "stale"
            await self.session.commit()
            raise RunStaleError(
                "После расчёта данные изменились (назначения, люди, допуски или ячейки). "
                "Пересчитайте распределение."
            )
        decisions = list(
            await self.session.scalars(
                select(AllocationDecision).where(AllocationDecision.run_id == run.id)
            )
        )
        if run.kind == "people":
            applied = await self._apply_people(run, decisions, unit.unit_id)
        else:
            applied = await self._apply_units(run, decisions, unit.unit_id)
        run.status = "applied"
        run.applied_at = dt.datetime.now(dt.UTC)
        run.applied_by_name = self.operator.full_name or self.operator.username
        audit.record(
            self.session,
            action="allocation.apply",
            entity_type="allocation_run",
            entity_id=run.id,
            scope_unit_id=unit.unit_id,
            after={"kind": run.kind, "applied": applied, "removed": len(run.metrics["removed"])},
        )
        add_event(
            self.session,
            "allocation.applied",
            "allocation_run",
            run.id,
            {"run_id": run.id, "schedule_id": schedule.id, "kind": run.kind, "applied": applied},
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(
                "Решение противоречит изменившимся данным. Пересчитайте распределение."
            ) from exc
        return run

    async def _apply_people(
        self, run: AllocationRun, decisions: list[AllocationDecision], scope_unit: uuid.UUID
    ) -> int:
        removed = [uuid.UUID(i) for i in run.metrics["removed"]]
        if removed:
            gone = list(
                await self.session.scalars(select(Assignment).where(Assignment.id.in_(removed)))
            )
            for a in gone:
                if a.source != "auto" or a.is_pinned:  # страховка: движок их не трогает (№41)
                    raise ConflictError("Решение снимает ручное или закреплённое назначение")
                audit.record(
                    self.session,
                    action="assignment.delete",
                    entity_type="assignment",
                    entity_id=a.id,
                    scope_unit_id=scope_unit,
                    before=a.snapshot(),
                    comment="Пересборка автораспределением",
                )
                await self.session.delete(a)
            await self.session.flush()
        cells = {
            c.id: (c, t)
            for c, t in await self.session.execute(
                select(DayPlan, DutyType)
                .join(DutyType, DutyType.id == DayPlan.duty_type_id)
                .where(DayPlan.id.in_({d.day_plan_id for d in decisions}))
            )
        }
        tz = ZoneInfo(self.timezone)
        for d in decisions:
            cell, duty_type = cells[d.day_plan_id]
            iv = interval(cell.date, duty_type.start_time, duty_type.duration_minutes, tz)
            a = Assignment(
                id=uuid7(),
                day_plan_id=cell.id,
                person_id=d.chosen_id,
                person_name=d.chosen_name,
                start_at=iv.start_at,
                end_at=iv.end_at,
                occupied_days=Range(iv.first_day, iv.last_day, bounds="[]"),
                source="auto",
                is_pinned=False,
                rest_override=False,
                limit_override=False,
                allocation_run_id=run.id,
                assigned_by=self.operator.subject,
                assigned_by_name=self.operator.full_name or self.operator.username,
            )
            self.session.add(a)
            if cell.delegation_status == "pending":
                cell.delegation_status = "accepted"
            audit.record(
                self.session,
                action="assignment.auto",
                entity_type="assignment",
                entity_id=a.id,
                scope_unit_id=scope_unit,
                after={**a.snapshot(), "allocation_run_id": run.id},
            )
            add_event(
                self.session,
                "assignment.created",
                "assignment",
                a.id,
                {
                    "assignment_id": a.id,
                    "day_plan_id": cell.id,
                    "person_id": a.person_id,
                    "unit_id": scope_unit,
                    "duty_type_id": cell.duty_type_id,
                    "duty_role_id": cell.duty_role_id,
                    "date": cell.date,
                    "start_at": a.start_at,
                    "end_at": a.end_at,
                    "source": "auto",
                },
            )
        await self.session.flush()
        return len(decisions)

    async def _apply_units(
        self, run: AllocationRun, decisions: list[AllocationDecision], scope_unit: uuid.UUID
    ) -> int:
        by_unit: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
        for d in decisions:
            if d.chosen_id != scope_unit:  # «оставить себе» — ничего не меняется
                by_unit[d.chosen_id].append(d.day_plan_id)
        total = 0
        for executor, cell_ids in sorted(by_unit.items(), key=lambda x: str(x[0])):
            total += await self.schedules.delegate(
                run.schedule_id, cell_ids, executor, commit=False
            )
        return total
