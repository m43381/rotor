"""Релей outbox сервиса auth-admin: `python -m auth_admin.relay` (события `audit.recorded`)."""

import asyncio

from auth_admin.settings import AuthAdminSettings
from dutyflow_common.app import setup_logging
from dutyflow_common.relay import run_relay

if __name__ == "__main__":
    settings = AuthAdminSettings()
    setup_logging(settings.log_level)
    asyncio.run(run_relay(settings))
