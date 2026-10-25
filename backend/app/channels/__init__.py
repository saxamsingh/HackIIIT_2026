"""Message channels: WhatsApp (Twilio) text and voice notes, and outbound notifications."""

from __future__ import annotations

from ..config import Settings
from .notify import Notifier, NullNotifier
from .twilio import TwilioNotifier


def make_notifier(settings: Settings) -> Notifier:
    """WhatsApp when Twilio is fully configured, otherwise a notifier that only logs."""
    if settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_whatsapp_from:
        return TwilioNotifier(settings)
    return NullNotifier()


__all__ = ["Notifier", "NullNotifier", "TwilioNotifier", "make_notifier"]
