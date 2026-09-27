from dutyflow_common.settings import ServiceSettings


class SchedulingSettings(ServiceSettings):
    service_name: str = "scheduling"
    org_url: str = "http://org:8000"
    personnel_url: str = "http://personnel:8000"
    allocation_url: str = "http://allocation:8000"
    # Сколько дней хранить сжатые снимки прогонов движка (для разбора «почему так»)
    allocation_snapshot_days: int = 90
    # Время нарядов — местное время инсталляции (ADR-0008), то же значение, что у org
    timezone: str = "Europe/Moscow"
