"""Релей outbox сервиса org: `python -m org.relay`."""

import asyncio

from dutyflow_common.app import setup_logging
from dutyflow_common.relay import run_relay
from org.settings import OrgSettings

if __name__ == "__main__":
    settings = OrgSettings()
    setup_logging(settings.log_level)
    asyncio.run(run_relay(settings))
