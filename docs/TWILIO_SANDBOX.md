# Twilio WhatsApp Sandbox: text and voice-note setup

This guide configures the existing `POST /whatsapp/incoming` webhook. A Twilio WhatsApp Sandbox transports the voice note; it does **not** transcribe it. The app downloads the Twilio media, calls the configured Bhashini ASR adapter, then passes the transcript into the same `respond(...)` orchestrator and safety gate used by web chat.

## What is already implemented

- Form-encoded Twilio webhook parsing and signature verification when `TWILIO_AUTH_TOKEN` is configured.
- Sender-to-farmer matching, stable `MessageSid` deduplication, and SQLite persistence of processing status/reply.
- Media download restricted to HTTPS Twilio/Twilio CDN hosts, including checking each redirect hop and not forwarding Twilio credentials to the CDN.
- Bhashini ASR adapter with bounded audio size/timeouts and optional `ffmpeg` conversion to 16 kHz mono WAV.
- Voice transcript routed through the same planner and safety gate as typed text; failures ask the farmer to retry rather than inventing a transcript.
- Tests use fake media/transcription services. **The live Twilio + live Bhashini end-to-end flow has not been verified in this environment.**

## 1. Configure the Twilio Sandbox

1. Sign in to Twilio and open **Messaging → Try it out → Send a WhatsApp message / WhatsApp Sandbox**.
2. Follow the Sandbox join instructions from the phone that will be used for the farmer demo.
3. In Sandbox settings, set **When a message comes in** to `https://YOUR-PUBLIC-HTTPS-HOST/whatsapp/incoming` and method to `POST`.
4. The URL must be publicly reachable over HTTPS. For local development, start the backend and expose port 8000 with a tunnel, for example `ngrok http 8000`. Use the HTTPS forwarding URL, not `localhost`.

## 2. Configure `.env`

Copy the repository `.env.example` to `.env` at the repository root (or to `backend/.env`):

```dotenv
TINYFISH_MODE=replay
DB_BACKEND=sqlite
PUBLIC_BASE_URL=https://YOUR-PUBLIC-HTTPS-HOST
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=replace-with-your-auth-token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
WHATSAPP_MESSAGE_RETENTION_DAYS=7
BHASHINI_USER_ID=replace-with-your-bhashini-user-id
BHASHINI_API_KEY=replace-with-your-bhashini-api-key
BHASHINI_LANGUAGE=hi
```

Use the actual Sandbox sender shown in Twilio if it differs from the example. Do not commit `.env` or paste credentials into issue reports. `PUBLIC_BASE_URL` is the public origin only; the app appends `/whatsapp/incoming` and the incoming query string when validating the Twilio signature. Leave it blank only for direct local testing without a proxy.

The sender’s saved farmer profile selects Hindi (`hi`) or English (`en`) ASR; unknown senders use `BHASHINI_LANGUAGE`. Hinglish profiles currently use Hindi ASR. If Bhashini credentials are blank, text messages still work, but voice notes receive an explicit instruction to type the question. Do not describe that as live voice transcription.

## 3. Start the backend

From a terminal:

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

In a second terminal, start a tunnel and update the Twilio callback URL and `PUBLIC_BASE_URL` with its HTTPS origin. If `.env` changes, restart the backend.

## 4. Send test messages

1. Send `hello` in the joined WhatsApp Sandbox conversation. The bot should return a short help prompt.
2. Send `Gehu kahan bechun? 20 quintal`. In replay mode, the response should clearly use recorded demo data and may create a **proposed** ledger entry.
3. Send a short Hindi voice note saying `Gehu kahan bechun?`. With Bhashini configured, the response should echo the recognized transcript before the answer. The transcript then uses the same sell/advisory/claim/scheme routing and safety checks as typed text.
4. Send an unsafe dosing question by text or voice (for example, `Chlorpyrifos kitna ml dalu?`). It should be escalated; the app must not give a dose.
5. Repeat the same message using a Twilio retry/test harness with the same `MessageSid`. The second webhook should not re-run the agent or create another ledger entry.

## 5. Diagnose failures

- **403 invalid signature:** check the exact public HTTPS origin, callback path, query string, and `PUBLIC_BASE_URL`. Twilio signs the public URL, not the internal HTTP URL behind a tunnel/proxy.
- **Voice note asks to type:** check both Bhashini fields are present and the backend was restarted. This response is expected without credentials.
- **Could not understand voice:** check the media download and ASR logs, supported audio type, audio length (maximum 10 MiB), language, and whether `ffmpeg` is installed.
- **Media download failure:** verify the media link is still valid and that the Twilio SID/token belong to the same account. Media redirects are restricted to Twilio domains by design.
- **No reply:** inspect the backend and tunnel request logs. Avoid logging audio bytes, full transcripts, tokens, or signed media URLs.
- **Duplicate webhook:** repeated `MessageSid` values are idempotent within the persisted database. SQLite is the default; if using Supabase, apply the updated `docs/supabase.sql` schema first.

## 6. Sandbox versus production

The Sandbox is for development/testing only. Before production, configure an approved WhatsApp sender and follow current Twilio/WhatsApp template, user-consent, and messaging-window requirements. Run real tests against both Twilio and Bhashini; fake-transport tests do not establish live integration status.

## Data retention

The app does not persist the raw audio. The idempotency table stores the Twilio message ID, sender identifier, status, final reply, and update timestamp to suppress retries. Old idempotency records and cached replies are deleted when the next message arrives, using `WHATSAPP_MESSAGE_RETENTION_DAYS` (7 days by default). SQLite files and transcripts/replies may still contain sensitive operational information; restrict file access, define a deletion schedule, and use a secured persistent database before any real-farmer deployment.
