"""Помощники для тестов сервисов: выпуск JWT, подписанных тестовым ключом, без Keycloak."""

import json
import time
import uuid
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from dutyflow_common.auth import JwksCache, TokenVerifier
from dutyflow_common.settings import ServiceSettings

TEST_KID = "test-key"


class TestIssuer:
    """Выпускает токены так же, как Keycloak: RS256, realm_access.roles, unit_id."""

    __test__ = False  # не коллекционировать pytest-ом

    def __init__(self, settings: ServiceSettings) -> None:
        self.settings = settings
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self._key.public_key()))
        public_jwk.update({"kid": TEST_KID, "use": "sig", "alg": "RS256"})
        self.jwks = JwksCache("http://unused")
        self.jwks.set_keys({"keys": [public_jwk]})
        self.verifier = TokenVerifier(settings, self.jwks)

    def token(
        self,
        *,
        unit_id: uuid.UUID,
        roles: list[str],
        sub: str | None = None,
        username: str = "test",
        ttl: int = 300,
        **extra: Any,
    ) -> str:
        now = int(time.time())
        claims = {
            "sub": sub or str(uuid.uuid4()),
            "preferred_username": username,
            "name": username,
            "iss": self.settings.oidc_issuer,
            "aud": self.settings.oidc_audience,
            "iat": now,
            "exp": now + ttl,
            self.settings.oidc_unit_claim: str(unit_id),
            "realm_access": {"roles": roles},
            **extra,
        }
        return jwt.encode(claims, self._key, algorithm="RS256", headers={"kid": TEST_KID})
