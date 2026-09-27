from dutyflow_common.settings import ServiceSettings


class SchedulingSettings(ServiceSettings):
    service_name: str = "scheduling"
    org_url: str = "http://org:8000"
    personnel_url: str = "http://personnel:8000"
    # Время нарядов — местное время инсталляции (ADR-0008), то же значение, что у org
    timezone: str = "Europe/Moscow"
