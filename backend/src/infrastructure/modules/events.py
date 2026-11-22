"""An in-process event bus, so modules react to each other without importing each other.

Publish ``"<module>.<entity>.<verb>"`` events with a JSON-able payload; subscribe from your module's
``events.py``, which the loader imports. Handlers run after the publisher's work, in the same
process; one that raises is logged and doesn't stop the others. Work that must survive a restart
belongs in a Taskiq task the handler enqueues.
"""

import fnmatch
from collections.abc import Awaitable, Callable
from typing import Any

from ..logging import get_logger

logger = get_logger()

Handler = Callable[[str, dict[str, Any]], Awaitable[None]]

_handlers: list[tuple[str, Handler]] = []


def subscribe(pattern: str) -> Callable[[Handler], Handler]:
    """Decorate an ``async def handler(event, payload)``. ``pattern`` may use ``*``, e.g. ``"projects.*"``."""

    def register(handler: Handler) -> Handler:
        _handlers.append((pattern, handler))
        return handler

    return register


async def publish(event: str, payload: dict[str, Any]) -> None:
    """Call every handler whose pattern matches ``event``."""
    for pattern, handler in list(_handlers):
        if fnmatch.fnmatchcase(event, pattern):
            try:
                await handler(event, payload)
            except Exception:
                logger.exception("Event handler failed", extra={"event": event, "handler": handler.__qualname__})


def clear() -> None:
    """Forget every subscription. For tests."""
    _handlers.clear()
