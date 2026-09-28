from dutyflow_common.settings import ServiceSettings


class AuthAdminSettings(ServiceSettings):
    service_name: str = "auth-admin"
    # Keycloak внутри сети compose и realm системы
    keycloak_url: str = "http://keycloak:8080/auth"
    keycloak_realm: str = "dutyflow"
    # Служебный клиент с правами на пользователей realm (создаёт keycloak-init)
    auth_admin_client_id: str = "dutyflow-auth-admin"
    auth_admin_client_secret: str = ""
    # Подразделения в scope оператора — у org, от имени оператора (ADR-0014)
    org_url: str = "http://org:8000"
    # Для keycloak-init: администратор master-realm (создаётся Keycloak при первом запуске)
    keycloak_admin: str = ""
    keycloak_admin_password: str = ""
