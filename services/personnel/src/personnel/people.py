"""Логика личного состава: scope по проекции дерева, список, карточка, изменения, перевод,
исключение из списков и восстановление, освобождения. Все изменения — с аудитом (ADR-0010)
и событиями (ADR-0004)."""

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from dutyflow_common import audit
from dutyflow_common.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
)
from dutyflow_common.ltree import is_descendant_or_self
from dutyflow_common.outbox import add_event
from dutyflow_common.pagination import Page, PageParams
from dutyflow_common.projections import RankProjection, UnitProjection
from dutyflow_common.scope import in_scope, scope_clause
from personnel.attributes import validate_values
from personnel.models import (
    AttributeDefinition,
    Exemption,
    ExemptionReason,
    Person,
    PersonAttribute,
    PersonCategory,
    Position,
    person_fio,
)
from personnel.schemas import (
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
    UnitCount,
)
from personnel.scoped import ScopedService, check_version

OVERLAP_CONSTRAINT = "ex_exemption_no_overlap"
EXEMPTION_EVENTS = {
    "exemption.create": "exemption.created",
    "exemption.update": "exemption.updated",
    "exemption.delete": "exemption.deleted",
}


def _like_pattern(q: str) -> str:
    escaped = q.lower().strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class PeopleService(ScopedService):
    # --- список и карточка -----------------------------------------------------------------

    def _list_query(self) -> Any:  # Select с пятью колонками; точный тип громоздок
        return (
            select(
                Person,
                UnitProjection.name.label("unit_name"),
                RankProjection.name.label("rank_name"),
                Position.name.label("position_name"),
                PersonCategory.name.label("category_name"),
            )
            .join(UnitProjection, UnitProjection.unit_id == Person.unit_id)
            .outerjoin(RankProjection, RankProjection.rank_id == Person.rank_id)
            .outerjoin(Position, Position.id == Person.position_id)
            .outerjoin(PersonCategory, PersonCategory.id == Person.category_id)
        )

    async def _exempt_today(
        self, person_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[dt.date, str]]:
        """Действующие сегодня освобождения — одним запросом на страницу списка."""
        if not person_ids:
            return {}
        today = dt.date.today()
        rows = await self.session.execute(
            select(Exemption.person_id, Exemption.date_to, ExemptionReason.name)
            .join(ExemptionReason, ExemptionReason.id == Exemption.reason_id)
            .where(
                Exemption.person_id.in_(person_ids),
                Exemption.date_from <= today,
                Exemption.date_to >= today,
            )
        )
        return {pid: (date_to, reason) for pid, date_to, reason in rows}

    async def list(self, flt: PeopleFilter, page: PageParams) -> Page[PersonListItem]:
        scope = self.policy.require(self.operator.roles, "person", "read")
        stmt = self._list_query().where(
            scope_clause(UnitProjection.path, await self.operator_path(), scope)
        )
        if flt.unit_id is not None:
            if flt.subtree:
                unit = await self._unit(flt.unit_id)
                stmt = stmt.where(is_descendant_or_self(UnitProjection.path, unit.path))
            else:
                stmt = stmt.where(Person.unit_id == flt.unit_id)
        if not flt.include_archived:
            stmt = stmt.where(Person.is_active)
        if flt.rank_id is not None:
            stmt = stmt.where(Person.rank_id == flt.rank_id)
        if flt.position_id is not None:
            stmt = stmt.where(Person.position_id == flt.position_id)
        if flt.category_id is not None:
            stmt = stmt.where(Person.category_id == flt.category_id)
        if flt.exempt_today:
            today = dt.date.today()
            stmt = stmt.where(
                select(Exemption.id)
                .where(
                    Exemption.person_id == Person.id,
                    Exemption.date_from <= today,
                    Exemption.date_to >= today,
                )
                .exists()
            )
        if flt.q and flt.q.strip():
            q = flt.q.strip()
            stmt = stmt.where(
                (person_fio.like(_like_pattern(q), escape="\\")) | (Person.personal_no == q)
            )
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = (
            await self.session.execute(
                stmt.order_by(Person.last_name, Person.first_name, Person.middle_name, Person.id)
                .limit(page.limit)
                .offset(page.offset)
            )
        ).all()
        exempt = await self._exempt_today([r.Person.id for r in rows])
        return Page(
            items=[self._item(r, exempt.get(r.Person.id)) for r in rows],
            total=total or 0,
            limit=page.limit,
            offset=page.offset,
        )

    async def counts(self) -> Sequence[UnitCount]:
        """Численность по подразделениям scope — для дерева подразделений (один запрос)."""
        scope = self.policy.require(self.operator.roles, "person", "read")
        rows = await self.session.execute(
            select(Person.unit_id, func.count())
            .join(UnitProjection, UnitProjection.unit_id == Person.unit_id)
            .where(
                Person.is_active,
                scope_clause(UnitProjection.path, await self.operator_path(), scope),
            )
            .group_by(Person.unit_id)
        )
        return [UnitCount(unit_id=u, people=n) for u, n in rows]

    @staticmethod
    def _item(row: Any, exempt: tuple[dt.date, str] | None = None) -> PersonListItem:
        p: Person = row.Person
        return PersonListItem(
            id=p.id,
            last_name=p.last_name,
            first_name=p.first_name,
            middle_name=p.middle_name,
            unit_id=p.unit_id,
            unit_name=row.unit_name,
            rank_id=p.rank_id,
            rank_name=row.rank_name,
            position_id=p.position_id,
            position_name=row.position_name,
            category_id=p.category_id,
            category_name=row.category_name,
            personal_no=p.personal_no,
            is_active=p.is_active,
            exempt_until=exempt[0] if exempt else None,
            exempt_reason=exempt[1] if exempt else None,
            version=p.version,
        )

    async def card(self, person_id: uuid.UUID) -> PersonOut:
        person = await self._person(person_id, "person", "read")
        row = (await self.session.execute(self._list_query().where(Person.id == person.id))).one()
        attrs = await self.session.execute(
            select(AttributeDefinition.code, PersonAttribute.value)
            .join(AttributeDefinition, AttributeDefinition.id == PersonAttribute.definition_id)
            .where(PersonAttribute.person_id == person.id)
        )
        exemptions = await self.session.scalars(
            select(Exemption)
            .where(Exemption.person_id == person.id)
            .order_by(Exemption.date_from.desc())
        )
        unit = await self._unit(person.unit_id)
        item = self._item(row, (await self._exempt_today([person.id])).get(person.id))
        return PersonOut(
            **item.model_dump(),
            note=person.note,
            archived_at=person.archived_at,
            attributes={code: value["v"] for code, value in attrs},
            exemptions=[ExemptionOut.model_validate(e) for e in exemptions],
            can_edit=person.is_active
            and in_scope(unit.path, await self.operator_path(), self._scope("person", "update")),
        )

    # --- изменение ---------------------------------------------------------------------------

    async def _definitions(self) -> dict[str, AttributeDefinition]:
        rows = await self.session.scalars(select(AttributeDefinition))
        return {d.code: d for d in rows}

    async def _check_refs(
        self,
        rank_id: uuid.UUID | None,
        position_id: uuid.UUID | None,
        category_id: uuid.UUID | None = None,
    ) -> None:
        if category_id is not None:
            category = await self.session.get(PersonCategory, category_id)
            if category is None or not category.is_active:
                raise ValidationFailedError("Категория личного состава не найдена")
        if rank_id is not None and await self.session.get(RankProjection, rank_id) is None:
            raise ValidationFailedError("Звание не найдено")
        if position_id is not None:
            position = await self.session.get(Position, position_id)
            if position is None or not position.is_active:
                raise ValidationFailedError("Должность не найдена")

    async def _check_personal_no(self, value: str | None, exclude: uuid.UUID | None = None) -> None:
        if not value:
            return
        stmt = select(Person.id).where(Person.personal_no == value)
        if exclude is not None:
            stmt = stmt.where(Person.id != exclude)
        if await self.session.scalar(stmt) is not None:
            raise ConflictError("Личный номер уже присвоен другому человеку")

    async def _save_attributes(
        self, person: Person, values: dict[str, Any], definitions: dict[str, AttributeDefinition]
    ) -> dict[str, Any]:
        """Сохраняет значения и возвращает изменения для аудита: {code: (было, стало)}."""
        current = {
            code: value["v"]
            for code, value in await self.session.execute(
                select(AttributeDefinition.code, PersonAttribute.value)
                .join(AttributeDefinition, AttributeDefinition.id == PersonAttribute.definition_id)
                .where(PersonAttribute.person_id == person.id)
            )
        }
        changes: dict[str, Any] = {}
        for code, value in values.items():
            if current.get(code) == value:
                continue
            definition = definitions[code]
            existing = await self.session.get(PersonAttribute, (person.id, definition.id))
            if value is None:
                if existing is not None:
                    await self.session.delete(existing)
            elif existing is None:
                self.session.add(
                    PersonAttribute(
                        person_id=person.id, definition_id=definition.id, value={"v": value}
                    )
                )
            else:
                existing.value = {"v": value}
            changes[code] = (current.get(code), value)
        return changes

    async def create(self, data: PersonCreate) -> Person:
        unit = await self._require_unit("person", "create", data.unit_id)
        if not unit.is_active:
            raise ValidationFailedError("Подразделение расформировано")
        await self._check_refs(data.rank_id, data.position_id, data.category_id)
        await self._check_personal_no(data.personal_no)
        definitions = await self._definitions()
        values = validate_values(definitions, data.attributes, require_all=True)

        person = Person(
            unit_id=unit.unit_id,
            **data.model_dump(exclude={"unit_id", "attributes"}),
            is_active=True,
        )
        self.session.add(person)
        await self.session.flush()
        await self._save_attributes(
            person, {k: v for k, v in values.items() if v is not None}, definitions
        )
        after = {
            **person.snapshot(),
            "attributes": {k: v for k, v in values.items() if v is not None},
        }
        audit.record(
            self.session,
            action="person.create",
            entity_type="person",
            entity_id=person.id,
            scope_unit_id=person.unit_id,
            after=after,
        )
        add_event(self.session, "person.created", "person", person.id, _event(person))
        await self._commit()
        return person

    async def update(self, person_id: uuid.UUID, data: PersonUpdate) -> Person:
        person = await self._person(person_id, "person", "update")
        if not person.is_active:
            raise ValidationFailedError("Человек исключён из списков — сначала восстановите его")
        check_version(person.version, data.version)
        fields = data.model_fields_set - {"version", "attributes"}
        if {"last_name", "first_name"} & fields and not all(
            getattr(data, f) for f in {"last_name", "first_name"} & fields
        ):
            raise ValidationFailedError("Фамилия и имя обязательны")
        if "category_id" in fields:
            if data.category_id is None:
                raise ValidationFailedError("Категорию можно сменить, но не сбросить")
            if data.category_id == person.category_id:
                fields -= {"category_id"}
        await self._check_refs(
            data.rank_id if "rank_id" in fields else None,
            data.position_id if "position_id" in fields else None,
            data.category_id if "category_id" in fields else None,
        )
        if "personal_no" in fields:
            await self._check_personal_no(data.personal_no, exclude=person.id)

        before = person.snapshot()
        # Сначала характеристики: их чтение вызывает autoflush, и если поля карточки уже
        # изменены, версия выросла бы дважды за одну операцию.
        attr_changes: dict[str, Any] = {}
        if data.attributes:
            definitions = await self._definitions()
            values = validate_values(definitions, data.attributes, require_all=False)
            attr_changes = await self._save_attributes(person, values, definitions)
        for f in fields:
            setattr(person, f, getattr(data, f))
        if attr_changes and not self.session.is_modified(person):
            # Изменились только характеристики — версия карточки всё равно должна вырасти.
            person.updated_at = func.now()
        await self._flush()
        after = person.snapshot()
        if attr_changes:
            before["attributes"] = {k: old for k, (old, _) in attr_changes.items()}
            after["attributes"] = {k: new for k, (_, new) in attr_changes.items()}
        if audit.record(
            self.session,
            action="person.update",
            entity_type="person",
            entity_id=person.id,
            scope_unit_id=person.unit_id,
            before=before,
            after=after,
        ):
            add_event(self.session, "person.updated", "person", person.id, _event(person))
        await self._commit()
        return person

    async def set_archived(
        self, person_id: uuid.UUID, version: int, *, archived: bool, comment: str | None
    ) -> Person:
        person = await self._person(person_id, "person", "archive")
        check_version(person.version, version)
        if person.is_active != archived:
            raise ValidationFailedError(
                "Человек уже исключён из списков" if archived else "Человек не исключён из списков"
            )
        before = person.snapshot()
        person.is_active = not archived
        person.archived_at = func.now() if archived else None
        await self._flush()
        action = "person.archive" if archived else "person.restore"
        audit.record(
            self.session,
            action=action,
            entity_type="person",
            entity_id=person.id,
            scope_unit_id=person.unit_id,
            before=before,
            after=person.snapshot(),
            comment=comment,
        )
        add_event(
            self.session,
            "person.archived" if archived else "person.restored",
            "person",
            person.id,
            _event(person),
        )
        await self._commit()
        await self.session.refresh(person)
        return person

    async def transfer(self, person_ids: Sequence[uuid.UUID], unit_id: uuid.UUID) -> int:
        """Перевод в другое подразделение (open-questions №24): смена unit_id, след в аудите.
        Атомарно: либо переводятся все, либо никто."""
        target = await self._require_unit("person", "create", unit_id)
        if not target.is_active:
            raise ValidationFailedError("Подразделение расформировано")
        people = (await self.session.scalars(select(Person).where(Person.id.in_(person_ids)))).all()
        if len(people) != len(set(person_ids)):
            raise NotFoundError("Часть людей не найдена")
        op_path, scope = await self.operator_path(), self._scope("person", "transfer")
        paths = dict(
            (
                await self.session.execute(
                    select(UnitProjection.unit_id, UnitProjection.path).where(
                        UnitProjection.unit_id.in_({p.unit_id for p in people})
                    )
                )
            ).all()
        )
        for p in people:
            if not in_scope(paths.get(p.unit_id, ""), op_path, scope):
                raise ForbiddenError(f"{p.last_name} {p.first_name}: вне зоны ответственности")
            if not p.is_active:
                raise ValidationFailedError(f"{p.last_name} {p.first_name}: исключён из списков")
        moved = 0
        for p in people:
            if p.unit_id == unit_id:
                continue
            before = p.snapshot()
            p.unit_id = unit_id
            audit.record(
                self.session,
                action="person.transfer",
                entity_type="person",
                entity_id=p.id,
                scope_unit_id=unit_id,
                before=before,
                after=p.snapshot(),
            )
            add_event(
                self.session,
                "person.transferred",
                "person",
                p.id,
                {**_event(p), "from_unit_id": before["unit_id"]},
            )
            moved += 1
        await self._commit()
        return moved

    # --- освобождения --------------------------------------------------------------------------

    async def _reason(self, reason_id: uuid.UUID) -> ExemptionReason:
        reason = await self.session.get(ExemptionReason, reason_id)
        if reason is None or not reason.is_active:
            raise ValidationFailedError("Причина освобождения не найдена")
        return reason

    async def _exemption(self, exemption_id: uuid.UUID, action: str) -> tuple[Exemption, Person]:
        exemption = await self.session.get(Exemption, exemption_id)
        if exemption is None:
            raise NotFoundError("Освобождение не найдено")
        person = await self._person(exemption.person_id, "exemption", action)
        return exemption, person

    async def add_exemption(self, person_id: uuid.UUID, data: ExemptionIn) -> Exemption:
        person = await self._person(person_id, "exemption", "create")
        await self._reason(data.reason_id)
        exemption = Exemption(
            person_id=person.id, **data.model_dump(), created_by=self.operator.subject
        )
        self.session.add(exemption)
        await self._flush_exemption()
        self._audit_exemption("exemption.create", exemption, person, after=exemption.snapshot())
        await self._commit()
        return exemption

    async def update_exemption(self, exemption_id: uuid.UUID, data: ExemptionUpdate) -> Exemption:
        exemption, person = await self._exemption(exemption_id, "update")
        check_version(exemption.version, data.version)
        await self._reason(data.reason_id)
        before = exemption.snapshot()
        for key, value in data.model_dump(exclude={"version"}).items():
            setattr(exemption, key, value)
        await self._flush_exemption()
        self._audit_exemption(
            "exemption.update", exemption, person, before=before, after=exemption.snapshot()
        )
        await self._commit()
        return exemption

    async def delete_exemption(self, exemption_id: uuid.UUID) -> None:
        exemption, person = await self._exemption(exemption_id, "delete")
        self._audit_exemption("exemption.delete", exemption, person, before=exemption.snapshot())
        await self.session.delete(exemption)
        await self._commit()

    async def bulk_exemption(self, data: BulkExemptionIn) -> BulkResult:
        """Освобождение группе людей. Частичный успех: пересечения и чужие люди пропускаются
        с объяснением, остальные сохраняются."""
        await self._reason(data.reason_id)
        result = BulkResult(done=0)
        for person_id in dict.fromkeys(data.person_ids):
            try:
                person = await self._person(person_id, "exemption", "create")
            except (NotFoundError, ForbiddenError) as exc:
                result.skipped.append({"person_id": str(person_id), "reason": exc.message})
                continue
            exemption = Exemption(
                person_id=person.id,
                **data.model_dump(exclude={"person_ids"}),
                created_by=self.operator.subject,
            )
            try:
                async with self.session.begin_nested():
                    self.session.add(exemption)
                    await self._flush_exemption()
            except ConflictError as exc:
                result.skipped.append(
                    {
                        "person_id": str(person_id),
                        "reason": exc.message,
                        "name": f"{person.last_name} {person.first_name}",
                    }
                )
                continue
            self._audit_exemption("exemption.create", exemption, person, after=exemption.snapshot())
            result.done += 1
        await self._commit()
        return result

    def _audit_exemption(
        self,
        action: str,
        exemption: Exemption,
        person: Person,
        *,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        audit.record(
            self.session,
            action=action,
            entity_type="exemption",
            entity_id=exemption.id,
            scope_unit_id=person.unit_id,
            before=before,
            after=after,
        )
        add_event(
            self.session,
            EXEMPTION_EVENTS[action],
            "exemption",
            exemption.id,
            {
                "exemption_id": exemption.id,
                "person_id": person.id,
                "unit_id": person.unit_id,
                "date_from": exemption.date_from,
                "date_to": exemption.date_to,
                "reason_id": exemption.reason_id,
            },
        )

    async def _flush_exemption(self) -> None:
        try:
            await self.session.flush()
        except IntegrityError as exc:
            if OVERLAP_CONSTRAINT in str(exc.orig):
                raise ConflictError("Период пересекается с уже существующим освобождением") from exc
            raise
        except StaleDataError as exc:
            raise ConflictError("Освобождение уже изменено другим пользователем") from exc

    # --- вспомогательное -----------------------------------------------------------------------

    async def _flush(self) -> None:
        try:
            await self.session.flush()
        except StaleDataError as exc:
            await self.session.rollback()
            raise ConflictError("Карточка уже изменена другим пользователем") from exc


def _event(p: Person) -> dict[str, Any]:
    return {
        "person_id": p.id,
        "unit_id": p.unit_id,
        "rank_id": p.rank_id,
        "position_id": p.position_id,
        "category_id": p.category_id,
        "is_active": p.is_active,
        "version": p.version,
    }
