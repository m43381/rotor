"""Пакетный импорт личного состава, допусков и освобождений (фаза 6a).

Файл разбирает сервис `documents`, сюда приходят строки со значениями по ключам столбцов
шаблона. Ссылки — не идентификаторы, а понятные названия, которые этот же сервис отдаёт для
выпадающих списков шаблона (`template`): подразделение — путь от подразделения оператора
(«Факультет 1 / 1 курс»), роль — «Наряд — Роль», звание, должность, причина — по имени.

Одна и та же проверка работает в двух режимах:
- **предпросмотр** (`dry_run`): по каждой строке — создать / изменить (было → стало) /
  без изменений / ошибка, плюс хэш состояния;
- **применение**: проверка повторяется на свежих данных; если хэш не совпал с хэшем
  предпросмотра, ничего не применяется (409 `import_stale`). При ошибках применяется
  всё или ничего, если оператор явно не выбрал «только корректные строки» (open-questions
  №54). Всё — одной транзакцией, с аудитом и событием на каждую изменённую запись.

Сопоставление людей (№55): по личному номеру; без номера — по ФИО и подразделению. Удалений
и исключений из списков через импорт нет. Права — те же, что у одиночных операций, по
каждой строке. Справочники, люди, характеристики и допуски загружаются пачкой.
"""

import datetime as dt
import hashlib
import json
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from dutyflow_common import audit
from dutyflow_common.db import in_array
from dutyflow_common.errors import AppError, ValidationFailedError
from dutyflow_common.ids import uuid7
from dutyflow_common.outbox import add_event
from dutyflow_common.projections import RankProjection, UnitProjection
from dutyflow_common.requirements import check
from dutyflow_common.scope import Scope, in_scope
from personnel.attributes import normalize
from personnel.clearances import ClearanceService, RoleInfo
from personnel.models import (
    AttributeDefinition,
    Clearance,
    Exemption,
    ExemptionReason,
    Person,
    PersonAttribute,
    PersonCategory,
    Position,
)
from personnel.people import PeopleService, _event
from personnel.schemas import (
    ImportAction,
    ImportIn,
    ImportIssue,
    ImportKind,
    ImportOut,
    ImportRowIn,
    ImportRowOut,
    ImportTemplateOut,
    TemplateColumn,
)

SEP = " / "
DASH = " — "
TRUE = {"да", "true", "1", "+", "yes", "истина"}
FALSE = {"нет", "false", "0", "-", "no", "ложь"}


class ImportStaleError(AppError):
    status_code = 409
    code = "import_stale"


class RowError(Exception):
    def __init__(self, column: str | None, message: str) -> None:
        super().__init__(message)
        self.column = column
        self.message = message


# --- приведение значений из файла ----------------------------------------------------------------


def text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    result = str(value).strip()
    return result or None


def date(value: Any, column: str) -> dt.date | None:
    raw = text(value)
    if raw is None:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return dt.datetime.strptime(raw[:10] if fmt == "%Y-%m-%d" else raw, fmt).date()
        except ValueError:
            continue
    raise RowError(column, f"Не дата: «{raw}» (ожидается ДД.ММ.ГГГГ)")


def attribute_value(definition: AttributeDefinition, value: Any, column: str) -> Any:
    raw = text(value)
    if raw is None:
        return None
    converted: Any = raw
    match definition.value_type:
        case "bool":
            low = raw.lower()
            if low not in TRUE | FALSE:
                raise RowError(column, f"«{definition.name}»: ожидается да или нет")
            converted = low in TRUE
        case "int":
            try:
                converted = int(float(raw.replace(",", ".")))
            except ValueError as exc:
                raise RowError(column, f"«{definition.name}»: ожидается целое число") from exc
        case "date":
            parsed = date(value, column)
            converted = parsed.isoformat() if parsed else None
    try:
        return normalize(definition, converted)
    except ValidationFailedError as exc:
        raise RowError(column, exc.message) from exc


# --- справочники оператора -----------------------------------------------------------------------


@dataclass
class Refs:
    units: dict[str, UnitProjection]  # подпись → подразделение
    unit_label: dict[uuid.UUID, str]
    unit_path: dict[uuid.UUID, str]
    ranks: dict[str, uuid.UUID]
    rank_name: dict[uuid.UUID, str]
    positions: dict[str, uuid.UUID]
    position_name: dict[uuid.UUID, str]
    categories: dict[str, uuid.UUID]
    category_name: dict[uuid.UUID, str]
    reasons: dict[str, uuid.UUID]
    attributes: dict[str, AttributeDefinition]  # по коду
    roles: dict[str, RoleInfo] = field(default_factory=dict)  # подпись → роль
    ambiguous: set[str] = field(default_factory=set)


@dataclass
class Planned:
    """Проверенная строка и что с ней сделать при применении."""

    out: ImportRowOut
    # Изменение в два этапа: `apply` добавляет и меняет объекты, после одного общего flush
    # возвращённая им функция пишет аудит и события (им нужны id и версии записей)
    apply: Callable[[], Awaitable[Callable[[], None]]] | None = None


class ImportService(PeopleService):
    """Импорт — операции над людьми, допусками и освобождениями, поэтому сервис наследует
    PeopleService (аудит освобождений, события) и пользуется ClearanceService для ролей."""

    # --- шаблоны ----------------------------------------------------------------------------

    async def template(self, kind: ImportKind) -> ImportTemplateOut:
        refs = await self._refs(kind)
        person_cols = [
            TemplateColumn(
                key="personal_no",
                title="Личный номер",
                hint="По нему строка находит человека; без номера человек ищется по ФИО и "
                "подразделению" + (" или создаётся новый" if kind == "people" else ""),
            ),
            TemplateColumn(key="last_name", title="Фамилия", required=kind == "people"),
            TemplateColumn(key="first_name", title="Имя", required=kind == "people"),
            TemplateColumn(key="middle_name", title="Отчество"),
            TemplateColumn(
                key="unit",
                title="Подразделение",
                required=kind == "people",
                type="list",
                options=sorted(refs.units),
            ),
        ]
        if kind == "people":
            columns = [
                *person_cols,
                TemplateColumn(key="rank", title="Звание", type="list", options=sorted(refs.ranks)),
                TemplateColumn(
                    key="position", title="Должность", type="list", options=sorted(refs.positions)
                ),
                TemplateColumn(
                    key="category",
                    title="Категория",
                    required=True,
                    type="list",
                    options=list(refs.categories),
                    hint="Курсант, слушатель, постоянный состав… — от неё зависит, в какие "
                    "роли нарядов человек может заступать",
                ),
                TemplateColumn(key="note", title="Примечание"),
            ]
            for d in sorted(refs.attributes.values(), key=lambda d: (d.sort_order, d.name)):
                if not d.is_active:
                    continue
                columns.append(
                    TemplateColumn(
                        key=f"attr:{d.code}",
                        title=d.name,
                        required=d.is_required,
                        type={"bool": "bool", "int": "int", "date": "date", "enum": "list"}.get(
                            d.value_type, "text"
                        ),
                        options=list(d.enum_options or [])
                        if d.value_type == "enum"
                        else (["да", "нет"] if d.value_type == "bool" else None),
                    )
                )
            return ImportTemplateOut(
                kind=kind,
                title="Личный состав",
                columns=columns,
                instructions=[
                    "Одна строка — один человек. Обязательные столбцы отмечены звёздочкой.",
                    "Строка с известным личным номером изменяет карточку: заполненные ячейки "
                    "заменяют значения, пустые оставляют как есть. Смена подразделения — перевод.",
                    "Строка без личного номера создаёт нового человека; если такой человек уже "
                    "есть в подразделении, предпросмотр предупредит о возможном дубликате.",
                    "Исключать из списков через импорт нельзя — только вручную.",
                ],
            )
        if kind == "clearances":
            return ImportTemplateOut(
                kind=kind,
                title="Допуски",
                columns=[
                    *person_cols,
                    TemplateColumn(
                        key="role",
                        title="Наряд и роль",
                        required=True,
                        type="list",
                        options=sorted(refs.roles),
                    ),
                    TemplateColumn(key="valid_from", title="Действует с", type="date"),
                    TemplateColumn(key="valid_to", title="Действует по", type="date"),
                    TemplateColumn(
                        key="override_comment",
                        title="Основание выдачи вопреки требованиям",
                        hint="Заполняется, только если человек не проходит требования роли",
                    ),
                ],
                instructions=[
                    "Одна строка — один допуск человека к роли наряда.",
                    "Если допуск к роли уже выдан, строка меняет его срок действия.",
                    "Если человек не проходит требования роли, строка — ошибка, пока не указано "
                    "основание выдачи вопреки требованиям.",
                ],
            )
        return ImportTemplateOut(
            kind=kind,
            title="Освобождения",
            columns=[
                *person_cols,
                TemplateColumn(
                    key="reason",
                    title="Причина",
                    required=True,
                    type="list",
                    options=sorted(refs.reasons),
                ),
                TemplateColumn(key="date_from", title="С", required=True, type="date"),
                TemplateColumn(key="date_to", title="По", required=True, type="date"),
                TemplateColumn(key="comment", title="Комментарий"),
            ],
            instructions=[
                "Одна строка — одно освобождение человека на период.",
                "Период не должен пересекаться с уже внесёнными освобождениями этого человека.",
            ],
        )

    async def _refs(self, kind: ImportKind) -> Refs:
        """Справочники с подписями, какие видит оператор. Подпись подразделения — путь от
        подразделения оператора (для всей организации — от корня)."""
        scope = self._scope("person", "read")
        op_path = await self.operator_path()
        all_units = list(await self.session.scalars(select(UnitProjection)))
        name_by_path = {u.path: u.name for u in all_units}
        start = 0 if scope == Scope.ALL else op_path.count(".")
        units: dict[str, UnitProjection] = {}
        labels: dict[uuid.UUID, str] = {}
        ambiguous: set[str] = set()
        for u in all_units:
            if not u.is_active or not in_scope(u.path, op_path, scope):
                continue
            parts = u.path.split(".")
            label = SEP.join(
                name_by_path.get(".".join(parts[: i + 1]), "?") for i in range(start, len(parts))
            )
            labels[u.unit_id] = label
            if label in units:
                ambiguous.add(label)
            units[label] = u
        ranks = list(await self.session.scalars(select(RankProjection)))
        positions = list(await self.session.scalars(select(Position)))
        categories = list(
            await self.session.scalars(
                select(PersonCategory).order_by(PersonCategory.sort_order, PersonCategory.name)
            )
        )
        reasons = list(await self.session.scalars(select(ExemptionReason)))
        refs = Refs(
            units=units,
            unit_label=labels,
            unit_path={u.unit_id: u.path for u in all_units},
            ranks={r.name: r.rank_id for r in ranks if r.is_active},
            rank_name={r.rank_id: r.name for r in ranks},
            positions={p.name: p.id for p in positions if p.is_active},
            position_name={p.id: p.name for p in positions},
            categories={c.name: c.id for c in categories if c.is_active},
            category_name={c.id: c.name for c in categories},
            reasons={r.name: r.id for r in reasons if r.is_active},
            attributes={a.code: a for a in await self.session.scalars(select(AttributeDefinition))},
            ambiguous=ambiguous,
        )
        if kind == "clearances":
            clearances = ClearanceService(self.session, self.operator, self.policy)
            options = await clearances.roles_for_operator()
            infos = await clearances._roles([o.duty_role_id for o in options])
            base = defaultdict(list)
            for o in options:
                base[f"{o.duty_type_name}{DASH}{o.role_name}"].append(o)
            for label, items in base.items():
                for o in items:
                    full = label if len(items) == 1 else f"{label} ({o.owner_unit_name})"
                    refs.roles[full] = infos[o.duty_role_id]
        return refs

    # --- проверка и применение ---------------------------------------------------------------

    async def run(self, kind: ImportKind, data: ImportIn) -> ImportOut:
        refs = await self._refs(kind)
        rows = sorted(data.rows, key=lambda r: r.row)
        if kind == "people":
            planned = await self._people(rows, refs)
        elif kind == "clearances":
            planned = await self._clearances(rows, refs)
        else:
            planned = await self._exemptions(rows, refs)
        outs = [p.out for p in planned]
        state_hash = _hash(kind, outs)
        summary: dict[ImportAction, int] = {"create": 0, "update": 0, "unchanged": 0, "error": 0}
        for o in outs:
            summary[o.action] += 1
        if data.dry_run:
            return ImportOut(
                kind=kind, applied=False, summary=summary, rows=outs, state_hash=state_hash
            )
        if data.expected_hash and data.expected_hash != state_hash:
            raise ImportStaleError(
                "После проверки данные изменились. Проверьте файл заново перед применением."
            )
        if summary["error"] and not data.skip_invalid:
            raise ValidationFailedError(
                f"В файле {summary['error']} строк с ошибками. Исправьте их или примените "
                "только корректные строки."
            )
        finish = [await p.apply() for p in planned if p.apply is not None]
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ImportStaleError(
                "Данные изменились во время применения. Проверьте файл заново."
            ) from exc
        for f in finish:
            f()
        await self._commit()
        return ImportOut(kind=kind, applied=True, summary=summary, rows=outs, state_hash=state_hash)

    # --- общие части строк -------------------------------------------------------------------

    def _unit_ref(self, refs: Refs, value: Any) -> UnitProjection | None:
        label = text(value)
        if label is None:
            return None
        if label in refs.ambiguous:
            raise RowError("unit", f"Подразделений «{label}» несколько — уточните в справочнике")
        unit = refs.units.get(label)
        if unit is None:
            raise RowError("unit", f"Подразделение «{label}» не найдено или вне вашей зоны")
        return unit

    def _allowed(self, refs: Refs, unit_id: uuid.UUID, resource: str, action: str) -> bool:
        path = refs.unit_path.get(unit_id)
        return path is not None and in_scope(
            path, self._op_path or "", self._scope(resource, action)
        )

    async def _find_people(
        self, rows: list[ImportRowIn], refs: Refs
    ) -> tuple[dict[str, Person], dict[tuple[uuid.UUID, str, str, str], list[Person]]]:
        """Люди по личным номерам из файла и по (подразделение, ФИО) — пачкой."""
        numbers = {n for r in rows if (n := text(r.values.get("personal_no")))}
        by_no: dict[str, Person] = {}
        if numbers:
            for p in await self.session.scalars(
                select(Person).where(in_array(Person.personal_no, numbers))
            ):
                by_no[p.personal_no or ""] = p
        unit_ids = set()
        for r in rows:
            label = text(r.values.get("unit"))
            if label and label in refs.units:
                unit_ids.add(refs.units[label].unit_id)
        by_name: dict[tuple[uuid.UUID, str, str, str], list[Person]] = defaultdict(list)
        if unit_ids:
            for p in await self.session.scalars(
                select(Person).where(in_array(Person.unit_id, unit_ids), Person.is_active)
            ):
                by_name[_fio_key(p.unit_id, p.last_name, p.first_name, p.middle_name)].append(p)
        return by_no, by_name

    def _identify(
        self,
        row: ImportRowIn,
        refs: Refs,
        by_no: dict[str, Person],
        by_name: dict[tuple[uuid.UUID, str, str, str], list[Person]],
    ) -> Person:
        number = text(row.values.get("personal_no"))
        if number:
            person = by_no.get(number)
            if person is None:
                raise RowError("personal_no", f"Человек с личным номером «{number}» не найден")
        else:
            last, first = text(row.values.get("last_name")), text(row.values.get("first_name"))
            unit = self._unit_ref(refs, row.values.get("unit"))
            if not (last and first and unit):
                raise RowError(
                    "personal_no",
                    "Укажите личный номер или фамилию, имя и подразделение человека",
                )
            found = by_name.get(
                _fio_key(unit.unit_id, last, first, text(row.values.get("middle_name")))
            )
            if not found:
                raise RowError("last_name", "Человек с такими ФИО в подразделении не найден")
            if len(found) > 1:
                raise RowError("last_name", "Людей с такими ФИО несколько — укажите личный номер")
            person = found[0]
        if not person.is_active:
            raise RowError("personal_no", "Человек исключён из списков")
        return person

    # --- личный состав -------------------------------------------------------------------------

    async def _people(self, rows: list[ImportRowIn], refs: Refs) -> list[Planned]:
        await self.operator_path()
        by_no, by_name = await self._find_people(rows, refs)
        current_attrs: dict[uuid.UUID, dict[str, Any]] = defaultdict(dict)
        existing_ids = [p.id for p in by_no.values()]
        if existing_ids:
            for pid, code, value in await self.session.execute(
                select(PersonAttribute.person_id, AttributeDefinition.code, PersonAttribute.value)
                .join(AttributeDefinition, AttributeDefinition.id == PersonAttribute.definition_id)
                .where(in_array(PersonAttribute.person_id, existing_ids))
            ):
                current_attrs[pid][code] = value["v"]
        seen_numbers: dict[str, int] = {}
        seen_names: dict[tuple[uuid.UUID, str, str, str], int] = {}
        planned = []
        for row in rows:
            out = ImportRowOut(row=row.row, action="error")
            v = row.values
            try:
                number = text(v.get("personal_no"))
                last, first = text(v.get("last_name")), text(v.get("first_name"))
                middle, note = text(v.get("middle_name")), text(v.get("note"))
                out.label = " ".join(x for x in (last, first, middle) if x) or number
                if number and number in seen_numbers:
                    raise RowError(
                        "personal_no", f"Личный номер повторяется в строке {seen_numbers[number]}"
                    )
                unit = self._unit_ref(refs, v.get("unit"))
                rank_id = self._ref(refs.ranks, v.get("rank"), "rank", "Звание")
                position_id = self._ref(refs.positions, v.get("position"), "position", "Должность")
                category_id = self._ref(refs.categories, v.get("category"), "category", "Категория")
                attrs: dict[str, Any] = {}
                for key, raw in v.items():
                    if not key.startswith("attr:"):
                        continue
                    definition = refs.attributes.get(key[5:])
                    if definition is None or not definition.is_active:
                        raise RowError(key, "Характеристика не используется")
                    value = attribute_value(definition, raw, key)
                    if value is not None:
                        attrs[definition.code] = value
                for column, value in (("last_name", last), ("first_name", first)):
                    if value and len(value) > 100:
                        raise RowError(column, "Не длиннее 100 символов")
                existing = by_no.get(number) if number else None
                if existing is not None:
                    planned.append(
                        self._update_person(
                            out, existing, refs, unit, last, first, middle, note,
                            rank_id, position_id, category_id, attrs, current_attrs[existing.id],
                        )
                    )  # fmt: skip
                else:
                    planned.append(
                        self._create_person(
                            out, refs, number, unit, last, first, middle, note,
                            rank_id, position_id, category_id, attrs, by_name, seen_names,
                        )
                    )  # fmt: skip
                if number:
                    seen_numbers[number] = row.row
            except RowError as exc:
                out.action = "error"
                out.errors.append(ImportIssue(column=exc.column, message=exc.message))
                planned.append(Planned(out))
        return planned

    @staticmethod
    def _ref(options: dict[str, uuid.UUID], value: Any, column: str, name: str) -> uuid.UUID | None:
        label = text(value)
        if label is None:
            return None
        if label not in options:
            raise RowError(column, f"{name} «{label}» не найдено в справочнике")
        return options[label]

    def _create_person(
        self,
        out: ImportRowOut,
        refs: Refs,
        number: str | None,
        unit: UnitProjection | None,
        last: str | None,
        first: str | None,
        middle: str | None,
        note: str | None,
        rank_id: uuid.UUID | None,
        position_id: uuid.UUID | None,
        category_id: uuid.UUID | None,
        attrs: dict[str, Any],
        by_name: dict[tuple[uuid.UUID, str, str, str], list[Person]],
        seen_names: dict[tuple[uuid.UUID, str, str, str], int],
    ) -> Planned:
        if not last:
            raise RowError("last_name", "Фамилия обязательна")
        if not first:
            raise RowError("first_name", "Имя обязательно")
        if unit is None:
            raise RowError("unit", "Подразделение обязательно для нового человека")
        if category_id is None:
            raise RowError("category", "Категория обязательна для нового человека")
        if not self._allowed(refs, unit.unit_id, "person", "create"):
            raise RowError("unit", "Нет прав добавлять людей в это подразделение")
        missing = [
            d.name
            for d in refs.attributes.values()
            if d.is_required and d.is_active and d.code not in attrs
        ]
        if missing:
            raise RowError(f"attr:{missing[0]}", f"Не заполнено: {', '.join(missing)}")
        key = _fio_key(unit.unit_id, last, first, middle)
        if by_name.get(key):
            out.warnings.append(
                ImportIssue(
                    column="last_name",
                    message="В подразделении уже есть человек с такими ФИО — возможен дубликат",
                )
            )
        if key in seen_names:
            out.warnings.append(
                ImportIssue(
                    column="last_name",
                    message=f"Такой же человек уже есть в строке {seen_names[key]}",
                )
            )
        seen_names.setdefault(key, out.row)
        out.action = "create"

        async def apply() -> Callable[[], None]:
            person = Person(
                id=uuid7(),
                unit_id=unit.unit_id,
                last_name=last,
                first_name=first,
                middle_name=middle,
                rank_id=rank_id,
                position_id=position_id,
                category_id=category_id,
                personal_no=number,
                note=note,
                is_active=True,
            )
            self.session.add(person)
            for code, value in attrs.items():
                self.session.add(
                    PersonAttribute(
                        person_id=person.id,
                        definition_id=refs.attributes[code].id,
                        value={"v": value},
                    )
                )

            def finish() -> None:
                audit.record(
                    self.session,
                    action="person.create",
                    entity_type="person",
                    entity_id=person.id,
                    scope_unit_id=person.unit_id,
                    after={**person.snapshot(), "attributes": attrs},
                    comment="Импорт",
                )
                add_event(self.session, "person.created", "person", person.id, _event(person))

            return finish

        return Planned(out, apply)

    def _update_person(
        self,
        out: ImportRowOut,
        person: Person,
        refs: Refs,
        unit: UnitProjection | None,
        last: str | None,
        first: str | None,
        middle: str | None,
        note: str | None,
        rank_id: uuid.UUID | None,
        position_id: uuid.UUID | None,
        category_id: uuid.UUID | None,
        attrs: dict[str, Any],
        current: dict[str, Any],
    ) -> Planned:
        if not person.is_active:
            raise RowError("personal_no", "Человек исключён из списков — восстановите его вручную")
        if not self._allowed(refs, person.unit_id, "person", "update"):
            raise RowError("personal_no", "Человек вне вашей зоны ответственности")
        out.label = f"{person.last_name} {person.first_name} {person.middle_name or ''}".strip()
        fields: dict[str, Any] = {}
        changes: dict[str, list[Any]] = {}
        show: dict[uuid.UUID, str] | None
        new: Any
        for name, new, title, show in (
            ("last_name", last, "Фамилия", None),
            ("first_name", first, "Имя", None),
            ("middle_name", middle, "Отчество", None),
            ("note", note, "Примечание", None),
            ("rank_id", rank_id, "Звание", refs.rank_name),
            ("position_id", position_id, "Должность", refs.position_name),
            ("category_id", category_id, "Категория", refs.category_name),
        ):
            old = getattr(person, name)
            if new is not None and new != old:
                fields[name] = new
                changes[title] = [
                    show.get(old) if show and old else old,
                    show.get(new) if show else new,
                ]
        attr_changes = {c: v for c, v in attrs.items() if current.get(c) != v}
        for code, value in attr_changes.items():
            changes[refs.attributes[code].name] = [current.get(code), value]
        target = unit.unit_id if unit is not None and unit.unit_id != person.unit_id else None
        if target is not None:
            if not self._allowed(refs, person.unit_id, "person", "transfer") or not self._allowed(
                refs, target, "person", "create"
            ):
                raise RowError("unit", "Нет прав перевести человека в это подразделение")
            changes["Подразделение"] = [
                refs.unit_label.get(person.unit_id),
                refs.unit_label[target],
            ]
        out.changes = changes
        out.action = "update" if changes else "unchanged"
        if not changes:
            return Planned(out)

        async def apply() -> Callable[[], None]:
            before = person.snapshot()
            for name, value in fields.items():
                setattr(person, name, value)
            for code, value in attr_changes.items():
                definition = refs.attributes[code]
                row = await self.session.get(PersonAttribute, (person.id, definition.id))
                if row is None:
                    self.session.add(
                        PersonAttribute(
                            person_id=person.id, definition_id=definition.id, value={"v": value}
                        )
                    )
                else:
                    row.value = {"v": value}
            if target is not None:
                person.unit_id = target
            person.updated_at = func.now()

            def finish() -> None:
                after = person.snapshot()
                if attr_changes:
                    before["attributes"] = {c: current.get(c) for c in attr_changes}
                    after["attributes"] = attr_changes
                audit.record(
                    self.session,
                    action="person.update" if fields or attr_changes else "person.transfer",
                    entity_type="person",
                    entity_id=person.id,
                    scope_unit_id=person.unit_id,
                    before=before,
                    after=after,
                    comment="Импорт",
                )
                if target is not None:
                    add_event(
                        self.session,
                        "person.transferred",
                        "person",
                        person.id,
                        {**_event(person), "from_unit_id": before["unit_id"]},
                    )
                if fields or attr_changes:
                    add_event(self.session, "person.updated", "person", person.id, _event(person))

            return finish

        return Planned(out, apply)

    # --- допуски ---------------------------------------------------------------------------------

    async def _clearances(self, rows: list[ImportRowIn], refs: Refs) -> list[Planned]:
        await self.operator_path()
        by_no, by_name = await self._find_people(rows, refs)
        clearances = ClearanceService(self.session, self.operator, self.policy)
        people_ids = {p.id for p in by_no.values()} | {
            p.id for group in by_name.values() for p in group
        }
        active: dict[tuple[uuid.UUID, uuid.UUID], Clearance] = {}
        if people_ids:
            for c in await self.session.scalars(
                select(Clearance).where(
                    in_array(Clearance.person_id, people_ids), Clearance.revoked_at.is_(None)
                )
            ):
                active[(c.person_id, c.duty_role_id)] = c
        traits = await clearances._traits(people_ids)
        describer = await clearances._describer()
        seen: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
        planned = []
        for row in rows:
            out = ImportRowOut(row=row.row, action="error")
            v = row.values
            try:
                person = self._identify(row, refs, by_no, by_name)
                out.label = _label(person)
                role_label = text(v.get("role"))
                if role_label is None:
                    raise RowError("role", "Укажите наряд и роль")
                info = refs.roles.get(role_label)
                if info is None or not info.is_active:
                    raise RowError("role", f"Роль «{role_label}» не найдена или не действует")
                if not info.covers(refs.unit_path.get(person.unit_id, "")):
                    raise RowError("role", info.not_covered_reason())
                valid_from = date(v.get("valid_from"), "valid_from")
                valid_to = date(v.get("valid_to"), "valid_to")
                if valid_from and valid_to and valid_to < valid_from:
                    raise RowError("valid_to", "Дата окончания раньше даты начала")
                key = (person.id, info.role.duty_role_id)
                if key in seen:
                    raise RowError("role", f"Этот допуск уже есть в строке {seen[key]}")
                seen[key] = row.row
                existing = active.get(key)
                if existing is not None:
                    planned.append(
                        self._update_clearance(out, refs, clearances, existing, person,
                                               valid_from, valid_to)
                    )  # fmt: skip
                    continue
                if not self._allowed(refs, person.unit_id, "clearance", "grant"):
                    raise RowError("personal_no", "Нет прав выдавать допуски этому человеку")
                violations = check(traits[person.id], info.requirements)
                hard = [x for x in violations if x.hard]
                if hard:  # категория не перекрывается основанием (ADR-0018)
                    raise RowError("role", describer.out(hard, info.requirements)[0].message)
                comment = text(v.get("override_comment"))
                if violations and not comment:
                    raise RowError(
                        "role",
                        "Не проходит требования роли: "
                        + "; ".join(x.message for x in describer.out(violations, info.requirements))
                        + ". Укажите основание выдачи вопреки требованиям.",
                    )
                if violations:
                    out.warnings.append(
                        ImportIssue(column="role", message="Выдаётся вопреки требованиям роли")
                    )
                out.action = "create"
                planned.append(
                    Planned(
                        out,
                        _grant(clearances, person, info, valid_from, valid_to, violations, comment),
                    )
                )
            except RowError as exc:
                out.errors.append(ImportIssue(column=exc.column, message=exc.message))
                planned.append(Planned(out))
        return planned

    def _update_clearance(
        self,
        out: ImportRowOut,
        refs: Refs,
        clearances: ClearanceService,
        c: Clearance,
        person: Person,
        valid_from: dt.date | None,
        valid_to: dt.date | None,
    ) -> Planned:
        if (c.valid_from, c.valid_to) == (valid_from, valid_to):
            out.action = "unchanged"
            return Planned(out)
        if not self._allowed(refs, person.unit_id, "clearance", "update"):
            raise RowError("personal_no", "Нет прав менять допуски этому человеку")
        out.action = "update"
        out.changes = {
            "Срок действия": [_period(c.valid_from, c.valid_to), _period(valid_from, valid_to)]
        }

        async def apply() -> Callable[[], None]:
            before = c.snapshot()
            c.valid_from, c.valid_to = valid_from, valid_to

            def finish() -> None:
                audit.record(
                    self.session,
                    action="clearance.update",
                    entity_type="clearance",
                    entity_id=c.id,
                    scope_unit_id=person.unit_id,
                    before=before,
                    after=c.snapshot(),
                    comment="Импорт",
                )
                clearances._event("clearance.updated", c, person)

            return finish

        return Planned(out, apply)

    # --- освобождения ---------------------------------------------------------------------------

    async def _exemptions(self, rows: list[ImportRowIn], refs: Refs) -> list[Planned]:
        await self.operator_path()
        by_no, by_name = await self._find_people(rows, refs)
        people_ids = {p.id for p in by_no.values()} | {
            p.id for group in by_name.values() for p in group
        }
        periods: dict[uuid.UUID, list[tuple[dt.date, dt.date, uuid.UUID, int | None]]] = (
            defaultdict(list)
        )
        if people_ids:
            for e in await self.session.scalars(
                select(Exemption).where(in_array(Exemption.person_id, people_ids))
            ):
                periods[e.person_id].append((e.date_from, e.date_to, e.reason_id, None))
        planned = []
        for row in rows:
            out = ImportRowOut(row=row.row, action="error")
            v = row.values
            try:
                person = self._identify(row, refs, by_no, by_name)
                out.label = _label(person)
                if not self._allowed(refs, person.unit_id, "exemption", "create"):
                    raise RowError("personal_no", "Нет прав вносить освобождения этому человеку")
                reason_id = self._ref(refs.reasons, v.get("reason"), "reason", "Причина")
                if reason_id is None:
                    raise RowError("reason", "Укажите причину")
                date_from = date(v.get("date_from"), "date_from")
                date_to = date(v.get("date_to"), "date_to")
                if date_from is None:
                    raise RowError("date_from", "Укажите дату начала")
                if date_to is None:
                    raise RowError("date_to", "Укажите дату окончания")
                if date_to < date_from:
                    raise RowError("date_to", "Дата окончания раньше даты начала")
                comment = text(v.get("comment"))
                same = [p for p in periods[person.id] if p[0] <= date_to and p[1] >= date_from]
                if any(p[:3] == (date_from, date_to, reason_id) and p[3] is None for p in same):
                    out.action = "unchanged"
                    planned.append(Planned(out))
                    continue
                if same:
                    where = next((p[3] for p in same if p[3] is not None), None)
                    raise RowError(
                        "date_from",
                        f"Период пересекается с освобождением из строки {where}"
                        if where
                        else "Период пересекается с уже внесённым освобождением",
                    )
                periods[person.id].append((date_from, date_to, reason_id, row.row))
                out.action = "create"
                planned.append(
                    Planned(
                        out, self._add_exemption(person, reason_id, date_from, date_to, comment)
                    )
                )
            except RowError as exc:
                out.errors.append(ImportIssue(column=exc.column, message=exc.message))
                planned.append(Planned(out))
        return planned

    def _add_exemption(
        self,
        person: Person,
        reason_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
        comment: str | None,
    ) -> Callable[[], Awaitable[Callable[[], None]]]:
        async def apply() -> Callable[[], None]:
            exemption = Exemption(
                id=uuid7(),
                person_id=person.id,
                reason_id=reason_id,
                date_from=date_from,
                date_to=date_to,
                comment=comment,
                created_by=self.operator.subject,
            )
            self.session.add(exemption)
            return lambda: self._audit_exemption(
                "exemption.create", exemption, person, after=exemption.snapshot()
            )

        return apply


def _grant(
    clearances: ClearanceService,
    person: Person,
    info: RoleInfo,
    valid_from: dt.date | None,
    valid_to: dt.date | None,
    violations: list[Any],
    comment: str | None,
) -> Callable[[], Awaitable[Callable[[], None]]]:
    async def apply() -> Callable[[], None]:
        c = Clearance(
            id=uuid7(),
            person_id=person.id,
            duty_role_id=info.role.duty_role_id,
            valid_from=valid_from,
            valid_to=valid_to,
            overrides_requirements=bool(violations),
            override_comment=comment if violations else None,
            granted_by=clearances.operator.subject,
            granted_by_name=clearances.operator.full_name or clearances.operator.username,
        )
        clearances.session.add(c)
        return lambda: clearances._record_grant(c, person)

    return apply


def _fio_key(
    unit_id: uuid.UUID, last: str, first: str, middle: str | None
) -> tuple[uuid.UUID, str, str, str]:
    return (unit_id, last.strip().lower(), first.strip().lower(), (middle or "").strip().lower())


def _label(p: Person) -> str:
    return " ".join(x for x in (p.last_name, p.first_name, p.middle_name) if x)


def _period(a: dt.date | None, b: dt.date | None) -> str:
    fmt = "%d.%m.%Y"
    return f"{a.strftime(fmt) if a else '…'} – {b.strftime(fmt) if b else '…'}"


def _hash(kind: str, rows: Iterable[ImportRowOut]) -> str:
    content = [kind, [r.model_dump(mode="json") for r in rows]]
    return hashlib.sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
