"""Ручные назначения людей в ячейки (фаза 3b)."""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from scheduling.api.deps import AssignmentServiceDep
from scheduling.schemas import AssignIn, CandidatesOut

router = APIRouter(tags=["assignments"])


class PinAssignmentIn(BaseModel):
    pinned: bool


@router.get(
    "/day-plans/{day_plan_id}/candidates",
    response_model=CandidatesOut,
    summary="Назначенные и кандидаты: люди поддерева исполнителя с причинами непригодности",
)
async def candidates(day_plan_id: uuid.UUID, svc: AssignmentServiceDep) -> CandidatesOut:
    return await svc.candidates(day_plan_id)


@router.post(
    "/day-plans/{day_plan_id}/assignments",
    response_model=CandidatesOut,
    status_code=201,
    summary="Назначить человека",
    description="422 `assignment_blocked` — жёсткие нарушения (допуск, освобождение, занят, "
    "не в подразделении); 422 `override_required` — нарушены отдых или лимит, повтор с "
    "`confirm_override` и комментарием. Нарушения — в `details.violations`.",
)
async def assign(
    day_plan_id: uuid.UUID, data: AssignIn, svc: AssignmentServiceDep
) -> CandidatesOut:
    await svc.assign(day_plan_id, data)
    return await svc.candidates(day_plan_id)


@router.delete("/assignments/{assignment_id}", response_model=CandidatesOut)
async def remove(assignment_id: uuid.UUID, svc: AssignmentServiceDep) -> CandidatesOut:
    cell_id = await svc.remove(assignment_id)
    return await svc.candidates(cell_id)


@router.post("/assignments/{assignment_id}/pin", response_model=CandidatesOut)
async def pin(
    assignment_id: uuid.UUID, data: PinAssignmentIn, svc: AssignmentServiceDep
) -> CandidatesOut:
    cell_id = await svc.pin(assignment_id, data.pinned)
    return await svc.candidates(cell_id)
