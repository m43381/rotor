"""Допуски к ролям нарядов (ADR-0009).

- Допуск выдаёт оператор, в чей scope входит подразделение человека.
- Допуск к роли можно выдать, только если наряд принадлежит подразделению человека или
  вышестоящему: только такие роли могут прийти к нему по делегированию.
- Требования роли проверяются при выдаче. Если человек их не проходит, сервис отвечает 422
  `requirements_not_met` с перечнем нарушений; выдать всё равно можно — с подтверждением
  и комментарием, запись попадает в аудит (`clearance.grant_override`). Такой допуск важнее
  требований: движок распределения видит только сам допуск.
- Категория личного состава — жёсткое требование (ADR-0018): допуск человеку неподходящей
  категории не выдаётся (422 `category_not_allowed`), а ставший неподходящим не действует
  (статус `category_mismatch`, во внутренний batch не попадает).
- Роль, закреплённая за подразделением, доступна только людям его поддерева (ADR-0018).
- Требования берутся из локальной копии (`duty_role_projection`), поэтому выдача не зависит
  от доступности scheduling.

Все данные для проверки грузятся пачками (роли, люди, характеристики, звания), без N+1.
"""

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import StaleDataError

from dutyflow_common import audit
from dutyflow_common.errors import AppError, ConflictError, NotFoundError, ValidationFailedError
from dutyflow_common.ids import uuid7
from dutyflow_common.ltree import is_ancestor_or_self, is_descendant_or_self
from dutyflow_common.outbox import add_event
from dutyflow_common.pagination import Page, PageParams
from dutyflow_common.projections import RankProjection, UnitProjection
from dutyflow_common.requirements import (
    OP_LABELS,
    PersonTraits,
    RoleRequirements,
    Violation,
    check,
)
from dutyflow_common.scope import in_scope, scope_clause
from personnel.models import (
    AttributeDefinition,
    Clearance,
    DutyRoleProjection,
    DutyTypeProjection,
    Person,
    PersonAttribute,
    PersonCategory,
    Position,
)
from personnel.schemas import (
    BulkClearanceIn,
    BulkClearanceResult,
    ClearanceIn,
    ClearanceOption,
    ClearanceOut,
    ClearanceRoleOut,
    ClearanceStatus,
    ClearanceUpdate,
    MismatchItem,
    RevokeIn,
    ViolationOut,
)
from personnel.scoped import ScopedService, check_version

ACTIVE_CONSTRAINT = "uq_clearance_person_role_active"


class RequirementsNotMetError(AppError):
    """Человек не проходит требования роли — нужна выдача с подтверждением."""

    status_code = 422
    code = "requirements_not_met"


class CategoryNotAllowedError(AppError):
    """Категория человека не допускается ролью — допуск не выдаётся даже с подтверждением."""

    status_code = 422
    code = "category_not_allowed"


@dataclass(frozen=True, slots=True)
class RoleInfo:
    role: DutyRoleProjection
    duty_type: DutyTypeProjection
    owner_path: str | None
    owner_name: str | None
    requirements: RoleRequirements
    # Путь подразделения, за которым закреплена роль (ADR-0018); None — не закреплена
    assigned_path: str | None = None
    assigned_name: str | None = None

    @property
    def is_active(self) -> bool:
        return self.role.is_active and self.duty_type.is_active

    def covers(self, unit_path: str) -> bool:
        """Наряд принадлежит подразделению человека или вышестоящему, а закреплённая роль —
        ещё и подразделению из поддерева закреплённого: только к ним ячейка может прийти."""
        if self.owner_path is None:
            return False
        person = unit_path.split(".")
        owner = self.owner_path.split(".")
        if person[: len(owner)] != owner:
            return False
        if self.role.assigned_unit_id is None:
            return True
        if self.assigned_path is None:  # закреплённое подразделение неизвестно — не выдаём
            return False
        assigned = self.assigned_path.split(".")
        return person[: len(assigned)] == assigned

    def not_covered_reason(self) -> str:
        if self.role.assigned_unit_id is not None:
            return (
                f"Роль «{self.role.name}» закреплена за подразделением "
                f"«{self.assigned_name or '?'}» — допуск выдаётся только его личному составу"
            )
        return (
            f"Наряд «{self.duty_type.name}» принадлежит подразделению «{self.owner_name}» "
            "и не распространяется на подразделение человека"
        )

    def ref(self) -> dict[str, Any]:
        return {
            "duty_role_id": self.role.duty_role_id,
            "role_name": self.role.name,
            "duty_type_id": self.duty_type.duty_type_id,
            "duty_type_name": self.duty_type.name,
            "owner_unit_id": self.duty_type.owner_unit_id,
            "owner_unit_name": self.owner_name,
            "assigned_unit_id": self.role.assigned_unit_id,
            "assigned_unit_name": self.assigned_name,
        }


class Describer:
    """Человекочитаемые формулировки нарушений: имена званий, должностей, характеристик."""

    def __init__(
        self,
        ranks: Sequence[RankProjection],
        positions: dict[uuid.UUID, str],
        attributes: dict[str, AttributeDefinition],
        categories: dict[uuid.UUID, str] | None = None,
    ) -> None:
        # На один порядок может приходиться несколько званий (архивное и действующее)
        self.rank_names: dict[int, str] = {}
        for r in sorted(ranks, key=lambda r: r.is_active):
            self.rank_names[r.order] = r.name
        self.positions = positions
        self.attributes = attributes
        self.categories = categories or {}

    def _value(self, code: str | None, value: Any) -> str:
        if value is None:
            return "не заполнено"
        if isinstance(value, bool):
            return "да" if value else "нет"
        if isinstance(value, list):
            return ", ".join(self._value(code, v) for v in value)
        definition = self.attributes.get(code or "")
        if definition is not None and definition.value_type == "date":
            try:
                return dt.date.fromisoformat(str(value)).strftime("%d.%m.%Y")
            except ValueError:
                pass
        return f"«{value}»"

    def message(self, v: Violation, op: str | None = None) -> str:
        match v.kind:
            case "category":
                allowed = ", ".join(
                    f"«{self.categories.get(uuid.UUID(c), '?')}»" for c in v.expected
                )
                have = self.categories.get(v.actual) if v.actual else None
                head = f"Категория «{have}»" if have else "Категория не указана и"
                return f"{head} не допускается ролью: допустимы {allowed}"
            case "rank":
                need = self.rank_names.get(v.expected, f"порядок {v.expected}")
                have = self.rank_names.get(v.actual) if v.actual is not None else None
                return f"Звание ниже требуемого: нужно не ниже «{need}», у человека — " + (
                    f"«{have}»" if have else "звание не указано"
                )
            case "position":
                allowed = ", ".join(
                    f"«{self.positions.get(uuid.UUID(p), '?')}»" for p in v.expected
                )
                have = self.positions.get(v.actual) if v.actual else None
                head = (
                    f"Должность «{have}» не входит" if have else "Должность не указана и не входит"
                )
                return f"{head} в допустимые: {allowed}"
            case "attribute":
                definition = self.attributes.get(v.code or "")
                name = definition.name if definition else v.code
                label = "" if op in (None, "eq") else OP_LABELS[op] + " "
                need = self._value(v.code, v.expected)
                have = self._value(v.code, v.actual)
                return f"«{name}»: требуется {label}{need}, у человека — {have}"
        return "Требование не выполнено"  # pragma: no cover

    def out(self, violations: Iterable[Violation], req: RoleRequirements) -> list[ViolationOut]:
        ops = {a.code: a.op for a in req.attributes}
        return [
            ViolationOut(
                kind=v.kind,
                code=v.code,
                message=self.message(v, ops.get(v.code or "")),
                hard=v.hard,
            )
            for v in violations
        ]


def status_of(
    c: Clearance, info: RoleInfo | None, today: dt.date, traits: PersonTraits | None = None
) -> ClearanceStatus:
    if c.revoked_at is not None:
        return "revoked"
    if info is None or not info.is_active:
        return "role_inactive"
    if traits is not None and any(v.hard for v in check(traits, info.requirements)):
        return "category_mismatch"
    if c.valid_from is not None and c.valid_from > today:
        return "future"
    if c.valid_to is not None and c.valid_to < today:
        return "expired"
    return "active"


class ClearanceService(ScopedService):
    # --- загрузка пачками ------------------------------------------------------------------------

    async def _roles(
        self, role_ids: Iterable[uuid.UUID] | None = None
    ) -> dict[uuid.UUID, RoleInfo]:
        assigned = aliased(UnitProjection)
        stmt = (
            select(
                DutyRoleProjection,
                DutyTypeProjection,
                UnitProjection.path,
                UnitProjection.name,
                assigned.path,
                assigned.name,
            )
            .join(
                DutyTypeProjection,
                DutyTypeProjection.duty_type_id == DutyRoleProjection.duty_type_id,
            )
            .outerjoin(UnitProjection, UnitProjection.unit_id == DutyTypeProjection.owner_unit_id)
            .outerjoin(assigned, assigned.unit_id == DutyRoleProjection.assigned_unit_id)
        )
        if role_ids is not None:
            stmt = stmt.where(DutyRoleProjection.duty_role_id.in_(set(role_ids)))
        result = {}
        for role, duty_type, path, name, a_path, a_name in await self.session.execute(stmt):
            result[role.duty_role_id] = RoleInfo(
                role,
                duty_type,
                path,
                name,
                RoleRequirements.from_row(
                    role.min_rank_order,
                    role.allowed_position_ids,
                    role.attribute_requirements,
                    role.allowed_category_ids,
                ),
                a_path,
                a_name,
            )
        return result

    async def _traits(self, person_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, PersonTraits]:
        ids = set(person_ids)
        if not ids:
            return {}
        attrs: dict[uuid.UUID, dict[str, Any]] = defaultdict(dict)
        for pid, code, value in await self.session.execute(
            select(PersonAttribute.person_id, AttributeDefinition.code, PersonAttribute.value)
            .join(AttributeDefinition, AttributeDefinition.id == PersonAttribute.definition_id)
            .where(PersonAttribute.person_id.in_(ids))
        ):
            attrs[pid][code] = value["v"]
        rows = await self.session.execute(
            select(Person.id, RankProjection.order, Person.position_id, Person.category_id)
            .outerjoin(RankProjection, RankProjection.rank_id == Person.rank_id)
            .where(Person.id.in_(ids))
        )
        return {
            pid: PersonTraits(
                rank_order=order,
                position_id=pos,
                attributes=attrs.get(pid, {}),
                category_id=category,
            )
            for pid, order, pos, category in rows
        }

    async def _describer(self) -> Describer:
        ranks = list(await self.session.scalars(select(RankProjection)))
        positions = dict((await self.session.execute(select(Position.id, Position.name))).all())
        attributes = {a.code: a for a in await self.session.scalars(select(AttributeDefinition))}
        categories = dict(
            (await self.session.execute(select(PersonCategory.id, PersonCategory.name))).all()
        )
        return Describer(ranks, positions, attributes, categories)

    async def _person_path(self, person: Person) -> str:
        return (await self._unit(person.unit_id)).path

    # --- чтение ---------------------------------------------------------------------------------

    async def list_for_person(
        self, person_id: uuid.UUID, *, include_revoked: bool = False
    ) -> list[ClearanceOut]:
        person = await self._person(person_id, "clearance", "read")
        stmt = select(Clearance).where(Clearance.person_id == person.id)
        if not include_revoked:
            stmt = stmt.where(Clearance.revoked_at.is_(None))
        clearances = list(await self.session.scalars(stmt.order_by(Clearance.granted_at)))
        roles = await self._roles(c.duty_role_id for c in clearances)
        traits = (await self._traits([person.id]))[person.id]
        describer = await self._describer()
        today = dt.date.today()
        result = [
            self._out(c, roles.get(c.duty_role_id), traits, describer, today) for c in clearances
        ]
        order = {
            "active": 0,
            "future": 1,
            "category_mismatch": 2,
            "expired": 3,
            "role_inactive": 4,
            "revoked": 5,
        }
        result.sort(key=lambda c: (order[c.status], c.duty_type_name, c.role_name))
        return result

    @staticmethod
    def _out(
        c: Clearance,
        info: RoleInfo | None,
        traits: PersonTraits,
        describer: Describer,
        today: dt.date,
    ) -> ClearanceOut:
        status = status_of(c, info, today, traits)
        violations = (
            describer.out(check(traits, info.requirements), info.requirements)
            if info is not None and status in ("active", "future", "category_mismatch")
            else []
        )
        ref = (
            info.ref()
            if info is not None
            else {  # роль ещё не дошла до локальной копии или неизвестна
                "duty_role_id": c.duty_role_id,
                "role_name": "Неизвестная роль",
                "duty_type_id": None,
                "duty_type_name": "—",
                "owner_unit_id": None,
                "owner_unit_name": None,
                "assigned_unit_id": None,
                "assigned_unit_name": None,
            }
        )
        return ClearanceOut(
            **ref,
            id=c.id,
            person_id=c.person_id,
            valid_from=c.valid_from,
            valid_to=c.valid_to,
            status=status,
            overrides_requirements=c.overrides_requirements,
            override_comment=c.override_comment,
            granted_by_name=c.granted_by_name,
            granted_at=c.granted_at,
            revoked_at=c.revoked_at,
            violations=violations,
            version=c.version,
        )

    async def options(self, person_id: uuid.UUID) -> list[ClearanceOption]:
        """Роли, к которым человеку можно выдать допуск, с проверкой требований."""
        person = await self._person(person_id, "clearance", "read")
        path = await self._person_path(person)
        roles = [
            info
            for info in (await self._roles_covering(path)).values()
            if info.is_active and info.covers(path)
        ]
        traits = (await self._traits([person.id]))[person.id]
        describer = await self._describer()
        granted = set(
            await self.session.scalars(
                select(Clearance.duty_role_id).where(
                    Clearance.person_id == person.id, Clearance.revoked_at.is_(None)
                )
            )
        )
        result = [
            ClearanceOption(
                **info.ref(),
                sort_order=info.role.sort_order,
                has_requirements=not info.requirements.is_empty,
                violations=describer.out(check(traits, info.requirements), info.requirements),
                granted=info.role.duty_role_id in granted,
            )
            for info in roles
        ]
        result.sort(key=lambda o: (o.duty_type_name, o.sort_order, o.role_name))
        return result

    async def _roles_covering(self, unit_path: str) -> dict[uuid.UUID, RoleInfo]:
        ids = await self.session.scalars(
            select(DutyRoleProjection.duty_role_id)
            .join(
                DutyTypeProjection,
                DutyTypeProjection.duty_type_id == DutyRoleProjection.duty_type_id,
            )
            .join(UnitProjection, UnitProjection.unit_id == DutyTypeProjection.owner_unit_id)
            .where(is_ancestor_or_self(UnitProjection.path, unit_path))
        )
        return await self._roles(ids)

    async def roles_for_operator(self) -> list[ClearanceRoleOut]:
        """Действующие роли, допуски к которым оператор может выдавать своим людям: наряды
        вышестоящих подразделений и своего поддерева (для массовой выдачи)."""
        scope = self.policy.require(self.operator.roles, "clearance", "read")
        op_path = await self.operator_path()
        ids = await self.session.scalars(
            select(DutyRoleProjection.duty_role_id)
            .join(
                DutyTypeProjection,
                DutyTypeProjection.duty_type_id == DutyRoleProjection.duty_type_id,
            )
            .join(UnitProjection, UnitProjection.unit_id == DutyTypeProjection.owner_unit_id)
            .where(
                DutyRoleProjection.is_active,
                DutyTypeProjection.is_active,
                or_(
                    is_ancestor_or_self(UnitProjection.path, op_path),
                    scope_clause(UnitProjection.path, op_path, scope),
                ),
            )
        )
        roles = await self._roles(ids)
        result = [
            ClearanceRoleOut(
                **info.ref(),
                sort_order=info.role.sort_order,
                has_requirements=not info.requirements.is_empty,
            )
            for info in roles.values()
        ]
        result.sort(key=lambda o: (o.owner_unit_name or "", o.duty_type_name, o.sort_order))
        return result

    # --- выдача, изменение, отзыв -------------------------------------------------------------

    async def grant(self, person_id: uuid.UUID, data: ClearanceIn) -> Clearance:
        person = await self._person(person_id, "clearance", "grant")
        if not person.is_active:
            raise ValidationFailedError("Человек исключён из списков")
        info = (await self._roles([data.duty_role_id])).get(data.duty_role_id)
        if info is None or not info.is_active:
            raise ValidationFailedError("Роль наряда не найдена или не действует")
        if not info.covers(await self._person_path(person)):
            raise ValidationFailedError(info.not_covered_reason())
        existing = await self.session.scalar(
            select(Clearance.id).where(
                Clearance.person_id == person.id,
                Clearance.duty_role_id == data.duty_role_id,
                Clearance.revoked_at.is_(None),
            )
        )
        if existing is not None:
            raise ConflictError("Допуск на эту роль уже выдан — измените его срок или отзовите")

        traits = (await self._traits([person.id]))[person.id]
        violations = check(traits, info.requirements)
        hard = [v for v in violations if v.hard]
        if hard:
            described = (await self._describer()).out(hard, info.requirements)
            raise CategoryNotAllowedError(
                described[0].message, details={"violations": [v.model_dump() for v in described]}
            )
        if violations and not data.confirm_override:
            describer = await self._describer()
            raise RequirementsNotMetError(
                "Человек не проходит требования роли. Допуск можно выдать с подтверждением "
                "и комментарием.",
                details={
                    "violations": [
                        v.model_dump() for v in describer.out(violations, info.requirements)
                    ]
                },
            )
        clearance = self._new(person, data.duty_role_id, data, override=bool(violations))
        self.session.add(clearance)
        await self._flush()
        self._record_grant(clearance, person)
        await self._commit()
        return clearance

    def _new(
        self,
        person: Person,
        role_id: uuid.UUID,
        data: ClearanceIn | BulkClearanceIn,
        *,
        override: bool,
    ) -> Clearance:
        return Clearance(
            id=uuid7(),
            person_id=person.id,
            duty_role_id=role_id,
            valid_from=data.valid_from,
            valid_to=data.valid_to,
            overrides_requirements=override,
            override_comment=(data.override_comment or "").strip() if override else None,
            granted_by=self.operator.subject,
            granted_by_name=self.operator.full_name or self.operator.username,
        )

    def _record_grant(self, c: Clearance, person: Person) -> None:
        audit.record(
            self.session,
            action="clearance.grant_override" if c.overrides_requirements else "clearance.grant",
            entity_type="clearance",
            entity_id=c.id,
            scope_unit_id=person.unit_id,
            after=c.snapshot(),
            comment=c.override_comment,
            require_comment=c.overrides_requirements,
        )
        self._event("clearance.granted", c, person)

    def _event(self, event_type: str, c: Clearance, person: Person) -> None:
        add_event(
            self.session,
            event_type,
            "clearance",
            c.id,
            {
                "clearance_id": c.id,
                "person_id": person.id,
                "unit_id": person.unit_id,
                "duty_role_id": c.duty_role_id,
                "valid_from": c.valid_from,
                "valid_to": c.valid_to,
                "overrides_requirements": c.overrides_requirements,
            },
        )

    async def _clearance(self, clearance_id: uuid.UUID, action: str) -> tuple[Clearance, Person]:
        clearance = await self.session.get(Clearance, clearance_id)
        if clearance is None:
            raise NotFoundError("Допуск не найден")
        person = await self._person(clearance.person_id, "clearance", action)
        if clearance.revoked_at is not None:
            raise ValidationFailedError("Допуск уже отозван")
        return clearance, person

    async def update(self, clearance_id: uuid.UUID, data: ClearanceUpdate) -> Clearance:
        """Меняется только срок действия. Требования заново не проверяются: роль та же."""
        clearance, person = await self._clearance(clearance_id, "update")
        check_version(clearance.version, data.version)
        before = clearance.snapshot()
        clearance.valid_from = data.valid_from
        clearance.valid_to = data.valid_to
        await self._flush()
        if audit.record(
            self.session,
            action="clearance.update",
            entity_type="clearance",
            entity_id=clearance.id,
            scope_unit_id=person.unit_id,
            before=before,
            after=clearance.snapshot(),
        ):
            self._event("clearance.updated", clearance, person)
        await self._commit()
        return clearance

    async def revoke(self, clearance_id: uuid.UUID, data: RevokeIn) -> Clearance:
        clearance, person = await self._clearance(clearance_id, "revoke")
        before = clearance.snapshot()
        clearance.revoked_at = dt.datetime.now(dt.UTC)
        clearance.revoked_by = self.operator.subject
        await self._flush()
        audit.record(
            self.session,
            action="clearance.revoke",
            entity_type="clearance",
            entity_id=clearance.id,
            scope_unit_id=person.unit_id,
            before=before,
            after=clearance.snapshot(),
            comment=data.comment,
        )
        self._event("clearance.revoked", clearance, person)
        await self._commit()
        return clearance

    async def bulk(self, data: BulkClearanceIn) -> BulkClearanceResult:
        """Допуск группе людей на одну или несколько ролей (open-questions №16).

        Частичный успех: кому выдать нельзя, пропускаются с причиной. Не прошедшие требования
        без подтверждения тоже пропускаются, их число — в `needs_override`, чтобы UI предложил
        повторить выдачу с комментарием.
        """
        self.policy.require(self.operator.roles, "clearance", "grant")
        roles = await self._roles(data.duty_role_ids)
        people = {
            p.id: p
            for p in await self.session.scalars(
                select(Person).where(Person.id.in_(data.person_ids))
            )
        }
        paths = dict(
            (
                await self.session.execute(
                    select(UnitProjection.unit_id, UnitProjection.path).where(
                        UnitProjection.unit_id.in_({p.unit_id for p in people.values()})
                    )
                )
            ).all()
        )
        granted = {
            (pid, rid)
            for pid, rid in await self.session.execute(
                select(Clearance.person_id, Clearance.duty_role_id).where(
                    Clearance.person_id.in_(people),
                    Clearance.duty_role_id.in_(roles),
                    Clearance.revoked_at.is_(None),
                )
            )
        }
        traits = await self._traits(people)
        describer = await self._describer()
        op_path = await self.operator_path()
        scope = self._scope("clearance", "grant")
        result = BulkClearanceResult(done=0)

        def skip(pid: uuid.UUID, info: RoleInfo | None, reason: str, **extra: Any) -> None:
            p = people.get(pid)
            result.skipped.append(
                {
                    "person_id": str(pid),
                    "name": f"{p.last_name} {p.first_name}" if p else None,
                    "duty_role_id": str(info.role.duty_role_id) if info else None,
                    "role_name": f"{info.duty_type.name}: {info.role.name}" if info else None,
                    "reason": reason,
                    **extra,
                }
            )

        new: list[tuple[Clearance, Person]] = []
        for pid in dict.fromkeys(data.person_ids):
            person = people.get(pid)
            path = paths.get(person.unit_id) if person else None
            if person is None or path is None or not in_scope(path, op_path, scope):
                skip(pid, None, "Человек не найден или вне зоны ответственности")
                continue
            if not person.is_active:
                skip(pid, None, "Исключён из списков")
                continue
            for role_id in dict.fromkeys(data.duty_role_ids):
                info = roles.get(role_id)
                if info is None or not info.is_active:
                    skip(pid, None, "Роль наряда не найдена или не действует")
                    continue
                if not info.covers(path):
                    skip(pid, info, info.not_covered_reason())
                    continue
                if (pid, role_id) in granted:
                    skip(pid, info, "Допуск уже выдан")
                    continue
                violations = check(traits[pid], info.requirements)
                hard = [v for v in violations if v.hard]
                if hard:
                    skip(
                        pid,
                        info,
                        "Категория не допускается ролью",
                        violations=[v.message for v in describer.out(hard, info.requirements)],
                    )
                    continue
                if violations and not data.confirm_override:
                    result.needs_override += 1
                    skip(
                        pid,
                        info,
                        "Не проходит требования роли",
                        violations=[
                            v.message for v in describer.out(violations, info.requirements)
                        ],
                    )
                    continue
                new.append((self._new(person, role_id, data, override=bool(violations)), person))
        for clearance, _ in new:
            self.session.add(clearance)
        await self._flush()
        for clearance, person in new:
            self._record_grant(clearance, person)
        result.done = len(new)
        await self._commit()
        return result

    # --- отчёт о несоответствиях ----------------------------------------------------------------

    async def mismatches(
        self, unit_id: uuid.UUID | None, subtree: bool, page: PageParams
    ) -> Page[MismatchItem]:
        """Действующие допуски, которые сейчас не проходят требования роли: выданы вопреки
        требованиям или устарели после смены звания, должности, характеристик или требований.
        Несоответствие категории (допуск не действует) помечено `hard`."""
        scope = self.policy.require(self.operator.roles, "clearance", "read")
        today = dt.date.today()
        stmt = (
            select(Clearance, Person, UnitProjection.name)
            .join(Person, Person.id == Clearance.person_id)
            .join(UnitProjection, UnitProjection.unit_id == Person.unit_id)
            .join(DutyRoleProjection, DutyRoleProjection.duty_role_id == Clearance.duty_role_id)
            .join(
                DutyTypeProjection,
                DutyTypeProjection.duty_type_id == DutyRoleProjection.duty_type_id,
            )
            .where(
                scope_clause(UnitProjection.path, await self.operator_path(), scope),
                Person.is_active,
                Clearance.revoked_at.is_(None),
                or_(Clearance.valid_to.is_(None), Clearance.valid_to >= today),
                DutyRoleProjection.is_active,
                DutyTypeProjection.is_active,
            )
        )
        if unit_id is not None:
            unit = await self._unit(unit_id)
            stmt = stmt.where(
                is_descendant_or_self(UnitProjection.path, unit.path)
                if subtree
                else Person.unit_id == unit_id
            )
        rows = (await self.session.execute(stmt)).all()
        roles = await self._roles({c.duty_role_id for c, _, _ in rows})
        traits = await self._traits({p.id for _, p, _ in rows})
        describer = await self._describer()
        items: list[MismatchItem] = []
        for c, p, unit_name in rows:
            info = roles[c.duty_role_id]
            violations = check(traits[p.id], info.requirements)
            if not violations:
                continue
            items.append(
                MismatchItem(
                    **info.ref(),
                    clearance_id=c.id,
                    person_id=p.id,
                    person_name=" ".join(filter(None, [p.last_name, p.first_name, p.middle_name])),
                    unit_id=p.unit_id,
                    unit_name=unit_name,
                    overrides_requirements=c.overrides_requirements,
                    override_comment=c.override_comment,
                    valid_to=c.valid_to,
                    violations=describer.out(violations, info.requirements),
                )
            )
        items.sort(key=lambda i: (i.unit_name or "", i.person_name, i.duty_type_name, i.role_name))
        return Page(
            items=items[page.offset : page.offset + page.limit],
            total=len(items),
            limit=page.limit,
            offset=page.offset,
        )

    # --- вспомогательное -----------------------------------------------------------------------

    async def _flush(self) -> None:
        try:
            await self.session.flush()
        except StaleDataError as exc:
            await self.session.rollback()
            raise ConflictError("Допуск уже изменён другим пользователем") from exc
        except IntegrityError as exc:
            await self.session.rollback()
            if ACTIVE_CONSTRAINT in str(exc.orig):
                raise ConflictError("Допуск на эту роль уже выдан") from exc
            raise
