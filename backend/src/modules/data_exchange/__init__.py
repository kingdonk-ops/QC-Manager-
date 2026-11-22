"""The import/export hub: every module's datasets out to Excel, CSV and PDF; spreadsheets in through importers."""

from ...infrastructure.reporting import ensure_loaded


async def on_startup() -> None:
    ensure_loaded()
