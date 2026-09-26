import time

from dutyflow_common.ids import uuid7


def test_uuid7_version_and_variant() -> None:
    u = uuid7()
    assert u.version == 7
    assert u.variant == "specified in RFC 4122"


def test_uuid7_time_ordered() -> None:
    first = uuid7()
    time.sleep(0.002)
    second = uuid7()
    assert first < second


def test_uuid7_unique() -> None:
    assert len({uuid7() for _ in range(10_000)}) == 10_000
