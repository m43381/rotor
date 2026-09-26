import pytest

from dutyflow_common.scope import Scope, in_scope

OP = "1.2"


@pytest.mark.parametrize(
    ("scope", "target", "expected"),
    [
        (Scope.NONE, "1.2", False),
        (Scope.ALL, "9", True),
        (Scope.OWN_UNIT, "1.2", True),
        (Scope.OWN_UNIT, "1.2.3", False),
        (Scope.CHILDREN, "1.2.3", True),
        (Scope.CHILDREN, "1.2.3.4", False),
        (Scope.CHILDREN, "1.2", False),
        (Scope.OWN_AND_CHILDREN, "1.2", True),
        (Scope.OWN_AND_CHILDREN, "1.2.3", True),
        (Scope.OWN_AND_CHILDREN, "1.2.3.4", False),
        (Scope.ALL_DESCENDANTS, "1.2", False),
        (Scope.ALL_DESCENDANTS, "1.2.3.4", True),
        (Scope.OWN_AND_ALL_DESCENDANTS, "1.2", True),
        (Scope.OWN_AND_ALL_DESCENDANTS, "1.2.3.4", True),
        # Соседняя ветка с общим префиксом строки, но не пути: 1.20 не потомок 1.2
        (Scope.OWN_AND_ALL_DESCENDANTS, "1.20", False),
        (Scope.OWN_AND_ALL_DESCENDANTS, "1", False),
    ],
)
def test_in_scope(scope: Scope, target: str, expected: bool) -> None:
    assert in_scope(target, OP, scope) is expected
