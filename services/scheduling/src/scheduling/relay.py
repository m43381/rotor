"""Релей outbox сервиса scheduling: `python -m scheduling.relay`."""

import asyncio

from dutyflow_common.app import setup_logging
from dutyflow_common.relay import run_relay
from scheduling.settings import SchedulingSettings

if __name__ == "__main__":
    settings = SchedulingSettings()
    setup_logging(settings.log_level)
    asyncio.run(run_relay(settings))
