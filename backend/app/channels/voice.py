"""Voice notes: download the WhatsApp media and turn Hindi speech into text with Bhashini (ULCA pipeline).

The Bhashini request shapes follow its public pipeline docs and have NOT been exercised against a live key
from this repo; the tests use a fake transport. Treat the first real voice note as the integration test."""

from __future__ import annotations

import asyncio
import base64
import logging
import shutil
from typing import Protocol
from urllib.parse import urljoin, urlparse

import httpx

from ..config import Settings

log = logging.getLogger("khetkaaj.voice")

PIPELINE_SEARCH_URL = "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"
PIPELINE_ID = "64392f96daac500b55c543cd"  # Bhashini's public pipeline id for ASR / NMT / TTS composites
MAX_AUDIO_BYTES = 10 * 1024 * 1024
_ALLOWED_MEDIA_HOSTS = ("twilio.com", "twiliocdn.com")
_FORMATS = {
    "audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-wav": "wav",
    "audio/flac": "flac", "audio/amr": "amr", "audio/mp4": "mp4",
}


class VoiceError(Exception):
    """Voice could not be turned into text. The message is safe to log, not to show a farmer."""


class Transcriber(Protocol):
    async def transcribe(self, audio: bytes, content_type: str, language: str | None = None) -> str: ...


class MediaFetcher(Protocol):
    async def __call__(self, url: str) -> tuple[bytes, str]: ...


def media_host_allowed(url: str) -> bool:
    """The webhook body is attacker-controlled when signatures are off, so only fetch from Twilio over https."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    try:
        safe_port = parsed.port in (None, 443)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and safe_port
        and parsed.username is None
        and parsed.password is None
        and any(host == d or host.endswith("." + d) for d in _ALLOWED_MEDIA_HOSTS)
    )


class TwilioMediaFetcher:
    """Downloads a Twilio media URL, with Basic auth when credentials are configured."""

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self._transport = transport

    async def __call__(self, url: str) -> tuple[bytes, str]:
        current = url
        sid, token = self.settings.twilio_account_sid, self.settings.twilio_auth_token
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=30, follow_redirects=False) as client:
                for _hop in range(4):
                    if not media_host_allowed(current):
                        raise VoiceError("media host not allowed")
                    host = (urlparse(current).hostname or "").lower()
                    # Twilio API media URLs use Basic auth. Never forward credentials to the CDN.
                    is_twilio_api = host == "twilio.com" or host.endswith(".twilio.com")
                    auth = (sid, token) if sid and token and is_twilio_api else None
                    async with client.stream("GET", current, auth=auth) as r:
                        if r.status_code in (301, 302, 303, 307, 308):
                            location = r.headers.get("location")
                            if not location:
                                raise VoiceError("media redirect missing location")
                            current = urljoin(current, location)
                            if not media_host_allowed(current):
                                raise VoiceError("media redirect host not allowed")
                            continue
                        if r.status_code >= 300:
                            raise VoiceError(f"media download failed: HTTP {r.status_code}")
                        announced = r.headers.get("content-length")
                        if announced and announced.isdigit() and int(announced) > MAX_AUDIO_BYTES:
                            raise VoiceError("voice note too large")
                        body = bytearray()
                        async for chunk in r.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > MAX_AUDIO_BYTES:
                                raise VoiceError("voice note too large")
                        content_type = r.headers.get("content-type", "audio/ogg").split(";")[0].strip().lower()
                        if content_type == "application/octet-stream":
                            # Use the verified Twilio webhook content type as a fallback in reply_for.
                            content_type = ""
                        elif content_type not in _FORMATS:
                            raise VoiceError("unsupported audio content type")
                        return bytes(body), content_type
                raise VoiceError("too many media redirects")
        except httpx.HTTPError as e:
            raise VoiceError(f"media download failed: {type(e).__name__}") from e



async def to_wav_16k(audio: bytes) -> bytes | None:
    """Convert to 16 kHz mono WAV with ffmpeg when it is installed; None when it is not or conversion fails."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            ffmpeg, "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar", "16000", "-f", "wav", "pipe:1",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate(audio)
    except (OSError, asyncio.SubprocessError):
        return None
    return out if proc.returncode == 0 and out else None


class BhashiniClient:
    """Speech to text through Bhashini's pipeline API: look up the ASR service once, then call its inference URL."""

    def __init__(
        self,
        user_id: str,
        api_key: str,
        *,
        language: str = "hi",
        transport: httpx.AsyncBaseTransport | None = None,
        convert: bool = True,
    ) -> None:
        self.user_id, self.api_key, self.language = user_id, api_key, language
        self._transport = transport
        self._convert = convert
        self._pipelines: dict[str, dict] = {}

    async def _pipeline_config(self, client: httpx.AsyncClient, language: str) -> dict:
        if language not in self._pipelines:
            r = await client.post(
                PIPELINE_SEARCH_URL,
                headers={"userID": self.user_id, "ulcaApiKey": self.api_key},
                json={
                    "pipelineTasks": [{"taskType": "asr", "config": {"language": {"sourceLanguage": language}}}],
                    "pipelineRequestConfig": {"pipelineId": PIPELINE_ID},
                },
            )
            if r.status_code >= 300:
                raise VoiceError(f"Bhashini pipeline lookup failed: HTTP {r.status_code}")
            body = r.json()
            try:
                endpoint = body["pipelineInferenceAPIEndPoint"]
                self._pipelines[language] = {
                    "url": endpoint["callbackUrl"],
                    "key_name": endpoint["inferenceApiKey"]["name"],
                    "key_value": endpoint["inferenceApiKey"]["value"],
                    "service_id": body["pipelineResponseConfig"][0]["config"][0]["serviceId"],
                }
            except (KeyError, IndexError, TypeError) as e:
                raise VoiceError("Bhashini pipeline lookup returned an unexpected shape") from e
        return self._pipelines[language]

    async def transcribe(self, audio: bytes, content_type: str, language: str | None = None) -> str:
        # Bhashini has to be configured for a language explicitly. Farmer profiles may request Hindi or English;
        # Hinglish profiles use Hindi ASR as the safer default until a provider supports code-switching well.
        active_language = language if language in {"hi", "en"} else self.language
        fmt = _FORMATS.get(content_type.lower(), "ogg")
        if self._convert:
            wav = await to_wav_16k(audio)
            if wav:
                audio, fmt = wav, "wav"
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=60) as client:
                p = await self._pipeline_config(client, active_language)
                r = await client.post(
                    p["url"],
                    headers={p["key_name"]: p["key_value"]},
                    json={
                        "pipelineTasks": [
                            {
                                "taskType": "asr",
                                "config": {
                                    "language": {"sourceLanguage": active_language},
                                    "serviceId": p["service_id"],
                                    "audioFormat": fmt,
                                    "samplingRate": 16000,
                                },
                            }
                        ],
                        "inputData": {"audio": [{"audioContent": base64.b64encode(audio).decode("ascii")}]},
                    },
                )
        except httpx.HTTPError as e:
            raise VoiceError(f"Bhashini request failed: {type(e).__name__}") from e
        if r.status_code >= 300:
            raise VoiceError(f"Bhashini transcription failed: HTTP {r.status_code}")
        try:
            return str(r.json()["pipelineResponse"][0]["output"][0]["source"]).strip()
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise VoiceError("Bhashini transcription returned an unexpected shape") from e


def make_transcriber(settings: Settings) -> Transcriber | None:
    """A Bhashini client when both credentials are set, otherwise None (the channel then replies text-only)."""
    if settings.bhashini_user_id and settings.bhashini_api_key:
        return BhashiniClient(settings.bhashini_user_id, settings.bhashini_api_key, language=settings.bhashini_language)
    return None
