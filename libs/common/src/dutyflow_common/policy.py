"""Политика доступа: роль × ресурс × действие → scope (`docs/architecture.md` §6).

Единственный движок прав для всех сервисов — без legacy-fallback. Правила объявлены
декларативно; сервис спрашивает `policy.scope_for(operator, resource, action)` и строит
SQL-условие через `scope_clause`.
"""

from collections.abc import Iterable, Mapping
from enum import StrEnum

from dutyflow_common.errors import ForbiddenError
from dutyflow_common.scope import Scope


class Role(StrEnum):
    SUPERADMIN = "superadmin"
    UNIT_ADMIN = "unit_admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


# Порядок старшинства: если у оператора несколько ролей, действует самая широкая scope.
ROLE_ORDER: tuple[Role, ...] = (Role.SUPERADMIN, Role.UNIT_ADMIN, Role.OPERATOR, Role.VIEWER)

_WIDTH: dict[Scope, int] = {
    Scope.NONE: 0,
    Scope.OWN_UNIT: 1,
    Scope.CHILDREN: 1,
    Scope.OWN_AND_CHILDREN: 2,
    Scope.ALL_DESCENDANTS: 3,
    Scope.OWN_AND_ALL_DESCENDANTS: 4,
    Scope.ALL: 5,
}

type RuleKey = tuple[Role, str, str]


class Policy:
    def __init__(self, rules: Mapping[RuleKey, Scope]) -> None:
        self._rules = dict(rules)

    def scope_for(self, roles: Iterable[Role], resource: str, action: str) -> Scope:
        best = Scope.NONE
        for role in roles:
            if role is Role.SUPERADMIN:
                return Scope.ALL
            scope = self._rules.get((role, resource, action), Scope.NONE)
            if _WIDTH[scope] > _WIDTH[best]:
                best = scope
        return best

    def require(self, roles: Iterable[Role], resource: str, action: str) -> Scope:
        scope = self.scope_for(roles, resource, action)
        if scope is Scope.NONE:
            raise ForbiddenError(f"Нет прав на действие «{action}» для ресурса «{resource}»")
        return scope


def _rules(role: Role, resource: str, **actions: Scope) -> dict[RuleKey, Scope]:
    return {(role, resource, action): scope for action, scope in actions.items()}


SUBTREE = Scope.OWN_AND_ALL_DESCENDANTS
BELOW = Scope.ALL_DESCENDANTS

# Правила по умолчанию. Суперадминистратор получает ALL на всё без явных правил.
DEFAULT_RULES: dict[RuleKey, Scope] = {
    # Подразделения: видеть своё поддерево; создавать под своим поддеревом; менять и переносить
    # только нижестоящие (своё собственное подразделение оператор не переносит и не удаляет).
    **_rules(
        Role.UNIT_ADMIN,
        "unit",
        read=SUBTREE,
        create=SUBTREE,
        update=SUBTREE,
        move=BELOW,
        delete=BELOW,
    ),
    **_rules(
        Role.OPERATOR, "unit", read=SUBTREE, create=SUBTREE, update=BELOW, move=BELOW, delete=BELOW
    ),
    **_rules(Role.VIEWER, "unit", read=SUBTREE),
    # Справочники читают все, меняет только суперадминистратор.
    **{
        (role, resource, "read"): Scope.ALL
        for role in (Role.UNIT_ADMIN, Role.OPERATOR, Role.VIEWER)
        for resource in (
            "unit_type",
            "rank",
            "calendar",
            "position",
            "attribute_definition",
            "exemption_reason",
        )
    },
    # Личный состав — данные, которые ведут операторы своего поддерева (open-questions №3).
    # Перевод и архивация — отдельные действия, чтобы их можно было ограничить независимо.
    **{
        (role, resource, action): SUBTREE
        for role in (Role.UNIT_ADMIN, Role.OPERATOR)
        for resource, actions in {
            "person": ("read", "create", "update", "archive", "transfer"),
            "exemption": ("read", "create", "update", "delete"),
        }.items()
        for action in actions
    },
    **_rules(Role.VIEWER, "person", read=SUBTREE),
    **_rules(Role.VIEWER, "exemption", read=SUBTREE),
    # Типы нарядов ведёт подразделение-владелец (и вышестоящие операторы). Кроме своего
    # поддерева оператор всегда видит наряды вышестоящих подразделений — их роли могут
    # делегироваться вниз (ADR-0009); это правило реализует сервис scheduling.
    **{
        (role, "duty_type", action): SUBTREE
        for role in (Role.UNIT_ADMIN, Role.OPERATOR)
        for action in ("read", "create", "update")
    },
    **_rules(Role.VIEWER, "duty_type", read=SUBTREE),
    # Графики: подразделение ведёт свой график, вышестоящие операторы могут вмешаться
    # в графики своего поддерева. Делегирование, принятие и закрепление — «update».
    **{
        (role, "schedule", action): SUBTREE
        for role in (Role.UNIT_ADMIN, Role.OPERATOR)
        for action in ("read", "create", "update", "publish")
    },
    **_rules(Role.VIEWER, "schedule", read=SUBTREE),
    # Лимиты нарядов задаёт оператор для своего поддерева (open-questions №9)
    **{
        (role, "duty_limit", action): SUBTREE
        for role in (Role.UNIT_ADMIN, Role.OPERATOR)
        for action in ("read", "create", "update")
    },
    **_rules(Role.VIEWER, "duty_limit", read=SUBTREE),
    # Допуски выдаёт оператор, в чей scope входит подразделение человека (ADR-0009).
    **{
        (role, "clearance", action): SUBTREE
        for role in (Role.UNIT_ADMIN, Role.OPERATOR)
        for action in ("read", "grant", "update", "revoke")
    },
    **_rules(Role.VIEWER, "clearance", read=SUBTREE),
    # Реквизиты печатных форм (open-questions №52): видят все в своём поддереве, задаёт
    # администратор подразделения. Шаблоны форм меняет только суперадминистратор (№51) —
    # правил для других ролей нет.
    **_rules(Role.UNIT_ADMIN, "document_settings", read=SUBTREE, update=SUBTREE),
    **_rules(Role.OPERATOR, "document_settings", read=SUBTREE),
    **_rules(Role.VIEWER, "document_settings", read=SUBTREE),
    # Аналитика нагрузки видна в своём поддереве всем ролям (open-questions №56)
    **_rules(Role.UNIT_ADMIN, "analytics", read=SUBTREE),
    **_rules(Role.OPERATOR, "analytics", read=SUBTREE),
    **_rules(Role.VIEWER, "analytics", read=SUBTREE),
    # Журнал аудита: оператор видит записи своего поддерева (ADR-0010).
    **_rules(Role.UNIT_ADMIN, "audit", read=SUBTREE),
    **_rules(Role.OPERATOR, "audit", read=SUBTREE),
    **_rules(Role.VIEWER, "audit", read=SUBTREE),
}

default_policy = Policy(DEFAULT_RULES)
