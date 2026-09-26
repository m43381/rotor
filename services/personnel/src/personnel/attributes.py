"""Проверка и нормализация значений характеристик по их определениям (ADR-0005)."""

import datetime as dt
from collections.abc import Mapping
from typing import Any

from dutyflow_common.errors import ValidationFailedError
from personnel.models import AttributeDefinition

MAX_STRING = 500


def normalize(definition: AttributeDefinition, value: Any) -> Any:
    """Возвращает значение в каноническом виде для хранения в JSONB или бросает ошибку."""
    name = definition.name
    match definition.value_type:
        case "bool":
            if not isinstance(value, bool):
                raise ValidationFailedError(f"«{name}»: ожидается да/нет")
            return value
        case "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValidationFailedError(f"«{name}»: ожидается целое число")
            return value
        case "enum":
            if value not in (definition.enum_options or []):
                raise ValidationFailedError(
                    f"«{name}»: допустимые значения — {', '.join(definition.enum_options or [])}"
                )
            return value
        case "date":
            try:
                return dt.date.fromisoformat(str(value)).isoformat()
            except ValueError as exc:
                raise ValidationFailedError(f"«{name}»: ожидается дата ГГГГ-ММ-ДД") from exc
        case "string":
            if not isinstance(value, str) or len(value) > MAX_STRING:
                raise ValidationFailedError(f"«{name}»: ожидается строка до {MAX_STRING} символов")
            return value.strip()
    raise ValidationFailedError(f"«{name}»: неизвестный тип характеристики")


def validate_values(
    definitions: Mapping[str, AttributeDefinition],
    values: Mapping[str, Any],
    *,
    require_all: bool,
) -> dict[str, Any]:
    """Проверяет набор значений по коду характеристики. `None` означает «удалить значение»."""
    unknown = sorted(set(values) - set(definitions))
    if unknown:
        raise ValidationFailedError(f"Неизвестные характеристики: {', '.join(unknown)}")
    result: dict[str, Any] = {}
    for code, value in values.items():
        definition = definitions[code]
        if value is None:
            if definition.is_required:
                raise ValidationFailedError(f"«{definition.name}» — обязательная характеристика")
            result[code] = None
            continue
        if not definition.is_active:
            raise ValidationFailedError(f"«{definition.name}» больше не используется")
        result[code] = normalize(definition, value)
    if require_all:
        missing = [
            d.name
            for code, d in definitions.items()
            if d.is_required and d.is_active and result.get(code) is None
        ]
        if missing:
            raise ValidationFailedError(
                f"Не заполнены обязательные характеристики: {', '.join(missing)}"
            )
    return result
