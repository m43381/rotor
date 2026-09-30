import uuid

import pytest

from dutyflow_common.requirements import (
    AttributeRequirement,
    PersonTraits,
    RoleRequirements,
    check,
    validate_requirement,
)

POS_A, POS_B = uuid.uuid4(), uuid.uuid4()


def person(
    rank: int | None = 50, position: uuid.UUID | None = POS_A, **attrs: object
) -> PersonTraits:
    return PersonTraits(rank_order=rank, position_id=position, attributes=attrs)


def req(**kwargs: object) -> RoleRequirements:
    return RoleRequirements.from_row(
        kwargs.get("min_rank_order"),  # type: ignore[arg-type]
        kwargs.get("positions"),  # type: ignore[arg-type]
        kwargs.get("attrs"),  # type: ignore[arg-type]
    )


def test_no_requirements_always_pass() -> None:
    r = req()
    assert r.is_empty
    assert check(person(rank=None, position=None), r) == []


def test_min_rank() -> None:
    r = req(min_rank_order=60)
    assert [v.kind for v in check(person(rank=50), r)] == ["rank"]
    assert check(person(rank=60), r) == []
    assert [v.kind for v in check(person(rank=None), r)] == ["rank"]


def test_allowed_positions() -> None:
    r = req(positions=[POS_A])
    assert check(person(position=POS_A), r) == []
    assert [v.kind for v in check(person(position=POS_B), r)] == ["position"]
    assert [v.kind for v in check(person(position=None), r)] == ["position"]


@pytest.mark.parametrize(
    ("op", "value", "actual", "ok"),
    [
        ("eq", "Курсант", "Курсант", True),
        ("eq", "Курсант", "Слушатель", False),
        ("in", ["Курсант", "Слушатель"], "Слушатель", True),
        ("in", ["Курсант"], "Постоянный состав", False),
        ("gte", 3, 3, True),
        ("gte", 3, 2, False),
        ("lte", "2026-01-01", "2025-12-31", True),
        ("lte", "2026-01-01", "2026-01-02", False),
        ("gte", 3, "три", False),  # несравнимые типы — не проходит, а не падает
        ("eq", True, None, False),  # характеристика не заполнена
    ],
)
def test_attribute_ops(op: str, value: object, actual: object, ok: bool) -> None:
    r = req(attrs=[{"code": "x", "op": op, "value": value}])
    attrs = {} if actual is None else {"x": actual}
    assert (check(person(**attrs), r) == []) is ok


def test_all_violations_reported() -> None:
    r = req(min_rank_order=100, positions=[POS_B], attrs=[{"code": "c", "op": "eq", "value": 1}])
    assert [v.kind for v in check(person(c=2), r)] == ["rank", "position", "attribute"]


@pytest.mark.parametrize(
    ("op", "value", "value_type", "options", "error"),
    [
        ("eq", "Курсант", "enum", ["Курсант"], None),
        ("eq", "Генерал", "enum", ["Курсант"], "нет такого варианта"),
        ("in", ["Курсант"], "enum", ["Курсант"], None),
        ("in", [], "enum", ["Курсант"], "непустой список"),
        ("gte", 2, "int", None, None),
        ("gte", "a", "string", None, "только для чисел и дат"),
        ("lte", "2026-13-01", "date", None, "ожидается дата"),
        ("in", [True], "bool", None, "используйте «равно»"),
        ("eq", 1, "bool", None, "да/нет"),
    ],
)
def test_validate_requirement(
    op: str, value: object, value_type: str, options: list[str] | None, error: str | None
) -> None:
    result = validate_requirement(
        AttributeRequirement.model_validate({"code": "x", "op": op, "value": value}),
        "Икс",
        value_type,
        options,
    )
    if error is None:
        assert result is None
    else:
        assert result is not None
        assert error in result


def test_category_is_hard_requirement() -> None:
    cadet, officer = uuid.uuid4(), uuid.uuid4()
    r = RoleRequirements.from_row(None, None, None, [officer])
    assert not r.is_empty
    violations = check(PersonTraits(None, None, {}, category_id=cadet), r)
    assert [(v.kind, v.hard) for v in violations] == [("category", True)]
    assert check(PersonTraits(None, None, {}, category_id=officer), r) == []
    # Категория не указана — не подходит
    assert [v.kind for v in check(PersonTraits(None, None, {}), r)] == ["category"]
    # Без ограничения категории подходит любой, остальные нарушения мягкие
    soft = check(PersonTraits(10, None, {}, category_id=cadet), req(min_rank_order=60))
    assert [(v.kind, v.hard) for v in soft] == [("rank", False)]
