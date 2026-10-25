"""Outbound notifications (Watch Mode alerts). Agents depend on this interface, never on Twilio directly,
so tests can fake it and a deployment without Twilio credentials still works."""

from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger("khetkaaj.notify")


class Notifier(Protocol):
    async def send(self, phone: str, text: str) -> bool:
        """Deliver `text` to `phone`. Return False, never raise, when it cannot be delivered."""
        ...


class NullNotifier:
    """Used when no channel is configured: the alert is still stored, just not pushed."""

    async def send(self, phone: str, text: str) -> bool:
        log.info("notification not sent (no channel configured)")
        return False
