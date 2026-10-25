"""WhatsApp channel: a Twilio webhook in front of the same planner and safety gate the web app uses.

Text goes straight to the planner. A voice note is downloaded, transcribed by Bhashini and then treated as
text; without Bhashini credentials it gets a polite text-only reply. The sender's phone number identifies the
farmer; an unknown number is answered too, just without a profile."""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from ..config import Settings
from ..db import Repository
from ..deps import notifier_dep, repo_dep, settings_dep, web_dep
from ..models import Farmer
from ..orchestrator import respond
from ..tinyfish import WebClient, WebClientError
from .notify import Notifier
from .twilio import valid_signature
from .voice import MediaFetcher, Transcriber, VoiceError

log = logging.getLogger("khetkaaj.whatsapp")

router = APIRouter()
MAX_REPLY_CHARS = 1500  # Twilio rejects WhatsApp bodies over 1600 characters

NO_VOICE = (
    "Abhi main voice note nahi sun sakta. Kripya likhkar bhejiye, jaise: 'Gehu kahan bechun?'\n"
    "I cannot play voice notes yet. Please type your question, for example: 'Where should I sell wheat?'"
)
VOICE_FAILED = (
    "Aapki awaaz samajh nahi aayi. Dobara bolkar bhejiye ya likhkar poochiye.\n"
    "I could not understand that voice note. Please try again or type your question."
)
PORTAL_DOWN = (
    "Abhi portal se jaankari nahi mil paayi. Thodi der baad dobara koshish kijiye.\n"
    "I could not reach the portal just now. Please try again in a little while."
)


def twiml(message: str) -> Response:
    body = escape(message[:MAX_REPLY_CHARS])
    return Response(
        f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{body}</Message></Response>',
        media_type="application/xml",
    )


def empty_twiml() -> Response:
    """A duplicate webhook must not cause Twilio to emit the same reply a second time."""
    return Response('<?xml version="1.0" encoding="UTF-8"?><Response></Response>', media_type="application/xml")


def _first(form: dict[str, list[str]], key: str) -> str:
    return (form.get(key) or [""])[0]


def audio_media(form: dict[str, list[str]]) -> tuple[str, str] | None:
    """The first audio attachment as (url, content_type), if the message has one."""
    try:
        count = int(_first(form, "NumMedia") or 0)
    except ValueError:
        count = 0
    for i in range(min(count, 10)):
        ctype, url = _first(form, f"MediaContentType{i}"), _first(form, f"MediaUrl{i}")
        if ctype.lower().startswith("audio/") and url:
            return url, ctype
    return None


def _digits(phone: str) -> str:
    return re.sub(r"\D", "", phone)


def farmer_for(repo: Repository, sender: str) -> Farmer | None:
    """`whatsapp:+919800000000` to the farmer with that number (digits only, so formatting does not matter)."""
    wanted = _digits(sender)
    if not wanted:
        return None
    return next((f for f in repo.list_farmers() if f.phone and _digits(f.phone) == wanted), None)


def public_url(request: Request, settings: Settings) -> str:
    """The URL Twilio signed. Behind ngrok / Render the app sees http, so prefer the configured public origin."""
    base = settings.public_base_url.rstrip("/")
    if base:
        query = f"?{request.url.query}" if request.url.query else ""
        return f"{base}{request.url.path}{query}"
    return str(request.url)


async def reply_for(
    form: dict[str, list[str]],
    *,
    repo: Repository,
    web: WebClient,
    settings: Settings,
    notifier: Notifier,
    transcriber: Transcriber | None,
    fetch_media: MediaFetcher,
) -> str:
    """Turn one incoming WhatsApp message into the reply text. Never raises for user-caused failures."""
    text = _first(form, "Body").strip()
    sender = _first(form, "From")
    farmer = farmer_for(repo, sender)
    heard = False
    audio = audio_media(form)
    if audio and not text:
        if transcriber is None:
            return NO_VOICE
        try:
            data, ctype = await fetch_media(audio[0])
            if farmer:
                preferred_language = farmer.language if farmer.language in {"hi", "en"} else "hi"
            else:
                preferred_language = settings.bhashini_language
            text = (await transcriber.transcribe(data, ctype or audio[1], preferred_language)).strip()
        except VoiceError as e:
            log.warning("voice note failed: %s", e)
            return VOICE_FAILED
        if not text:
            return VOICE_FAILED
        heard = True
    try:
        gated = await respond(
            text, repo=repo, web=web, settings=settings, farmer_id=farmer.id if farmer else None, notifier=notifier
        )
    except (WebClientError, ValueError) as e:
        log.warning("message failed: %s", e)
        return PORTAL_DOWN
    return f'Suna: "{text}"\n{gated.reply}' if heard else gated.reply


@router.post("/whatsapp/incoming")
async def incoming(
    request: Request,
    repo: Repository = Depends(repo_dep),
    web: WebClient = Depends(web_dep),
    settings: Settings = Depends(settings_dep),
    notifier: Notifier = Depends(notifier_dep),
) -> Response:
    form = parse_qs((await request.body()).decode("utf-8", "replace"), keep_blank_values=True)
    token = settings.twilio_auth_token
    if token and not valid_signature(
        public_url(request, settings), form, request.headers.get("X-Twilio-Signature"), token
    ):
        raise HTTPException(403, "invalid Twilio signature")
    # Twilio retries inbound webhooks when the response is delayed or lost. Claim the stable
    # MessageSid before doing any work so a retry cannot create a second ledger entry or ticket.
    message_id = _first(form, "MessageSid") or _first(form, "SmsMessageSid")
    if message_id:
        repo.purge_channel_messages(settings.whatsapp_message_retention_days)
        claimed, _ = repo.claim_channel_message(message_id, _first(form, "From"))
        if not claimed:
            # Returning the cached TwiML would re-send the same WhatsApp reply on webhook retries.
            # The original request owns the reply; duplicates are acknowledged silently.
            return empty_twiml()

    try:
        reply = await reply_for(
            form,
            repo=repo,
            web=web,
            settings=settings,
            notifier=notifier,
            transcriber=request.app.state.transcriber,
            fetch_media=request.app.state.media_fetcher,
        )
    except Exception:
        if message_id:
            repo.fail_channel_message(message_id)
        raise
    if message_id:
        repo.finish_channel_message(message_id, reply)
    return twiml(reply)
