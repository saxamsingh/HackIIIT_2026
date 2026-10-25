# KhetKaaj

A farmer's agent: **sell** at the mandi that pays most after transport, find the **schemes** you qualify for, and
prepare a crop-damage **claim** dossier. Hindi, Hinglish and English; web app and WhatsApp (text and voice
notes). Powered by [TinyFish](https://tinyfish.ai). The farmer always verifies and submits; KhetKaaj never
submits anything for you, and it never gives a pesticide or fertiliser dose.

Read [CLAUDE.md](CLAUDE.md) for the rules and contracts and [docs/sources.md](docs/sources.md) for where every
number comes from.

## Run it

Needs Python 3.11+ and Node 20+. The default mode is **replay**: recorded fixtures, no network, no API key.

**Windows (PowerShell)**

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy ..\.env.example ..\.env
uvicorn app.main:app --reload
```

**macOS / Linux**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example ../.env
uvicorn app.main:app --reload
```

API on <http://localhost:8000> (docs at `/docs`). In a second terminal, the web app:

```bash
cd web
npm install
npm run dev        # http://localhost:5173 (proxies the API); npm test; npm run build
```

### Scheme discovery and review

No scheme ships **reviewed**, and an unreviewed scheme is never shown to farmers. In the web app, open **Operator → Scheme discovery & review → Discover new scheme notices**. Results remain candidates, and replay mode is explicitly labelled as fixture-based. Then open each cited source, verify the benefit, eligibility rules and deadline, enter a reviewer name, acknowledge that review and publish the record. Auto-discovered records with no structured eligibility rules are blocked from publication until the YAML catalog has been completed and verified.

The command line is also available for the shipped catalog:

```bash
cd backend
python -m app.cli list
python -m app.cli review pm-kisan pmfby kcc --reviewer "Your Name"      # only after source review; or review --all
```

## Check it

```bash
(cd backend && ruff check . && python -m pytest)  # offline backend suite
(cd web && npm ci && npm test && npm run build)  # frontend tests + production build
python scripts/demo_check.py --spawn             # the four demo paths, PASS or FAIL
```

The demo paths: (a) a sell question returns ranked mandis with sources and raises the ledger; (b) the schemes
screen shows 2+ eligible schemes with a packet PDF; (c) a replayed hail warning raises an alert and a claim
dossier; (d) "Chlorpyrifos kitna ml dalu?" is escalated with a ticket and no dose. The Operator button opens a live-backend review panel for tickets, alerts, runs, farmer profiles, proposed ledger entries, scheme discovery and the source-linked scheme review queue.

## Live vs replay behavior

The header and Operator → Integration readiness panel show the configured mode. Replay is intentional by default; it is not live pricing/monitoring. Live TinyFish needs a key and a manual smoke test. WhatsApp voice notes need Twilio plus Bhashini credentials. Watch Mode turns configured monitor webhook changes into deduplicated alerts, including scheme notices that require human review; it does not run a hidden local scheduler. Live monitors need a TinyFish key, a public HTTPS webhook and a secret token; create monitors with `python -m app.scripts.create_monitors --apply` only after reviewing the dry-run output. Scheme matching is rules-based over the local catalog and must not be represented as an official decision.

`SQLITE_PATH=./data/khetkaaj.db` is resolved relative to `backend/`, so starting Uvicorn from the repository root or `backend/` uses the same database. An empty `SQLITE_PATH` is ignored and falls back to `backend/khetkaaj.db`.

## Important MVP security boundary

This is a hackathon/demo build. The API and Operator dashboard do not yet enforce user/operator authentication or row-level access controls. Run it locally or behind a trusted private network with synthetic farmer data; **do not expose it publicly or use it for real farmer records until authentication, authorization, and data-access policies are added.**

## What is real and what is not

- **Offline demo data is illustrative.** Mandi names are real; the prices and dates in `backend/fixtures` are made
  up and labelled so, and every replayed answer is shown as *replay*, never *live*.
- **Live TinyFish has not been run** (no key was available). The client is covered by tests against a fake SDK.
  Run `python -m app.scripts.smoke_live` with a key; it prints the streaming URL, steps and the cost, measured
  from the wallet balance. **Measured cost: not yet measured.**
- Agmarknet's official Daily Price and Arrival Report URL is configured, but automated retrieval is
  unverified: the public filters API returned a database error and the report endpoint required CAPTCHA
  credentials when checked on 25 Oct 2026. Do not bypass CAPTCHA. See `docs/sources.md`. The IMD district
  page and Monitor webhook body also remain unconfirmed; record any permitted successful live run with
  `TINYFISH_RECORD=1`.
- Freight rate and distances are assumptions; the MSP is sourced (2026-27 official, 2027-28 secondary).
- Bhashini voice has never been run against a live key. PDFs are English only (no Devanagari font bundled).

## WhatsApp and voice

`POST /whatsapp/incoming` is the Twilio webhook. Text and voice notes go through the same planner and safety
gate as the web app; the sender's number identifies the farmer. A voice note is downloaded from an allowlisted Twilio host and transcribed with Bhashini (ffmpeg, if installed, converts it to 16 kHz WAV); farmer profiles select Hindi or English ASR, and unknown senders use `BHASHINI_LANGUAGE`. Without Bhashini credentials the farmer gets a polite "please type" reply. Repeated `MessageSid` webhook deliveries are deduplicated in the database. Set `TWILIO_AUTH_TOKEN` to validate signatures and `PUBLIC_BASE_URL` when behind ngrok or Render. See [docs/TWILIO_SANDBOX.md](docs/TWILIO_SANDBOX.md) for step-by-step setup.

## Live TinyFish, monitors, deployment

```bash
# .env: TINYFISH_MODE=live  TINYFISH_API_KEY=...  PUBLIC_BASE_URL=https://...  TINYFISH_WEBHOOK_TOKEN=...
python -m app.scripts.smoke_live              # one Fetch and one short Agent run, with cost
python -m app.scripts.create_monitors         # dry run; add --apply to create the Monitors
```

- **Backend on Render or Railway (free tier):** root `backend/`, build `pip install .`, start
  `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Set the variables from `.env.example`. The free tier
  sleeps and loses its disk, so use `DB_BACKEND=supabase` (run `docs/supabase.sql`) for anything persistent. For a
  local demo, ngrok gives the webhook an https URL.
- **Web on Vercel:** import the repo, root `web/`, preset Vite, set `VITE_API_BASE` to the backend origin, and set
  the backend's `CORS_ORIGINS` to the Vercel origin. Camera and location need https on a phone.

## Who builds what

| Lane | Owner | Files |
|---|---|---|
| Platform | Pushkar | `app/tinyfish`, `app/ladder.py`, `app/replies.py`, `app/orchestrator`, `app/safety`, `app/db.py` |
| Sell + Watch | Saksham | `app/agents/{sell,watch}.py`, `app/rules/{market,weather}.py`, `knowledge/{msp,mandi_costs,weather}.yaml` |
| Subsidy + Claim | Krishyangi | `app/agents/{subsidy,claim}.py`, `app/rules/eligibility.py`, `app/reports/`, `knowledge/schemes/` |
| Web + WhatsApp + voice | Achintya | `web/`, `app/channels/` |
