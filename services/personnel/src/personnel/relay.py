"""Релей outbox сервиса personnel: `python -m personnel.relay`."""

import asyncio

from dutyflow_common.app import setup_logging
from dutyflow_common.relay import run_relay
from personnel.settings import PersonnelSettings

if __name__ == "__main__":
    settings = PersonnelSettings()
    setup_logging(settings.log_level)
    asyncio.run(run_relay(settings))
