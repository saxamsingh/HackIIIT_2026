"""WhatsApp and voice: fake Twilio payloads, a fake Bhashini, no network."""

import base64
from urllib.parse import urlencode

import httpx
import pytest
from fastapi.testclient import TestClient

from app.channels import make_notifier, twilio, voice, whatsapp
from app.channels.notify import NullNotifier
from app.factory import create_app

FORM = {"Content-Type": "application/x-www-form-urlencoded"}
URL = "http://testserver/whatsapp/incoming"
SENDER = "whatsapp:+910000000001"  # the seeded farmer_demo_1


class FakeTranscriber:
    def __init__(self, text="Gehu kahan bechun? 20 quintal", error=None):
        self.text, self.error, self.calls = text, error, []

    async def transcribe(self, audio, content_type, language=None):
        self.calls.append((audio, content_type, language))
        if self.error:
            raise self.error
        return self.text


async def fake_media(url):
    return b"OGG-BYTES", "audio/ogg"


def make_client(settings, transcriber=None, fetch_media=fake_media) -> TestClient:
    app = create_app(settings)
    app.state.transcriber = transcriber
    app.state.media_fetcher = fetch_media
    return TestClient(app)


def body(**extra) -> str:
    return urlencode({"From": SENDER, **extra})


def voice_form(**extra) -> str:
    fields = {
        "Body": "", "NumMedia": "1", "MediaContentType0": "audio/ogg",
        "MediaUrl0": "https://api.twilio.com/2010-04-01/Accounts/AC1/Messages/MM1/Media/ME1", **extra,
    }
    return body(**fields)


def reply_text(r) -> str:
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    return r.text


# --- text -------------------------------------------------------------------------------------------------------
def test_a_text_question_gets_the_same_sourced_answer_as_the_web_app(settings):
    c = make_client(settings)
    r = reply_text(c.post("/whatsapp/incoming", content=body(Body="Gehu kahan bechun? 20 quintal"), headers=FORM))
    assert r.startswith("<?xml") and "<Message>" in r and "₹2,612" in r and "Delhi (Azadpur)" in r
    # the sender was recognised by phone number, so the question reached the ledger
    ledger = c.get("/api/ledger", params={"farmer_id": "farmer_demo_1"}).json()
    assert ledger["projected_rs"] == 1440


def test_twilio_retry_does_not_repeat_sell_or_send_another_twiML_reply(settings):
    c = make_client(settings)
    payload = body(Body="Gehu kahan bechun? 20 quintal", MessageSid="SM_IDEMPOTENT_001")
    first = c.post("/whatsapp/incoming", content=payload, headers=FORM)
    assert "₹2,612" in first.text
    before = c.get("/api/ledger", params={"farmer_id": "farmer_demo_1"}).json()

    retry = c.post("/whatsapp/incoming", content=payload, headers=FORM)
    after = c.get("/api/ledger", params={"farmer_id": "farmer_demo_1"}).json()
    assert retry.status_code == 200 and "<Response></Response>" in retry.text
    assert after["projected_rs"] == before["projected_rs"]
    assert len(after["entries"]) == len(before["entries"])


def test_an_unknown_number_is_still_answered(settings):
    c = make_client(settings)
    r = reply_text(c.post("/whatsapp/incoming", content=urlencode({"From": "whatsapp:+15550001", "Body": "hello"}),
                          headers=FORM))
    assert "sell your crop" in r or "fasal" in r.lower()


def test_a_dose_question_over_whatsapp_is_handed_to_a_person(settings):
    c = make_client(settings)
    r = reply_text(c.post("/whatsapp/incoming", content=body(Body="Chlorpyrifos kitna ml dalu?"), headers=FORM))
    assert "tkt_" in r and "dawai" in r  # a ticket number and the neutral hand-off, no dose
    assert len(c.app.state.repo.list_tickets()) == 1


def test_the_reply_is_xml_escaped_and_length_limited():
    assert "a &lt; b &amp; c" in whatsapp.twiml("a < b & c").body.decode()
    message = whatsapp.twiml("y" * 5000).body.decode().split("<Message>")[1].split("</Message>")[0]
    assert len(message) == whatsapp.MAX_REPLY_CHARS


def test_a_failing_portal_is_a_friendly_reply_not_a_500(settings, monkeypatch):
    from app.agents import sell
    from app.tinyfish import WebClientError

    async def down(ctx):
        raise WebClientError("503")

    monkeypatch.setattr(sell, "run", down)
    r = reply_text(make_client(settings).post(
        "/whatsapp/incoming", content=body(Body="Gehu kahan bechun?"), headers=FORM))
    assert "portal" in r and "503" not in r


# --- signatures -------------------------------------------------------------------------------------------------
def test_signature_matches_the_official_sdk_output():
    # Computed with twilio.request_validator.RequestValidator.compute_signature for the same inputs.
    params = {"CallSid": ["CA1234567890ABCDE"], "Caller": ["+12349013030"], "Digits": ["1234"],
              "From": ["+12349013030"], "To": ["+18005551212"]}
    assert twilio.signature_for("https://mycompany.com/myapp.php?foo=1&bar=2", params, "12345") == \
        "0/KCTR6DLpKmkAf8muzZqo1nDgQ="


def test_bad_or_missing_signature_is_rejected_when_a_token_is_set(settings):
    settings.twilio_auth_token = "secret"
    c = make_client(settings)
    payload = body(Body="Gehu kahan bechun?")
    assert c.post("/whatsapp/incoming", content=payload, headers=FORM).status_code == 403
    assert c.post("/whatsapp/incoming", content=payload, headers={**FORM, "X-Twilio-Signature": "nope"}).status_code == 403


def test_a_valid_signature_is_accepted(settings):
    settings.twilio_auth_token = "secret"
    params = {"From": [SENDER], "Body": ["Gehu kahan bechun?"]}
    sig = twilio.signature_for(URL, params, "secret")
    r = make_client(settings).post(
        "/whatsapp/incoming", content=body(Body="Gehu kahan bechun?"), headers={**FORM, "X-Twilio-Signature": sig})
    assert r.status_code == 200


def test_signature_uses_the_public_url_behind_a_proxy(settings):
    settings.twilio_auth_token, settings.public_base_url = "secret", "https://khet.example.com/"
    sig = twilio.signature_for(
        "https://khet.example.com/whatsapp/incoming", {"From": [SENDER], "Body": ["hello"]}, "secret")
    r = make_client(settings).post(
        "/whatsapp/incoming", content=body(Body="hello"), headers={**FORM, "X-Twilio-Signature": sig})
    assert r.status_code == 200


def test_repeated_parameter_values_are_deduplicated_like_the_sdk_does():
    one = twilio.signature_for("https://x.io/p", {"a": ["1", "1"]}, "t")
    assert one == twilio.signature_for("https://x.io/p", {"a": ["1"]}, "t")


# --- voice ------------------------------------------------------------------------------------------------------
def test_a_voice_note_is_transcribed_then_answered_like_text(settings):
    t = FakeTranscriber()
    r = reply_text(make_client(settings, t).post("/whatsapp/incoming", content=voice_form(), headers=FORM))
    assert 'Suna: "Gehu kahan bechun? 20 quintal"' in r and "₹2,612" in r
    assert t.calls == [(b"OGG-BYTES", "audio/ogg", "hi")]


def test_voice_note_uses_the_farmer_profile_language_for_asr(settings):
    from app.models import Farmer

    app_client = make_client(settings, FakeTranscriber())
    app_client.app.state.repo.upsert_farmer(Farmer(
        id="farmer_demo_1", name="Demo Farmer", phone="+910000000001", state="Uttar Pradesh",
        district="Meerut", crops=["wheat"], land_acres=1.0, language="en",
    ))
    r = reply_text(app_client.post("/whatsapp/incoming", content=voice_form(), headers=FORM))
    assert r.startswith("<?xml")
    assert app_client.app.state.transcriber.calls == [(b"OGG-BYTES", "audio/ogg", "en")]


def test_a_voice_note_without_bhashini_gets_a_polite_text_only_reply(settings):
    r = reply_text(make_client(settings, None).post("/whatsapp/incoming", content=voice_form(), headers=FORM))
    assert "voice note" in r and "likhkar" in r


def test_a_voice_failure_is_friendly_and_leaks_nothing(settings):
    t = FakeTranscriber(error=voice.VoiceError("secret internal detail"))
    r = reply_text(make_client(settings, t).post("/whatsapp/incoming", content=voice_form(), headers=FORM))
    assert "samajh nahi aayi" in r and "secret internal detail" not in r


def test_a_blank_transcript_is_friendly(settings):
    r = reply_text(make_client(settings, FakeTranscriber(text="  ")).post(
        "/whatsapp/incoming", content=voice_form(), headers=FORM))
    assert "samajh nahi aayi" in r


def test_a_spoken_dose_question_is_still_handed_to_a_person(settings):
    t = FakeTranscriber(text="Chlorpyrifos kitna ml dalu")
    r = reply_text(make_client(settings, t).post("/whatsapp/incoming", content=voice_form(), headers=FORM))
    assert "tkt_" in r


def test_typed_text_wins_over_attached_audio(settings):
    t = FakeTranscriber()
    make_client(settings, t).post("/whatsapp/incoming", content=voice_form(Body="hello"), headers=FORM)
    assert t.calls == []


def test_a_failed_download_is_friendly(settings):
    async def broken(url):
        raise voice.VoiceError("HTTP 404")

    r = reply_text(make_client(settings, FakeTranscriber(), broken).post(
        "/whatsapp/incoming", content=voice_form(), headers=FORM))
    assert "samajh nahi aayi" in r


def test_media_is_only_fetched_from_twilio_hosts():
    for ok in ("https://api.twilio.com/x", "https://media.twiliocdn.com/x"):
        assert voice.media_host_allowed(ok)
    for bad in (
        "http://api.twilio.com/x", "https://evil.example.com/x", "https://api.twilio.com.evil.example/x",
        "file:///etc/passwd", "https://169.254.169.254/latest", "https://api.twilio.com:8443/x",
        "https://attacker@api.twilio.com/x", "https://api.twilio.com:bad/x",
    ):
        assert not voice.media_host_allowed(bad)


async def test_the_default_fetcher_refuses_foreign_hosts(settings):
    with pytest.raises(voice.VoiceError):
        await voice.TwilioMediaFetcher(settings)("http://169.254.169.254/latest/meta-data")


async def test_the_fetcher_downloads_with_basic_auth_and_strips_the_content_type(settings):
    settings.twilio_account_sid, settings.twilio_auth_token = "AC1", "tok"
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, content=b"abc", headers={"content-type": "audio/ogg; codecs=opus"})

    fetcher = voice.TwilioMediaFetcher(settings, httpx.MockTransport(handler))
    assert await fetcher("https://api.twilio.com/m") == (b"abc", "audio/ogg") and seen["auth"].startswith("Basic ")


async def test_oversized_and_failed_downloads_are_errors(settings, monkeypatch):
    monkeypatch.setattr(voice, "MAX_AUDIO_BYTES", 10)
    big = voice.TwilioMediaFetcher(settings, httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 50)))
    with pytest.raises(voice.VoiceError, match="too large"):
        await big("https://api.twilio.com/m")
    missing = voice.TwilioMediaFetcher(settings, httpx.MockTransport(lambda r: httpx.Response(404)))
    with pytest.raises(voice.VoiceError, match="404"):
        await missing("https://api.twilio.com/m")


async def test_media_redirects_are_allowlisted_and_credentials_are_not_forwarded_to_cdn(settings):
    settings.twilio_account_sid, settings.twilio_auth_token = "AC1", "tok"
    seen = []

    def handler(request):
        seen.append((request.url.host, request.headers.get("authorization")))
        if request.url.host == "api.twilio.com":
            return httpx.Response(302, headers={"location": "https://media.twiliocdn.com/audio"})
        return httpx.Response(200, content=b"voice", headers={"content-type": "audio/ogg"})

    fetcher = voice.TwilioMediaFetcher(settings, httpx.MockTransport(handler))
    assert await fetcher("https://api.twilio.com/media") == (b"voice", "audio/ogg")
    assert seen[0][0] == "api.twilio.com" and seen[0][1].startswith("Basic ")
    assert seen[1] == ("media.twiliocdn.com", None)


async def test_media_redirect_to_untrusted_host_is_rejected_before_following(settings):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://169.254.169.254/latest/meta-data"})

    fetcher = voice.TwilioMediaFetcher(settings, httpx.MockTransport(handler))
    with pytest.raises(voice.VoiceError, match="redirect host not allowed"):
        await fetcher("https://api.twilio.com/media")
    assert len(calls) == 1


async def test_unsupported_download_content_type_is_rejected(settings):
    fetcher = voice.TwilioMediaFetcher(
        settings,
        httpx.MockTransport(
            lambda r: httpx.Response(200, content=b"not audio", headers={"content-type": "text/html"})
        ),
    )
    with pytest.raises(voice.VoiceError, match="unsupported audio content type"):
        await fetcher("https://api.twilio.com/media")


# --- Bhashini ---------------------------------------------------------------------------------------------------
def bhashini(calls, transcript="गेहूं कहां बेचूं"):
    def handler(request):
        calls.append(request)
        if request.url.host == "meity-auth.ulcacontrib.org":
            return httpx.Response(200, json={
                "pipelineResponseConfig": [{"config": [{"serviceId": "asr-svc"}]}],
                "pipelineInferenceAPIEndPoint": {
                    "callbackUrl": "https://dhruva.example/services/inference/pipeline",
                    "inferenceApiKey": {"name": "Authorization", "value": "infer-key"}}})
        return httpx.Response(200, json={"pipelineResponse": [{"output": [{"source": transcript}]}]})

    return handler


async def test_bhashini_looks_up_the_pipeline_once_then_transcribes():
    calls: list = []
    client = voice.BhashiniClient("uid", "key", transport=httpx.MockTransport(bhashini(calls)), convert=False)
    assert await client.transcribe(b"audio", "audio/ogg") == "गेहूं कहां बेचूं"
    await client.transcribe(b"audio", "audio/ogg")
    lookups = [c for c in calls if c.url.host == "meity-auth.ulcacontrib.org"]
    assert len(lookups) == 1 and lookups[0].headers["userid"] == "uid" and lookups[0].headers["ulcaapikey"] == "key"
    infer = next(c for c in calls if c.url.host == "dhruva.example")
    sent = infer.read().decode().replace(" ", "")
    assert infer.headers["authorization"] == "infer-key" and "asr-svc" in sent and '"sourceLanguage":"hi"' in sent
    assert base64.b64encode(b"audio").decode() in sent and '"audioFormat":"ogg"' in sent


async def test_bhashini_caches_separate_hindi_and_english_pipelines():
    calls: list = []
    client = voice.BhashiniClient(
        "uid", "key", transport=httpx.MockTransport(bhashini(calls, "recognized")), convert=False
    )
    assert await client.transcribe(b"hi", "audio/ogg", "hi") == "recognized"
    assert await client.transcribe(b"en", "audio/ogg", "en") == "recognized"
    assert await client.transcribe(b"en2", "audio/ogg", "en") == "recognized"
    lookups = [c for c in calls if c.url.host == "meity-auth.ulcacontrib.org"]
    languages = [c.read().decode() for c in lookups]
    assert len(lookups) == 2
    assert any('"sourceLanguage":"hi"' in payload for payload in languages)
    assert any('"sourceLanguage":"en"' in payload for payload in languages)


@pytest.mark.parametrize("handler", [lambda r: httpx.Response(401), lambda r: httpx.Response(200, json={"x": 1})])
async def test_bhashini_errors_become_voice_errors(handler):
    client = voice.BhashiniClient("u", "k", transport=httpx.MockTransport(handler), convert=False)
    with pytest.raises(voice.VoiceError):
        await client.transcribe(b"a", "audio/ogg")


def test_a_transcriber_needs_both_credentials(settings):
    assert voice.make_transcriber(settings) is None
    settings.bhashini_user_id = "u"
    assert voice.make_transcriber(settings) is None
    settings.bhashini_api_key = "k"
    assert isinstance(voice.make_transcriber(settings), voice.BhashiniClient)


# --- outbound ---------------------------------------------------------------------------------------------------
async def test_send_posts_a_whatsapp_message(settings):
    settings.twilio_account_sid, settings.twilio_auth_token = "AC1", "tok"
    settings.twilio_whatsapp_from = "+14155238886"
    seen = {}

    def handler(request):
        seen["url"], seen["body"] = str(request.url), request.read().decode()
        return httpx.Response(201, json={})

    assert await twilio.TwilioNotifier(settings, httpx.MockTransport(handler)).send("+919800000000", "Hail warning")
    assert "Accounts/AC1/Messages.json" in seen["url"]
    assert "whatsapp%3A%2B14155238886" in seen["body"] and "whatsapp%3A%2B919800000000" in seen["body"]


async def test_send_without_credentials_or_on_error_returns_false(settings):
    assert await twilio.TwilioNotifier(settings).send("+91", "x") is False
    settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_whatsapp_from = "AC1", "t", "+1"
    assert await twilio.TwilioNotifier(settings, httpx.MockTransport(lambda r: httpx.Response(500))).send("+91", "x") is False

    def down(request):
        raise httpx.ConnectError("no network")

    assert await twilio.TwilioNotifier(settings, httpx.MockTransport(down)).send("+91", "x") is False


def test_the_notifier_is_twilio_only_when_fully_configured(settings):
    assert isinstance(make_notifier(settings), NullNotifier)
    settings.twilio_account_sid, settings.twilio_auth_token = "AC1", "t"
    assert isinstance(make_notifier(settings), NullNotifier)
    settings.twilio_whatsapp_from = "+1"
    assert isinstance(make_notifier(settings), twilio.TwilioNotifier)


def test_farmers_are_found_by_phone_whatever_the_formatting(settings):
    c = make_client(settings)
    repo = c.app.state.repo
    for sender in ("whatsapp:+910000000002", "+91 0000 000 002", "910000000002"):
        assert whatsapp.farmer_for(repo, sender).id == "farmer_demo_2"
    assert whatsapp.farmer_for(repo, "whatsapp:+15550001") is None and whatsapp.farmer_for(repo, "") is None


def test_the_audio_attachment_is_found_only_when_it_is_audio():
    form = {"NumMedia": ["2"], "MediaContentType0": ["image/jpeg"], "MediaUrl0": ["https://a"],
            "MediaContentType1": ["audio/ogg"], "MediaUrl1": ["https://b"]}
    assert whatsapp.audio_media(form) == ("https://b", "audio/ogg")
    assert whatsapp.audio_media({"NumMedia": ["0"]}) is None and whatsapp.audio_media({"NumMedia": ["x"]}) is None
