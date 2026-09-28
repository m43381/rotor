"""Управление операторами (фаза 7a, open-questions №59, №61).

Права:
- суперадминистратор — любые операторы и роли;
- администратор подразделения — в своём поддереве: операторы и наблюдатели для своего и
  нижестоящих подразделений, администраторы — только для нижестоящих (не равных себе);
  суперадминистраторов не создаёт и не меняет;
- оператор и наблюдатель операторами не управляют.
Изменить существующую учётную запись можно, только если разрешены и её текущие роль и
подразделение, и новые. Себя нельзя заблокировать и нельзя сменить себе роль или
подразделение. Удаления нет — только блокировка: автор изменений в журналах остаётся.

Подразделения в scope берутся у org от имени оператора (ADR-0014). Все изменения — в журнал
аудита сервиса (пароли в журнал не попадают).
"""

import datetime as dt
import secrets
import string
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from auth_admin.keycloak import ROLES, KeycloakAdmin
from dutyflow_common import audit
from dutyflow_common.context import Operator
from dutyflow_common.errors import ForbiddenError, ValidationFailedError
from dutyflow_common.upstream import UpstreamClient

ROLE_NAMES = {
    "superadmin": "Суперадминистратор",
    "unit_admin": "Администратор подразделения",
    "operator": "Оператор",
    "viewer": "Наблюдатель",
}


def temporary_password() -> str:
    """12 символов: строчные и заглавные буквы и цифры — проходит политику паролей (№61)."""
    alphabet = string.ascii_letters + string.digits
    while True:
        value = "".join(secrets.choice(alphabet) for _ in range(12))
        if (
            any(c.islower() for c in value)
            and any(c.isupper() for c in value)
            and any(c.isdigit() for c in value)
        ):
            return value


@dataclass
class Scope:
    units: dict[str, dict[str, Any]]  # id → подразделение (id, name, path) в scope оператора
    all_units: bool


class OperatorService:
    def __init__(
        self,
        session: AsyncSession,
        operator: Operator,
        token: str,
        keycloak: KeycloakAdmin,
        org: UpstreamClient,
    ) -> None:
        self.session = session
        self.operator = operator
        self.token = token
        self.keycloak = keycloak
        self.org = org

    # --- права ---------------------------------------------------------------------------------

    async def _scope(self) -> Scope:
        if not (self.operator.is_superadmin or "unit_admin" in self.operator.roles):
            raise ForbiddenError("Операторами управляют администраторы")
        units = await self.org.get("/units", self.token)
        return Scope({u["id"]: u for u in units}, self.operator.is_superadmin)

    def _allowed(self, scope: Scope, role: str | None, unit_id: str | None) -> bool:
        if self.operator.is_superadmin:
            return True
        if role == "superadmin" or unit_id is None or unit_id not in scope.units:
            return False
        if role == "unit_admin":
            return unit_id != str(self.operator.unit_id)
        return role in ("operator", "viewer", None)

    def allowed_roles(self, scope: Scope, unit_id: str) -> list[str]:
        return [r for r in ROLES if self._allowed(scope, r, unit_id)]

    # --- чтение ----------------------------------------------------------------------------------

    def _out(self, u: dict[str, Any], role: str | None, scope: Scope) -> dict[str, Any]:
        unit_id = (u.get("attributes") or {}).get("unit_id", [None])[0]
        unit = scope.units.get(unit_id) if unit_id else None
        last, first = u.get("lastName") or "", u.get("firstName") or ""
        return {
            "id": u["id"],
            "username": u["username"],
            "last_name": last,
            "first_name": first,
            "full_name": f"{last} {first}".strip() or u["username"],
            "role": role,
            "role_name": ROLE_NAMES.get(role or "", "Без роли"),
            "unit_id": unit_id,
            "unit_name": unit["name"] if unit else None,
            "enabled": bool(u.get("enabled", True)),
            "created_at": (
                dt.datetime.fromtimestamp(u["createdTimestamp"] / 1000, dt.UTC)
                if u.get("createdTimestamp")
                else None
            ),
            "self": u["id"] == self.operator.subject,
            "can_edit": u["id"] != self.operator.subject and self._allowed(scope, role, unit_id),
        }

    async def list_operators(
        self, q: str | None, unit_id: str | None, limit: int, offset: int
    ) -> dict[str, Any]:
        scope = await self._scope()
        users = await self.keycloak.users()
        roles = await self.keycloak.role_members()
        units = scope.units
        if unit_id:
            root = units.get(unit_id)
            if root is None:
                raise ForbiddenError("Подразделение вне зоны ответственности")
            prefix = root["path"]
            units = {
                k: v
                for k, v in units.items()
                if v["path"] == prefix or v["path"].startswith(prefix + ".")
            }
        needle = (q or "").strip().lower()
        items = []
        for u in users:
            uid = (u.get("attributes") or {}).get("unit_id", [None])[0]
            if uid not in units and not (scope.all_units and not unit_id):
                continue
            out = self._out(u, roles.get(u["id"]), scope)
            if needle and needle not in f"{out['username']} {out['full_name']}".lower():
                continue
            items.append(out)
        items.sort(key=lambda o: (o["full_name"].lower(), o["username"]))
        return {
            "items": items[offset : offset + limit],
            "total": len(items),
            "limit": limit,
            "offset": offset,
        }

    async def _target(self, user_id: str, scope: Scope) -> tuple[dict[str, Any], str | None]:
        user = await self.keycloak.user(user_id)
        role = await self.keycloak.user_role(user_id)
        unit_id = (user.get("attributes") or {}).get("unit_id", [None])[0]
        if not self._allowed(scope, role, unit_id):
            raise ForbiddenError("Этим оператором управляет вышестоящий администратор")
        return user, role

    @staticmethod
    def _snapshot(user: dict[str, Any], role: str | None) -> dict[str, Any]:
        return {
            "username": user["username"],
            "last_name": user.get("lastName"),
            "first_name": user.get("firstName"),
            "role": role,
            "unit_id": (user.get("attributes") or {}).get("unit_id", [None])[0],
            "enabled": bool(user.get("enabled", True)),
        }

    def _audit(
        self,
        action: str,
        user_id: str,
        unit_id: str | None,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        comment: str | None = None,
    ) -> None:
        audit.record(
            self.session,
            action=action,
            entity_type="operator",
            entity_id=uuid.UUID(user_id),
            scope_unit_id=uuid.UUID(unit_id) if unit_id else None,
            before=before,
            after=after,
            comment=comment,
        )

    # --- изменение --------------------------------------------------------------------------------

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        scope = await self._scope()
        unit_id, role = str(data["unit_id"]), data["role"]
        if unit_id not in scope.units:
            raise ForbiddenError("Подразделение вне зоны ответственности")
        if not self._allowed(scope, role, unit_id):
            raise ForbiddenError(
                f"Роль «{ROLE_NAMES[role]}» для этого подразделения выдаёт вышестоящий"
            )
        password = temporary_password()
        user_id = await self.keycloak.create_user(
            {
                "username": data["username"],
                "enabled": True,
                "firstName": data["first_name"],
                "lastName": data["last_name"],
                "attributes": {"unit_id": [unit_id]},
                "credentials": [{"type": "password", "value": password, "temporary": True}],
                "requiredActions": ["UPDATE_PASSWORD"],
            }
        )
        await self.keycloak.set_role(user_id, role)
        user = await self.keycloak.user(user_id)
        self._audit("operator.create", user_id, unit_id, None, self._snapshot(user, role))
        await self.session.commit()
        return {**self._out(user, role, scope), "temporary_password": password}

    async def update(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        scope = await self._scope()
        user, role = await self._target(user_id, scope)
        before = self._snapshot(user, role)
        new_role = data.get("role") or role
        new_unit = str(data["unit_id"]) if data.get("unit_id") else before["unit_id"]
        if user_id == self.operator.subject and (new_role != role or new_unit != before["unit_id"]):
            raise ValidationFailedError(
                "Свои роль и подразделение меняет вышестоящий администратор"
            )
        if not self._allowed(scope, new_role, new_unit):
            raise ForbiddenError("Такую роль или подразделение назначает вышестоящий администратор")
        body = {
            **{
                k: v for k, v in user.items() if k in ("username", "email", "enabled", "attributes")
            },
            "firstName": data.get("first_name") or user.get("firstName"),
            "lastName": data.get("last_name") or user.get("lastName"),
        }
        body["attributes"] = {**(user.get("attributes") or {}), "unit_id": [new_unit]}
        await self.keycloak.update_user(user_id, body)
        if new_role and new_role != role:
            await self.keycloak.set_role(user_id, new_role)
        fresh = await self.keycloak.user(user_id)
        self._audit("operator.update", user_id, new_unit, before, self._snapshot(fresh, new_role))
        await self.session.commit()
        return self._out(fresh, new_role, scope)

    async def set_enabled(self, user_id: str, enabled: bool) -> dict[str, Any]:
        scope = await self._scope()
        if user_id == self.operator.subject:
            raise ValidationFailedError("Нельзя заблокировать самого себя")
        user, role = await self._target(user_id, scope)
        before = self._snapshot(user, role)
        await self.keycloak.update_user(user_id, {**user, "enabled": enabled})
        if not enabled:
            await self.keycloak.logout(user_id)
        fresh = await self.keycloak.user(user_id)
        self._audit(
            "operator.unblock" if enabled else "operator.block",
            user_id,
            before["unit_id"],
            before,
            self._snapshot(fresh, role),
        )
        await self.session.commit()
        return self._out(fresh, role, scope)

    async def reset_password(self, user_id: str) -> dict[str, Any]:
        scope = await self._scope()
        user, role = await self._target(user_id, scope)
        password = temporary_password()
        await self.keycloak.reset_password(user_id, password)
        await self.keycloak.logout(user_id)
        unit_id = self._snapshot(user, role)["unit_id"]
        self._audit(
            "operator.reset_password",
            user_id,
            unit_id,
            None,
            {"username": user["username"], "temporary": True},
        )
        await self.session.commit()
        return {**self._out(user, role, scope), "temporary_password": password}

    async def logout(self, user_id: str) -> dict[str, Any]:
        scope = await self._scope()
        user, role = await self._target(user_id, scope)
        await self.keycloak.logout(user_id)
        self._audit(
            "operator.logout",
            user_id,
            self._snapshot(user, role)["unit_id"],
            None,
            {"username": user["username"], "sessions": "завершены"},
        )
        await self.session.commit()
        return self._out(user, role, scope)

    async def options(self, unit_id: str) -> list[str]:
        """Роли, которые оператор может выдать в этом подразделении (для формы)."""
        scope = await self._scope()
        if unit_id not in scope.units:
            raise ForbiddenError("Подразделение вне зоны ответственности")
        return self.allowed_roles(scope, unit_id)
