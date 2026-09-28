"""Покрытие аудита (ADR-0010, фаза 7b): каждое изменение данных сервиса пишет журнал.
Выполняется последним и только при полном прогоне тестов сервиса."""

from pathlib import Path

import pytest

from dutyflow_common.testing.audit_coverage import AuditCoverage


def test_every_mutation_is_audited(
    request: pytest.FixtureRequest, audit_coverage: AuditCoverage
) -> None:
    audit_coverage.check(request, Path(__file__).parent)
