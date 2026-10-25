# KhetKaaj MVP verification matrix

This matrix reflects inspection of `KhetKaaj_HackIIITD_2026_AgriVerse.pptx`, the supplied repository, and the checks run in this workspace. `PASS` means local implementation/test evidence; it does not imply live-provider verification.

| Pitch / implementation requirement | Status | Implementation evidence | Verification / remaining work |
|---|---|---|---|
| Farmer web app, mobile layout, Hindi/English toggle | PARTIAL | `web/src/App.tsx`, `web/src/i18n.tsx`, farmer screens | Frontend build could not be run here because `npm ci` did not complete; rebuild with Node 20+ on a network-enabled machine. Operator dashboard strings are English-only. |
| Sell Agent ranks mandi options after freight | PASS (replay) | `backend/app/agents/sell.py`, `backend/app/rules/market.py`, YAML fixtures | `scripts/demo_check.py --spawn`: sell path passed, six options ranked. Prices are illustrative replay data, not live prices. |
| Scheme matching and draft packet PDF | PASS for reviewed/demo data | `backend/app/agents/subsidy.py`, `backend/app/rules/eligibility.py`, `backend/app/reports/` | Demo script passed. Schemes intentionally require review; official content, deadlines and application links must be reviewed/refreshed before real use. |
| Crop-damage claim and evidence dossier | PASS (replay/local) | `backend/app/agents/claim.py`, `/api/claim/photos`, report generation | Demo script passed hail replay + dossier generation. No insurer submission is made; real weather data and real claims remain unverified. |
| Watch Mode / alert deduplication | PASS (replay); live UNVERIFIED | `backend/app/agents/watch.py`, `POST /demo/replay-monitor`, TinyFish webhook | Hail replay scenario passed. Live monitor creation/provider payloads require a TinyFish key and real endpoint verification. |
| Live TinyFish run viewer | PARTIAL | `web/src/components/LiveRunViewer.tsx`, `/api/runs`, `backend/app/tinyfish/` | Replay/local viewer paths exist. No TinyFish API key was provided, so live browser execution and live SSE stream are not verified. |
| Safety gate and human escalation | PASS (local tests/replay) | `backend/app/safety/`, orchestrator, tickets | Dose question is escalated without a dose in demo check; gate tests pass. Clinical/agronomic correctness beyond configured rules needs expert review. |
| Proposed ledger + explicit confirmation | PASS (local) | `backend/app/ledger.py`, `/api/ledger`, `/api/ledger/{id}/confirm` | Local ledger persistence and confirmation tests pass. A confirmed amount is a recorded estimate, not money received or an external transaction. |
| Twilio WhatsApp text + voice note | PARTIAL / LIVE BLOCKED | `backend/app/channels/whatsapp.py`, `voice.py`, `twilio.py` | Fake-provider tests cover transcription, signature, fetch failure, safety routing and now webhook idempotency. Real Twilio and Bhashini credentials were unavailable; follow `docs/TWILIO_SANDBOX.md`. |
| Secure voice-media retrieval | PASS (mocked tests) | `TwilioMediaFetcher` | HTTPS allowlist, size limits and per-hop redirect validation tested. Real Twilio CDN behavior still needs live smoke testing. |
| CSC/FPO operator dashboard | IMPLEMENTED; frontend build UNVERIFIED | `web/src/screens/OperatorDashboard.tsx`, `GET /api/tickets` | Dashboard reads farmers, alerts, runs, all ledger entries and open tickets; it can confirm ledger entries. It is a hackathon/demo view with no operator authentication and must not be exposed publicly as-is. |
| SQLite local development | PASS | `backend/app/db.py`, app factory | Backend tests and demo script pass; DB file is generated locally and ignored by Git. |
| Supabase/PostGIS architecture | PARTIAL | Supabase PostgREST adapter, `docs/supabase.sql` | Adapter/schema exist, but live credentials were not provided. PostGIS-specific geospatial queries are not verified. |
| ChromaDB RAG / Qwen architecture listed in pitch | MISSING / NOT VERIFIED | Current path primarily uses curated YAML/rules and configured provider adapters | Do not claim ChromaDB or Qwen is active. Add only if required for the judging/demo contract and integrate into an actual request path. |
| TinyFish Browser/context profiles / OTP handoff | UNVERIFIED / PARTIAL | TinyFish abstraction and run viewer | No live key or operator session was available. Browser profiles, OTP handoff and screenshots are not proven end to end. |
| Production identity, operator authorization, retention policy | BLOCKED / NOT PRODUCTION READY | Demo-oriented API and SQLite baseline | Add authentication/authorization, access controls, deletion workflows, monitoring and deployment secrets management before handling real farmer data. |

## Checks executed

- `cd backend && python -m pytest -q` — **353 passed** after changes.
- `python scripts/demo_check.py --spawn` — **4/4 demo scenarios passed** after webhook/media hardening.
- `cd web && npm test -- --reporter=dot` — **could not start**: `vitest: not found` after frontend dependency installation did not complete.
- `cd web && npm run build` — **failed before compiling app code**: TypeScript could not find `vite/client` because the local package install was incomplete. `npm ci --offline` confirmed a required package was not cached (`ENOTCACHED`).
- TypeScript syntax check using the globally installed TypeScript transpiler — **18 TS/TSX files, 0 syntax diagnostics**; this is not a semantic type-check or production build.
- `python -m compileall -q backend/app` — **passed**.
- `ruff check .` — **not run**: Ruff is not installed in this environment.
- Live Twilio, Bhashini, TinyFish, and Supabase smoke tests — **not run**: credentials were not present.
