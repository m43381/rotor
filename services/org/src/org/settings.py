import uuid

from dutyflow_common.settings import ServiceSettings


class OrgSettings(ServiceSettings):
    service_name: str = "org"
    # Корневое подразделение создаётся при первом старте, если дерево пустое. Тот же id
    # прописан суперадминистратору в Keycloak (атрибут unit_id), см. deploy/.env.example.
    root_unit_id: uuid.UUID = uuid.UUID("00000000-0000-7000-8000-000000000001")
    root_unit_name: str = "Академия"
    root_unit_type_code: str = "academy"
    root_unit_type_name: str = "Академия"
    timezone: str = "Europe/Moscow"
