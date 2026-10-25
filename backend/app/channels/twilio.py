"""Twilio helpers: webhook signature validation and the outbound WhatsApp notifier.

Implemented over httpx so the project does not take the whole Twilio SDK as a dependency. The signature
algorithm was checked against Twilio's own SDK output (tests/test_channels.py)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging

import httpx

from ..config import Settings

log = logging.getLogger("khetkaaj.twilio")

MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"


def signature_for(url: str, params: dict[str, list[str]], auth_token: str) -> str:
    """Twilio's request signature: HMAC-SHA1 of ``url`` + each sorted ``key`` + ``value``, base64 encoded."""
    payload = url
    for key in sorted(params):
        for value in sorted(set(params[key])):
            payload += key + value
    digest = hmac.new(auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def valid_signature(url: str, params: dict[str, list[str]], signature: str | None, auth_token: str) -> bool:
    if not signature:
        return False
    return hmac.compare_digest(signature_for(url, params, auth_token), signature)


def whatsapp_address(phone: str) -> str:
    phone = phone.strip()
    return phone if phone.startswith("whatsapp:") else f"whatsapp:{phone}"


class TwilioNotifier:
    """Sends WhatsApp messages (Watch Mode alerts). Returns False, never raises, when it cannot send."""

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self._transport = transport

    async def send(self, phone: str, text: str) -> bool:
        s = self.settings
        if not (s.twilio_account_sid and s.twilio_auth_token and s.twilio_whatsapp_from):
            log.warning("WhatsApp send skipped: TWILIO_ACCOUNT_SID / AUTH_TOKEN / WHATSAPP_FROM not all set")
            return False
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=20) as client:
                r = await client.post(
                    MESSAGES_URL.format(sid=s.twilio_account_sid),
                    auth=(s.twilio_account_sid, s.twilio_auth_token),
                    data={
                        "From": whatsapp_address(s.twilio_whatsapp_from),
                        "To": whatsapp_address(phone),
                        "Body": text[:1600],
                    },
                )
        except httpx.HTTPError as e:
            log.warning("WhatsApp send failed: %s", type(e).__name__)
            return False
        if r.status_code >= 300:
            log.warning("WhatsApp send failed: HTTP %s", r.status_code)
            return False
        return True
