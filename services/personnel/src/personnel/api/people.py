"""Личный состав и освобождения."""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from dutyflow_common.pagination import Page, PageParams, page_params
from personnel.api.deps import PeopleServiceDep
from personnel.schemas import (
    ArchiveIn,
    BulkExemptionIn,
    BulkResult,
    ExemptionIn,
    ExemptionOut,
    ExemptionUpdate,
    PeopleFilter,
    PersonCreate,
    PersonListItem,
    PersonOut,
    PersonUpdate,
    TransferIn,
    UnitCount,
)

router = APIRouter(tags=["people"])


@router.get("/people", response_model=Page[PersonListItem], summary="Личный состав в scope")
async def list_people(
    svc: PeopleServiceDep,
    page: Annotated[PageParams, Depends(page_params)],
    unit_id: Annotated[uuid.UUID | None, Query()] = None,
    subtree: Annotated[bool, Query()] = True,
    q: Annotated[str | None, Query(max_length=100)] = None,
    rank_id: Annotated[uuid.UUID | None, Query()] = None,
    position_id: Annotated[uuid.UUID | None, Query()] = None,
    category_id: Annotated[uuid.UUID | None, Query()] = None,
    exempt_today: Annotated[bool, Query()] = False,
    include_archived: Annotated[bool, Query()] = False,
) -> Page[PersonListItem]:
    flt = PeopleFilter(
        unit_id=unit_id,
        subtree=subtree,
        q=q,
        rank_id=rank_id,
        position_id=position_id,
        category_id=category_id,
        exempt_today=exempt_today,
        include_archived=include_archived,
    )
    return await svc.list(flt, page)


@router.get(
    "/people/counts", response_model=list[UnitCount], summary="Численность по подразделениям"
)
async def people_counts(svc: PeopleServiceDep) -> Sequence[UnitCount]:
    return await svc.counts()


@router.post("/people", response_model=PersonOut, status_code=201)
async def create_person(data: PersonCreate, svc: PeopleServiceDep) -> PersonOut:
    person = await svc.create(data)
    return await svc.card(person.id)


@router.get("/people/{person_id}", response_model=PersonOut, summary="Карточка")
async def get_person(person_id: uuid.UUID, svc: PeopleServiceDep) -> PersonOut:
    return await svc.card(person_id)


@router.patch("/people/{person_id}", response_model=PersonOut)
async def update_person(
    person_id: uuid.UUID, data: PersonUpdate, svc: PeopleServiceDep
) -> PersonOut:
    await svc.update(person_id, data)
    return await svc.card(person_id)


@router.post(
    "/people/{person_id}/archive", response_model=PersonOut, summary="Исключить из списков"
)
async def archive_person(person_id: uuid.UUID, data: ArchiveIn, svc: PeopleServiceDep) -> PersonOut:
    await svc.set_archived(person_id, data.version, archived=True, comment=data.comment)
    return await svc.card(person_id)


@router.post(
    "/people/{person_id}/restore", response_model=PersonOut, summary="Восстановить в списках"
)
async def restore_person(person_id: uuid.UUID, data: ArchiveIn, svc: PeopleServiceDep) -> PersonOut:
    await svc.set_archived(person_id, data.version, archived=False, comment=data.comment)
    return await svc.card(person_id)


@router.post("/people/transfer", response_model=BulkResult, summary="Перевод в подразделение")
async def transfer(data: TransferIn, svc: PeopleServiceDep) -> BulkResult:
    return BulkResult(done=await svc.transfer(data.person_ids, data.unit_id))


@router.post("/people/{person_id}/exemptions", response_model=ExemptionOut, status_code=201)
async def add_exemption(
    person_id: uuid.UUID, data: ExemptionIn, svc: PeopleServiceDep
) -> ExemptionOut:
    return ExemptionOut.model_validate(await svc.add_exemption(person_id, data))


@router.put("/exemptions/{exemption_id}", response_model=ExemptionOut)
async def update_exemption(
    exemption_id: uuid.UUID, data: ExemptionUpdate, svc: PeopleServiceDep
) -> ExemptionOut:
    return ExemptionOut.model_validate(await svc.update_exemption(exemption_id, data))


@router.delete("/exemptions/{exemption_id}", status_code=204)
async def delete_exemption(exemption_id: uuid.UUID, svc: PeopleServiceDep) -> None:
    await svc.delete_exemption(exemption_id)


@router.post("/exemptions/bulk", response_model=BulkResult, summary="Освобождение группе людей")
async def bulk_exemption(data: BulkExemptionIn, svc: PeopleServiceDep) -> BulkResult:
    return await svc.bulk_exemption(data)
