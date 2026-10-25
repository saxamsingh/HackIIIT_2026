# CLAUDE.md - KhetKaaj

> **DRAFT.** The team's original CLAUDE.md was not available, so this file was written from the six build
> prompts (Prompt 0 to 5). Section numbers match the numbers those prompts cite. If the team has the
> original, diff it against this one: the contracts in section 5 are the part that must agree across code.
>
> **Status:** Prompts 0 to 5 are built. See README "What is real and what is not" for what has not been run live.

## 1. What this is

KhetKaaj helps a small farmer with three money moments, in Hindi, Hinglish or English, on the web and on
WhatsApp: **Sell** (which mandi pays the best price after transport), **Subsidy** (which schemes they
qualify for, with a prefilled draft), and **Claim** (a crop-damage insurance dossier). **Watch Mode**
re-checks official pages and raises an alert when one changes (a hail warning, a new scheme). TinyFish
does the web work; the app adds rules, a safety gate and a ledger of Rs Unlocked.

## 2. Non-negotiable rules

1. **The farmer verifies and submits.** KhetKaaj prepares drafts and dossiers. It never submits a
   form, claim or application to any external portal. Every generated document carries the banner
   "Farmer verifies and submits".
2. **No fact without a source.** Every price, MSP, scheme amount and deadline comes from a cited page
   (`Evidence`). A value that cannot be sourced is shown as an assumption (`assumed: true`) or not shown.
   No hardcoded prices, MSP or deadlines in code. Fixtures are labelled ILLUSTRATIVE until recorded.
3. **Page text never goes into an LLM prompt.** Web pages are untrusted input: a page can contain
   instructions. Pages are parsed by deterministic code (tables, regex, the Agent's `output_schema`).
   An LLM, if used at all, only rephrases already-structured data and sits behind `LLM_PHRASING`.
4. **The safety gate is the last step.** Nothing reaches a farmer except through `safety.gate` (section 8).
5. **No doses, ever.** Pesticide or fertiliser amounts are never given. Dose questions go to a human.
6. **Eligibility is rules, not a model.** Scheme matching is deterministic code over reviewed YAML.
   A scheme with `reviewed: false` is never shown to a farmer.
7. **Be honest about the mode.** `live`, `replay` and `offline sample` are always labelled in the UI.
   A cached answer must never look live.
8. **Tests pass with no network and no API key.** TinyFish, Twilio, Bhashini and Supabase are faked at
   the HTTP layer in tests.
9. **No secrets in the repo.** Keys come from `.env` (git-ignored); `.env.example` lists every variable.
10. **Money counts only when confirmed.** Ledger entries are `projected` until the farmer confirms.

## 3. Stack and dependencies

- Backend: Python 3.11+, FastAPI, pydantic v2, pydantic-settings, httpx, `tinyfish` (official SDK,
  0.11.0), PyYAML, Jinja2 and ReportLab (PDFs), Pillow (EXIF), python-multipart. Dev: pytest,
  pytest-asyncio, ruff. All in `backend/pyproject.toml`; a lane should not need to edit it.
- Database: SQLite by default; Supabase (PostgREST over httpx, no SDK) behind `DB_BACKEND=supabase`.
- Web: Vite, React 18, TypeScript, Tailwind 3. Mobile first (test at 360px). Hindi/English toggle.
- Channels: Twilio WhatsApp webhook, Bhashini speech to text (Prompt 4).

## 4. Repo layout

```
CLAUDE.md  README.md  .env.example  .gitignore
.github/workflows/ci.yml
docs/            sources.md (every cited source) · supabase.sql
knowledge/       demo_farmers.yaml · (later) schemes/*.yaml · msp.yaml · mandi_costs.yaml
backend/
  pyproject.toml
  app/
    main.py factory.py config.py models.py db.py seed.py deps.py files.py
    ladder.py replies.py ledger.py knowledge.py schemes.py discovery.py parsers.py exif.py webhooks.py cli.py
    rules/       market.py weather.py eligibility.py
    reports/     PDF packet and dossier (Jinja templates + ReportLab)
    channels/    whatsapp.py voice.py twilio.py notify.py
    scripts/     smoke_live.py create_monitors.py
    tinyfish/    base.py (WebClient) · replay.py · cache.py · budget.py · live.py · __init__.py
    orchestrator/ triage.py lexicon.py planner.py
    safety/      gate.py dose.py
    agents/      sell.py subsidy.py claim.py watch.py (lane code) · stubs.py (fallbacks) · base.py
    routers/     health chat schemes claim ledger resources webhooks files
  fixtures/tinyfish/   one recorded response per kind: search_ fetch_ agent_ monitor_
  tests/
web/             Vite + React + TS + Tailwind
```

`knowledge/` holds `msp.yaml`, `mandi_costs.yaml`, `weather.yaml`, `schemes/*.yaml`. `scripts/` at the root
holds `demo_check.py` and `export_mocks.py`.

## 5. Contracts

The source of truth is `backend/app/models.py`. Change a model there and update this section in the same
commit. Web types in `web/src/api.ts` mirror it.

**Building blocks.** `Evidence{source_url, kind, title?, quote?, fetched_at, run_id?, assumed}`.
`AgentResult{agent, answer_en, answer_hi, data, evidence[], confidence 0..1, run_id?}` is what an agent
returns to the gate. `GatedResponse{status: answered|escalated|menu, language, intent, reply, agent?, data,
evidence[], confidence, run_id?, ticket_id?, reasons[]}` is what a farmer gets. `run_id` points at the
TinyFish run behind the answer (`GET /api/runs/{id}` has its `streaming_url`).

**Tables (5).** `farmers`, `runs`, `alerts`, `ledger`, `tickets`.

| Table | Key fields |
|---|---|
| `farmers` | id, name, phone, state, district, crops[], land_acres, category (small/marginal/other), language, documents[] |
| `runs` | id, kind (search/fetch/agent/monitor), status, target, **streaming_url**, video_url, result, error, steps, cost_credits, mode (live/replay) |
| `alerts` | id, farmer_id? (null = whole area), type (hail/heavy_rain/scheme/price), title, detail, source_url, evidence[], claim_id? |
| `ledger` | id, farmer_id, kind (sell/subsidy/claim), amount_rs, formula, confirmed |
| `tickets` | id, farmer_id?, intent, query, reason (comma-separated reason codes), status (open/closed) |

**REST routes.**

| Route | Returns |
|---|---|
| `GET /health` | `HealthResponse{status, version, tinyfish_mode, db_backend, demo_state, demo_district}` |
| `POST /api/chat {text, farmer_id?}` | `GatedResponse` (full triage) |
| `POST /api/sell {crop, quantity_qtl, farmer_id?}` | `GatedResponse` from the Sell agent |
| `GET /api/schemes?farmer_id=` | `SchemesResponse{farmer_id, schemes: SchemeMatch[], confidence, note?}`: reviewed schemes only; empty with a `note` when nothing is reviewed (no ticket). `SchemeMatch` adds `needs_info[]`, `reasons[]` |
| `POST /api/claim {farmer_id, crop, event, event_date, photo_names[]}` and multipart `POST /api/claim/photos` (files, optional `device_lat/device_lon`, read for EXIF) | `ClaimResponse{claim_id, status: draft, dossier_url, intimation_deadline?, warnings[], evidence[], confidence}` |
| `GET /api/ledger?farmer_id=` | `LedgerResponse{total_rs (confirmed), projected_rs, entries[]}` |
| `POST /api/ledger/{id}/confirm` | `LedgerEntry` (the farmer's yes) |
| `GET /api/alerts?farmer_id=` · `GET /api/farmers` · `GET /api/runs?kind=&status=&limit=` · `GET /api/runs/{id}` | `Alert[]` · `Farmer[]` · `RunRecord[]` · `RunRecord` |
| `POST /webhooks/tinyfish?token=` | `{ok, run_id}`; 403 on a wrong token when `TINYFISH_WEBHOOK_TOKEN` is set |
| `POST /demo/replay-monitor {fixture_name}` | `Alert`: replays a recorded Monitor run through the alert path |
| `GET /files/{name}` | a generated PDF; names are confined to `FILES_DIR` |

`POST /whatsapp/incoming` is the Twilio webhook (signature checked when `TWILIO_AUTH_TOKEN` is set). A route returns **409** with the hand-off text if the
gate escalates an answer that the route needed in a fixed shape (schemes, claim).

## 6. TinyFish (confirmed against `tinyfish` 0.11.0 and docs.tinyfish.ai, checked while writing Prompt 0)

**Auth and base.** `X-API-Key` header; the SDK reads `api_key=` or the environment. REST base for agents,
runs and monitors: `https://agent.tinyfish.ai`.

**The SDK has an async client.** Use `AsyncTinyFish`; do not wrap the sync one.

| Need | Call | Returns |
|---|---|---|
| Search | `await client.search.query(q, purpose=...)` | `SearchQueryResponse{query, results[{position, title, url, snippet, site_name, date?}], total_results, page}` |
| Fetch | `await client.fetch.get_contents(urls, purpose=..., ttl=0)` (up to 10 urls) | `FetchResponse{results[{url, final_url, title, text, format, links}], errors[{url, error}]}`; per-URL failures do not fail the call |
| Agent, streaming | `client.agent.stream(goal=, url=, output_schema=, on_streaming_url=, on_progress=, on_complete=)` | `AsyncAgentStream`. Note `stream` is a plain method returning the stream, not a coroutine |
| Agent, wait | `await client.agent.run(goal=, url=, ...)` | `AgentRunResponse{status, run_id, result, error, num_of_steps}` |
| Agent, queue | `await client.agent.queue(...)` | `run_id` immediately |
| Poll a run | `await client.runs.get(run_id)` | `Run{status, result, streaming_url, error, ...}` |
| Monitors | `await client.monitors.create(type, config, schedule_cron, webhook_url=, name=, purpose=)`; also `get list pause resume run update cancel` | `MonitorCreateResponse{monitor, run}` |

**Agent run lifecycle.** Statuses: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`. SSE event types
(`POST /v1/automation/run-sse`): `STARTED`, `STREAMING_URL`, `PROGRESS{purpose}`, `HEARTBEAT`, `COMPLETE{status,
result}`. **The SDK names the COMPLETE payload `result_json`; the REST docs call it `result`.** `AgentEvent`
accepts both. SSE cannot resume: if the stream drops, poll `GET /v1/runs/{id}` until the status is terminal.
Store `streaming_url` in the `runs` row the moment the `STREAMING_URL` event arrives. The live-view URL is
shown in an https iframe.

**COMPLETED does not mean it worked.** A run can finish `COMPLETED` with a result saying the site blocked it.
Treat that as a failure (section 2.2): no evidence, no answer. `FAILED` carries `error.category`:
`SYSTEM_FAILURE` (retry after `retry_after`), `AGENT_FAILURE` (fix the input), `BILLING_FAILURE`, `UNKNOWN`.

**Limits.** Two concurrent Agent runs: queue the rest (`TINYFISH_MAX_CONCURRENT_RUNS`). `agent_config.max_steps`
and `mode: strict` are beta-gated and return 403 without access; do not depend on them. Agent runs cost
credits; the budget guard caps them (`TINYFISH_BUDGET_AGENT_RUNS`). Search and Fetch are counted against a
separate cap; whether they are billed was not stated in the docs read, so measure it.

**Webhooks are not signed.** TinyFish documents no signature header. We authenticate our own endpoint by
putting a secret token in the webhook URL: `https://<host>/webhooks/tinyfish?token=<TINYFISH_WEBHOOK_TOKEN>`.
A run webhook (`webhook_url` on run creation, HTTPS only) POSTs `{event: run.completed|run.failed|run.cancelled,
run_id, status, data: <same as GET /v1/runs/{id}>}` once; it retries 3 times on 5xx and network errors.

**Monitors.** `type: "fetch"` watches a page (always fetched fresh), `type: "search"` watches a query. Both take
`schedule_cron` and an optional `webhook_url`. **The Monitor webhook envelope is NOT confirmed**: the docs read
describe the run objects (`FetchMonitorRun{id, is_baseline, results[], errors[]}`) but not the POST body a
monitor sends. `fixtures/tinyfish/monitor_hail.json` follows the run object; confirm the real envelope the
first time a live monitor fires and update the fixture and this paragraph.

**The ladder** (Prompt 1, `app/ladder.py`): try Fetch (cheap) and parse deterministically; only if the page
needs interaction, escalate to an Agent run with an `output_schema`; log which rung answered. Never call
TinyFish from an agent directly: agents take a `WebClient` (`app/tinyfish/base.py`).

**Modes.** `TINYFISH_MODE=replay` reads `backend/fixtures/tinyfish/*.json` (no network). `live` calls TinyFish.
`TINYFISH_RECORD=1` (live only, Prompt 1) writes each response as a fixture. A fixture is
`{kind, default?, request, response}`; a request matches on its canonical key, else the kind's `default`
fixture answers. Fixture files marked ILLUSTRATIVE are placeholders to be replaced by recordings.

## 7. Agents (one lane each)

Each agent is `async def run(ctx: AgentContext) -> AgentResult` in `app/agents/<name>.py`, using only
`ctx.web`. Sell, Subsidy and Claim are implemented; Watch is driven by webhooks (`handle_monitor_payload`).
`agents/stubs.py` remains only as a labelled fallback for a module that raises `NotImplementedError`.

- **Sell** (Saksham). Input: crop, quantity, district. Pure functions in `rules/market.py`: net price =
  modal price minus transport; rank mandis by net price; compare with MSP; sanity and staleness checks on
  scraped prices; confidence from freshness and agreement; ledger value = (best net - nearest net) x quintals,
  with the formula stored. Transport cost per km and mandi distances live in `knowledge/mandi_costs.yaml`
  with sources, marked `assumed: true` where not cited. Output `data.options`, `data.best`, `data.msp`, one
  `Evidence` per price line.
- **Watch Mode** (Saksham). A Monitor fires `POST /webhooks/tinyfish`; the Watch agent turns it into an
  `Alert`, notifies by WhatsApp (through an interface so tests can fake it) and, for hail or heavy rain,
  starts claim preparation. `POST /demo/replay-monitor` drives the same path offline.
  `scripts/create_monitors.py` creates the Monitors.
- **Subsidy** (Krishyangi). `knowledge/schemes/*.yaml`: id, name, benefit, eligibility rules, documents,
  official URL, source and `reviewed`. `python -m app.cli review <id>` flips the flag. Discovery uses Search
  and Fetch to find new circulars and writes new YAML with `reviewed: false`. `rules/eligibility.py` is a
  deterministic matcher that also returns `missing_docs`. `reports/` renders a prefilled packet PDF.
- **Claim** (Krishyangi). Reads GPS and timestamp from photo EXIF (warns if missing), adds IMD evidence and the
  **cited** intimation deadline, renders a dossier PDF. It prepares; it never submits. `prepare_from_alert`
  lets Watch Mode start a claim.

## 8. Orchestrator and safety gate

**Triage** (`orchestrator/triage.py`, pure, tested): language (`hi` Devanagari, `hinglish` Hindi in Latin
letters, `en`), intent (`sell`, `subsidy`, `claim`, `advisory`, `unknown`), crop, quantity (converted to
quintals; kg/100, tonne x10), and `asks_dose`. **Advisory is checked first**: a pesticide or fertiliser name, a
spraying word, or "how much" with a chemical unit makes it advisory, so a dose question cannot be answered by
the Sell agent. kg, gram and litre alone do not count ("kitna kg bechun" is a sell question).

**Planner.** `unknown` returns a menu. `sell`/`subsidy`/`claim` run an agent. `advisory` has no agent and
goes straight to the gate. Every other path ends in `gate`.

**Gate** (`safety/gate.py`). An answer is withheld if any of these hold, and every reason is reported:

| Reason code | When |
|---|---|
| `dose_question` | triage says the question asks for a dose |
| `missing_evidence` | the result has no `Evidence` |
| `low_confidence` | `confidence < CONFIDENCE_THRESHOLD` (0.85; exactly 0.85 passes) |
| `dose_in_answer` | `contains_dose` finds a dose in `answer_en`, `answer_hi` or any string in `data` |

On withholding: create a `Ticket` (query and reason codes only), reply with a neutral hand-off in the
farmer's language naming the ticket and telling them not to spray or apply anything, and return **nothing of
the withheld answer** (`data={}`, `evidence=[]`, `confidence=0`). A test pins that the answer text appears
nowhere in the response or the ticket.

**Dose detector** (`safety/dose.py`). Matches a number plus a small unit (ml, cc, mg, मिली) anywhere, or a
larger unit (g, kg, litre) only with a per-area or per-volume denominator (`per acre`, `/ha`, `/L`, `प्रति
लीटर`, `per pump`). Handles Devanagari digits. Does not match `20 quintal`, `Rs 2,492 per quintal`,
`Rs 24/kg`, `70 km`, `2 acres`, `30 November`. It errs towards "dose": a false positive only sends the
farmer to a human. Add a failing test before changing it.

## 9. Web app

Mobile first, tested at 360px. Bottom tabs: **Home** (Rs Unlocked, alerts, ask box), **Sell**, **Schemes**,
**Claim** (camera input, geolocation), **Ledger** (big Rs total). Hindi/English toggle, remembered in
localStorage (wrapped in try/catch). A badge shows `live`, `replay` or `offline sample`. `web/src/api.ts` has a
typed function per route and falls back to `web/src/mocks/*.json` **only** when the backend cannot be
reached. `LiveRunViewer` frames `streaming_url` in an https iframe, falls back to a `video_url`, and always
shows the step log. Never show a recommendation from an escalated response.

## 10. Environment variables

All are fields of `backend/app/config.py` and listed in `.env.example`. Names are case-insensitive.

`TINYFISH_MODE` (replay|live, default replay) · `TINYFISH_API_KEY` · `TINYFISH_RECORD` ·
`TINYFISH_BUDGET_AGENT_RUNS` (10) · `TINYFISH_BUDGET_FREE_CALLS` (200) · `TINYFISH_MAX_CONCURRENT_RUNS` (2) ·
`TINYFISH_WEBHOOK_TOKEN` · `TINYFISH_CACHE_TTL_SECONDS` (3600) · `DB_BACKEND` (sqlite|supabase) · `SQLITE_PATH` ·
`SUPABASE_URL` · `SUPABASE_KEY` · `DEMO_STATE` · `DEMO_DISTRICT` · `CONFIDENCE_THRESHOLD` (0.85) ·
`PUBLIC_BASE_URL` · `CORS_ORIGINS` · `TWILIO_ACCOUNT_SID` · `TWILIO_AUTH_TOKEN` · `TWILIO_WHATSAPP_FROM` ·
`BHASHINI_USER_ID` · `BHASHINI_API_KEY` · `LLM_PHRASING` (off). Web: `VITE_API_BASE`.

`DEMO_STATE` and `DEMO_DISTRICT` are **placeholders** (Uttar Pradesh, Meerut) until the Sell lane picks the
district in `docs/sources.md`; the seeded farmers take whatever these say.

## 11. Demo script (must work with Wi-Fi off, in replay mode)

1. WhatsApp or web: "Gehu kahan bechun? 20 quintal" -> ranked mandis with net price and sources, and the
   projected ledger value goes up.
2. Schemes screen -> two or more eligible reviewed schemes -> a packet PDF downloads.
3. `POST /demo/replay-monitor {"fixture_name": "hail"}` -> an alert on Home and a claim dossier PDF.
4. "Chlorpyrifos kitna ml dalu?" -> escalation, neutral hand-off, a ticket is created, no dose shown.

`scripts/demo_check.py` (Prompt 5) runs these and prints PASS or FAIL.

## 12. Working rules

- One lane per person; touch only your files plus `docs/sources.md` (keep your own section). Contract changes
  (`models.py`, section 5) go through Pushkar. Branch per lane, PR when your checks pass.
- Done means: `ruff check .` and `pytest` pass in `backend/` with no network; `npm run build` passes in `web/`.
- Research before code: write sources to `docs/sources.md`, show them, wait for an OK. Mark anything not
  taken from a source `assumed: true`.
- Use `BossLogger`-style structured logging via the standard `logging` module; never log keys, phone
  numbers or farmer text beyond what a ticket needs.
- Keep files small and typed. Prefer a failing test first for anything the gate or triage decides.
