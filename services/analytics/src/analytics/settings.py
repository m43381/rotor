from dutyflow_common.settings import ServiceSettings


class AnalyticsSettings(ServiceSettings):
    service_name: str = "analytics"
    org_url: str = "http://org:8000"
    scheduling_url: str = "http://scheduling:8000"
    # Сервисы, чьи журналы аудита сводятся в один (выгрузка при начальном заполнении)
    personnel_url: str = "http://personnel:8000"
    documents_url: str = "http://documents:8000"
    auth_admin_url: str = "http://auth-admin:8000"
    # Даты фильтров журнала — в часовом поясе инсталляции
    timezone: str = "Europe/Moscow"

    def audit_sources(self) -> dict[str, str]:
        return {
            "org": self.org_url,
            "personnel": self.personnel_url,
            "scheduling": self.scheduling_url,
            "documents": self.documents_url,
            "auth-admin": self.auth_admin_url,
        }
