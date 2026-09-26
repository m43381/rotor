"""Scope оператора — какую часть дерева подразделений он видит (обобщение legacy access_control).

Семь видов scope взяты из legacy (`docs/legacy-analysis.md` §3), но вычисляются не рекурсией
в Python, а одним индексным предикатом по `ltree` (ADR-0003).
"""

from enum import StrEnum

from sqlalchemy import ColumnElement, SQLColumnExpression, cast, false, literal, true

from dutyflow_common.ltree import Ltree, is_descendant_or_self, matches


class Scope(StrEnum):
    NONE = "none"
    OWN_UNIT = "own_unit"
    CHILDREN = "children"
    OWN_AND_CHILDREN = "own_and_children"
    ALL_DESCENDANTS = "all_descendants"
    OWN_AND_ALL_DESCENDANTS = "own_and_all_descendants"
    ALL = "all"


def scope_clause(
    path: SQLColumnExpression[str], operator_path: str, scope: Scope
) -> ColumnElement[bool]:
    """SQL-условие «узел с путём `path` входит в scope оператора с путём `operator_path`»."""
    match scope:
        case Scope.NONE:
            return false()
        case Scope.ALL:
            return true()
        case Scope.OWN_UNIT:
            return path == cast(literal(operator_path), Ltree())
        case Scope.CHILDREN:
            return matches(path, f"{operator_path}.*{{1}}")
        case Scope.OWN_AND_CHILDREN:
            return matches(path, f"{operator_path}.*{{0,1}}")
        case Scope.ALL_DESCENDANTS:
            return matches(path, f"{operator_path}.*{{1,}}")
        case Scope.OWN_AND_ALL_DESCENDANTS:
            return is_descendant_or_self(path, operator_path)


def in_scope(target_path: str, operator_path: str, scope: Scope) -> bool:
    """То же, что `scope_clause`, но для одного уже загруженного узла (проверки при записи)."""
    target = target_path.split(".")
    own = operator_path.split(".")
    is_self = target == own
    is_below = len(target) > len(own) and target[: len(own)] == own
    depth = len(target) - len(own)
    match scope:
        case Scope.NONE:
            return False
        case Scope.ALL:
            return True
        case Scope.OWN_UNIT:
            return is_self
        case Scope.CHILDREN:
            return is_below and depth == 1
        case Scope.OWN_AND_CHILDREN:
            return is_self or (is_below and depth == 1)
        case Scope.ALL_DESCENDANTS:
            return is_below
        case Scope.OWN_AND_ALL_DESCENDANTS:
            return is_self or is_below
