"""Контекст текущего запроса: оператор и request_id. Нужен аудиту и логированию."""

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field

from dutyflow_common.policy import ROLE_ORDER, Role


@dataclass(frozen=True, slots=True)
class Operator:
    subject: str  # `sub` из JWT
    username: str
    unit_id: uuid.UUID
    roles: frozenset[Role] = field(default_factory=frozenset)
    full_name: str = ""

    @property
    def primary_role(self) -> Role | None:
        return next((r for r in ROLE_ORDER if r in self.roles), None)

    @property
    def is_superadmin(self) -> bool:
        return Role.SUPERADMIN in self.roles


current_operator: ContextVar[Operator | None] = ContextVar("current_operator", default=None)
current_request_id: ContextVar[str] = ContextVar("current_request_id", default="-")
