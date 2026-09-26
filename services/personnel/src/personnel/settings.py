from dutyflow_common.settings import ServiceSettings


class PersonnelSettings(ServiceSettings):
    service_name: str = "personnel"
    org_url: str = "http://org:8000"
