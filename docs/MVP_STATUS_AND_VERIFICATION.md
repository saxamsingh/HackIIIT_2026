# KhetKaaj MVP: status and verification

## What this build does locally

- Sell workflow runs the existing price extraction and net-realization calculations. In replay mode, portal results are saved fixtures and explicitly not current prices.
- Scheme workflow evaluates reviewed local YAML criteria, explains unknown facts / missing documents, links sources and creates a draft packet. A source-linked operator review queue now allows one-by-one publication; unreviewed schemes remain hidden. Eligibility is an aid, not an official decision.
- Crop claim workflow validates uploaded images, checks EXIF metadata, associates available weather evidence and creates a dossier PDF. It never submits an insurance claim.
- Safety gate escalates pesticide/chemical dosing questions instead of returning dose instructions.
- Ledger stores proposed value until a user/operator explicitly confirms it.
- Watch Mode processes configured TinyFish monitor webhooks; weather alerts can prepare claim drafts, and scheme-monitor changes create source-linked, deduplicated human-review alerts scoped to the configured state. Baseline monitor runs are ignored. Live scheduled monitoring is not active until real monitors/webhooks are configured.
- Operator dashboard surfaces backend farmers, alerts, runs, tickets and ledger entries; operators can explicitly trigger scheme discovery and review source-linked candidates. Auto-discovered records with no structured eligibility rules cannot be published.
- WhatsApp code accepts Twilio text/media webhooks and routes the text/transcript through the same orchestrator. Real voice transcription and WhatsApp send require provider credentials and live testing.

## Known external blockers

| Feature | Local status | What is needed to verify live |
|---|---|---|
| TinyFish portal reads | Replay by default | `TINYFISH_MODE=live`, valid API key, run `python -m app.scripts.smoke_live` and verify source/date/result |
| Real mandi prices | Not verified in this workspace | TinyFish live, current portal access and matching parser output; never use fixture values as current quotes |
| Government schemes | Local rules + cited catalog; publish requires human review | Human reviews source sites and state-specific/current eligibility; scheme data refresh process is not automated into an official determination |
| Automated Watch Mode | Webhook/replay handler exists | HTTPS public base URL, token, live TinyFish, then `python -m app.scripts.create_monitors --apply`; inspect first real webhook |
| WhatsApp text | Webhook implementation exists | Twilio Sandbox details, public HTTPS URL and valid signature / outbound send test |
| WhatsApp voice note | Pipeline/adapter exists, not live-verified | Twilio + Bhashini credentials, compatible audio and one real round-trip voice-note test |
| Supabase/PostGIS / ChromaDB / Qwen | Not treated as active unless separately configured | Provider/schema/model config and real-path test; do not infer use from the pitch deck alone |
| Frontend production build | Unverified in this workspace | Complete `npm ci`, then `npm test` and `npm run build` with network access |

## Tests executed after these changes

- `python -m compileall -q backend/app` — passed.
- `(cd backend && python -m pytest -q)` — 363 passed.
- `python scripts/demo_check.py --spawn` — 4/4 sell, scheme packet PDF, hail/claim dossier and safety escalation scenarios passed.
- TypeScript/TSX syntax transpilation — 18 files, no syntax errors. Frontend dependency installation could not complete because the npm registry was unreachable from this environment; therefore `npm test` and a production build remain unverified.

## Security note

This is a hackathon/local MVP, not a production farmer-data system. Authentication, role-based access control, per-farmer authorization and production data-retention policies still need to be implemented before exposing it publicly.
