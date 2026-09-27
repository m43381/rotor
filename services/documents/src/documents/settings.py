from dutyflow_common.settings import ServiceSettings


class DocumentsSettings(ServiceSettings):
    service_name: str = "documents"
    # Публичные API сервисов-владельцев внутри сети compose; вызовы — от имени оператора
    personnel_url: str = "http://personnel:8000"
    # Задачи импорта (с файлами) хранятся столько дней, потом удаляются
    import_ttl_days: int = 7
    max_upload_mb: int = 10
