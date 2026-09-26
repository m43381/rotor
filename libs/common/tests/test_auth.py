import uuid

import pytest

from dutyflow_common.errors import UnauthorizedError
from dutyflow_common.policy import Role
from dutyflow_common.settings import ServiceSettings
from dutyflow_common.testing import TestIssuer

SETTINGS = ServiceSettings()
ISSUER = TestIssuer(SETTINGS)


async def test_valid_token_gives_operator() -> None:
    unit = uuid.uuid4()
    op = await ISSUER.verifier.verify(ISSUER.token(unit_id=unit, roles=["operator", "offline"]))
    assert op.unit_id == unit
    assert op.roles == frozenset({Role.OPERATOR})  # посторонние роли Keycloak отбрасываются


async def test_expired_token_rejected() -> None:
    token = ISSUER.token(unit_id=uuid.uuid4(), roles=["operator"], ttl=-10)
    with pytest.raises(UnauthorizedError):
        await ISSUER.verifier.verify(token)


async def test_wrong_audience_rejected() -> None:
    token = ISSUER.token(unit_id=uuid.uuid4(), roles=["operator"], aud="other")
    with pytest.raises(UnauthorizedError):
        await ISSUER.verifier.verify(token)


async def test_foreign_key_rejected() -> None:
    other = TestIssuer(SETTINGS)  # тот же kid, но другой ключ
    with pytest.raises(UnauthorizedError):
        await ISSUER.verifier.verify(other.token(unit_id=uuid.uuid4(), roles=["operator"]))


async def test_token_without_roles_rejected() -> None:
    with pytest.raises(UnauthorizedError):
        await ISSUER.verifier.verify(ISSUER.token(unit_id=uuid.uuid4(), roles=["offline"]))
