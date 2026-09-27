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


def test_duty_type_and_clearance_rules() -> None:
    subtree = Scope.OWN_AND_ALL_DESCENDANTS
    assert default_policy.scope_for({Role.OPERATOR}, "duty_type", "create") is subtree
    assert default_policy.scope_for({Role.VIEWER}, "duty_type", "update") is Scope.NONE
    assert default_policy.scope_for({Role.UNIT_ADMIN}, "clearance", "grant") is subtree
    assert default_policy.scope_for({Role.VIEWER}, "clearance", "read") is subtree
    assert default_policy.scope_for({Role.VIEWER}, "clearance", "revoke") is Scope.NONE
