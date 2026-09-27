from dutyflow_common.settings import ServiceSettings


class AnalyticsSettings(ServiceSettings):
    service_name: str = "analytics"
    org_url: str = "http://org:8000"
    scheduling_url: str = "http://scheduling:8000"
