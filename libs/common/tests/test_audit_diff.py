import uuid

from dutyflow_common.audit import diff


def test_diff_keeps_only_changed_fields() -> None:
    uid = uuid.uuid4()
    before, after = diff({"name": "A", "parent": uid, "x": 1}, {"name": "B", "parent": uid, "x": 1})
    assert before == {"name": "A"}
    assert after == {"name": "B"}


def test_diff_create_returns_whole_object() -> None:
    before, after = diff(None, {"name": "A"})
    assert before is None
    assert after == {"name": "A"}
