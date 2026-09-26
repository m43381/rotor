import pytest

from dutyflow_common.errors import ForbiddenError
from dutyflow_common.policy import Role, default_policy
from dutyflow_common.scope import Scope


def test_superadmin_gets_all() -> None:
    assert default_policy.scope_for({Role.SUPERADMIN}, "anything", "delete") is Scope.ALL


def test_operator_cannot_move_own_unit() -> None:
    assert default_policy.scope_for({Role.OPERATOR}, "unit", "move") is Scope.ALL_DESCENDANTS


def test_widest_scope_wins_for_multiple_roles() -> None:
    roles = {Role.VIEWER, Role.UNIT_ADMIN}
    assert default_policy.scope_for(roles, "unit", "update") is Scope.OWN_AND_ALL_DESCENDANTS


def test_viewer_cannot_write() -> None:
    with pytest.raises(ForbiddenError):
        default_policy.require({Role.VIEWER}, "unit", "create")


def test_reference_data_readonly_for_operator() -> None:
    assert default_policy.scope_for({Role.OPERATOR}, "rank", "read") is Scope.ALL
    assert default_policy.scope_for({Role.OPERATOR}, "rank", "create") is Scope.NONE


def test_personnel_rules() -> None:
    assert (
        default_policy.scope_for({Role.OPERATOR}, "person", "transfer")
        is Scope.OWN_AND_ALL_DESCENDANTS
    )
    assert default_policy.scope_for({Role.VIEWER}, "person", "update") is Scope.NONE
    assert (
        default_policy.scope_for({Role.VIEWER}, "exemption", "read")
        is Scope.OWN_AND_ALL_DESCENDANTS
    )
    assert default_policy.scope_for({Role.OPERATOR}, "position", "create") is Scope.NONE
