"""Релей outbox сервиса documents: `python -m documents.relay` (события `audit.recorded`)."""

import asyncio

from documents.settings import DocumentsSettings
from dutyflow_common.app import setup_logging
from dutyflow_common.relay import run_relay

if __name__ == "__main__":
    settings = DocumentsSettings()
    setup_logging(settings.log_level)
    asyncio.run(run_relay(settings))
