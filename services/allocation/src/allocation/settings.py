from dutyflow_common.settings import ServiceSettings


class AllocationSettings(ServiceSettings):
    """Предметной БД у allocation нет (ADR-0006): движок — чистая функция над снимком."""

    service_name: str = "allocation"
