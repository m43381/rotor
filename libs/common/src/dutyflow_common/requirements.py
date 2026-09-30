"""Требования роли наряда к человеку и их проверка (ADR-0009).

Требования хранит `scheduling` (`duty_role`), проверяет `personnel` при выдаче допуска и в отчёте
о несоответствиях. Модуль — чистые функции без БД: одинаковый код для обеих сторон и для тестов.

Категория личного состава (ADR-0018) — отдельное жёсткое требование: в отличие от звания,
должности и характеристик, допуск-исключение её не перекрывает (`Violation.hard`).

Требование к характеристике ссылается на `AttributeDefinition.code` (ADR-0005). Операторы:
- `eq` — значение равно заданному;
- `in` — значение входит в список;
- `gte`, `lte` — не меньше / не больше (числа и даты; даты хранятся строкой ГГГГ-ММ-ДД,
  поэтому сравниваются лексикографически).
"""

import datetime as dt
import uuid
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

type Op = Literal["eq", "in", "gte", "lte"]

OP_LABELS: dict[str, str] = {"eq": "равно", "in": "одно из", "gte": "не меньше", "lte": "не больше"}
ORDERED_TYPES = frozenset({"int", "date"})


class AttributeRequirement(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    op: Op
    value: Any


@dataclass(frozen=True, slots=True)
class RoleRequirements:
    min_rank_order: int | None = None
    # None — подходит любая должность
    allowed_position_ids: frozenset[uuid.UUID] | None = None
    attributes: tuple[AttributeRequirement, ...] = ()
    # None — подходит любая категория
    allowed_category_ids: frozenset[uuid.UUID] | None = None

    @classmethod
    def from_row(
        cls,
        min_rank_order: int | None,
        allowed_position_ids: Collection[uuid.UUID] | None,
        attribute_requirements: Sequence[Mapping[str, Any]] | None,
        allowed_category_ids: Collection[uuid.UUID] | None = None,
    ) -> "RoleRequirements":
        return cls(
            min_rank_order=min_rank_order,
            allowed_position_ids=(
                frozenset(allowed_position_ids) if allowed_position_ids is not None else None
            ),
            attributes=tuple(
                AttributeRequirement.model_validate(r) for r in attribute_requirements or []
            ),
            allowed_category_ids=(
                frozenset(allowed_category_ids) if allowed_category_ids is not None else None
            ),
        )

    @property
    def is_empty(self) -> bool:
        return (
            self.min_rank_order is None
            and not self.allowed_position_ids
            and not self.attributes
            and not self.allowed_category_ids
        )


@dataclass(frozen=True, slots=True)
class PersonTraits:
    rank_order: int | None
    position_id: uuid.UUID | None
    attributes: Mapping[str, Any]
    category_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class Violation:
    """Нарушенное требование. `kind`: category / rank / position / attribute; `code` — код
    характеристики."""

    kind: Literal["category", "rank", "position", "attribute"]
    code: str | None
    expected: Any
    actual: Any

    @property
    def hard(self) -> bool:
        """Категорию допуск-исключение не перекрывает (ADR-0018)."""
        return self.kind == "category"


def _attribute_ok(req: AttributeRequirement, actual: Any) -> bool:
    if actual is None:
        return False
    try:
        match req.op:
            case "eq":
                return bool(actual == req.value)
            case "in":
                return actual in (req.value or [])
            case "gte":
                return bool(actual >= req.value)
            case "lte":
                return bool(actual <= req.value)
    except TypeError:  # несравнимые типы (значение сменило тип) — требование не выполнено
        return False
    return False  # pragma: no cover — Literal исчерпан


def check(person: PersonTraits, req: RoleRequirements) -> list[Violation]:
    """Список нарушенных требований; пустой — человек проходит роль."""
    violations: list[Violation] = []
    if req.allowed_category_ids is not None and person.category_id not in req.allowed_category_ids:
        violations.append(
            Violation(
                "category", None, sorted(map(str, req.allowed_category_ids)), person.category_id
            )
        )
    if req.min_rank_order is not None and (
        person.rank_order is None or person.rank_order < req.min_rank_order
    ):
        violations.append(Violation("rank", None, req.min_rank_order, person.rank_order))
    if req.allowed_position_ids is not None and person.position_id not in req.allowed_position_ids:
        violations.append(
            Violation(
                "position", None, sorted(map(str, req.allowed_position_ids)), person.position_id
            )
        )
    for a in req.attributes:
        actual = person.attributes.get(a.code)
        if not _attribute_ok(a, actual):
            violations.append(Violation("attribute", a.code, a.value, actual))
    return violations


def _typed(value: Any, value_type: str, enum_options: Sequence[str] | None) -> str | None:
    """Проверяет одно значение требования по типу характеристики. Возвращает текст ошибки."""
    match value_type:
        case "bool":
            return None if isinstance(value, bool) else "ожидается да/нет"
        case "int":
            ok = isinstance(value, int) and not isinstance(value, bool)
            return None if ok else "ожидается целое число"
        case "enum":
            return None if value in (enum_options or []) else "нет такого варианта"
        case "date":
            try:
                dt.date.fromisoformat(str(value))
            except ValueError:
                return "ожидается дата ГГГГ-ММ-ДД"
            return None
        case "string":
            return None if isinstance(value, str) and value.strip() else "ожидается строка"
    return "неизвестный тип характеристики"


def validate_requirement(
    req: AttributeRequirement, name: str, value_type: str, enum_options: Sequence[str] | None
) -> str | None:
    """Проверяет требование по определению характеристики. None — корректно, иначе — сообщение."""
    if req.op in ("gte", "lte") and value_type not in ORDERED_TYPES:
        return f"«{name}»: сравнение «{OP_LABELS[req.op]}» возможно только для чисел и дат"
    if req.op == "in" and value_type in ("bool", "date"):
        return f"«{name}»: выбор из списка для этого типа не подходит, используйте «равно»"
    values = req.value if req.op == "in" else [req.value]
    if req.op == "in" and (not isinstance(req.value, list) or not req.value):
        return f"«{name}»: нужен непустой список значений"
    for v in values:
        error = _typed(v, value_type, enum_options)
        if error:
            return f"«{name}»: {error}"
    return None
