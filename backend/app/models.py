"""The API contract (CLAUDE.md section 5). Change a model here and update the section in the same commit.

Groups: shared building blocks, persisted farmer/run/alert/ledger/ticket/channel-message records, request bodies, and response bodies.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Language = Literal["hi", "en", "hinglish"]
Intent = Literal["sell", "subsidy", "claim", "advisory", "unknown"]
AgentName = Literal["sell", "subsidy", "claim", "watch"]
TinyFishKind = Literal["search", "fetch", "agent", "monitor"]
EvidenceKind = Literal["search", "fetch", "agent", "monitor", "replay", "knowledge"]
RunStatus = Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]
AlertType = Literal["hail", "heavy_rain", "scheme", "price"]


def now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# --- building blocks ----------------------------------------------------------------------------------------


class Evidence(BaseModel):
    """Where a fact came from. Every answer must carry at least one, or the gate withholds it."""

    source_url: str
    kind: EvidenceKind
    title: str | None = None
    quote: str | None = None
    fetched_at: datetime = Field(default_factory=now)
    run_id: str | None = None
    # True when the value is an assumption rather than read from the source (shown as such in the UI).
    assumed: bool = False


class AgentResult(BaseModel):
    """What an agent hands the safety gate. Never shown to the farmer directly."""

    agent: AgentName
    answer_en: str
    answer_hi: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    run_id: str | None = None


class Triage(BaseModel):
    text: str
    language: Language
    intent: Intent
    crop: str | None = None
    quantity_qtl: float | None = None
    asks_dose: bool = False


class GatedResponse(BaseModel):
    """What the farmer sees. `answered` carries the agent's answer; `escalated` carries only a hand-off."""

    status: Literal["answered", "escalated", "menu"]
    language: Language
    intent: Intent
    reply: str
    agent: AgentName | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = 0.0
    run_id: str | None = None  # the TinyFish run behind the answer; GET /api/runs/{id} has its streaming_url
    ticket_id: str | None = None
    # Machine-readable reason codes (missing_evidence, low_confidence, dose_question, dose_in_answer).
    reasons: list[str] = Field(default_factory=list)


# --- stored tables ------------------------------------------------------------------------------------------


class Farmer(BaseModel):
    id: str
    name: str
    phone: str | None = None
    state: str
    district: str
    crops: list[str] = Field(default_factory=list)
    land_acres: float
    category: Literal["small", "marginal", "other"] = "small"
    language: Language = "hi"
    # Documents the farmer says they hold: aadhaar, bank_passbook, land_record, farmer_id, mobile_linked_aadhaar.
    documents: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now)


class RunRecord(BaseModel):
    """One TinyFish call. `streaming_url` is stored the moment the STREAMING_URL event arrives."""

    id: str
    kind: TinyFishKind
    status: RunStatus = "PENDING"
    target: str  # goal for an agent run, query for search, url for fetch, fixture name for a monitor
    streaming_url: str | None = None
    video_url: str | None = None  # a recording, when TinyFish captured one; the live viewer's fallback
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    steps: int | None = None
    cost_credits: float | None = None
    mode: Literal["live", "replay"] = "replay"
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class Alert(BaseModel):
    id: str = Field(default_factory=lambda: new_id("alert"))
    farmer_id: str | None = None
    type: AlertType
    title: str
    detail: str
    source_url: str
    evidence: list[Evidence] = Field(default_factory=list)
    claim_id: str | None = None
    created_at: datetime = Field(default_factory=now)


class LedgerEntry(BaseModel):
    """Rs Unlocked. Projected until the farmer confirms; only confirmed entries count towards the total."""

    id: str = Field(default_factory=lambda: new_id("led"))
    farmer_id: str
    kind: Literal["sell", "subsidy", "claim"]
    amount_rs: float
    formula: str
    confirmed: bool = False
    created_at: datetime = Field(default_factory=now)


class Ticket(BaseModel):
    """A question the gate refused to answer, queued for a human (KVK expert)."""

    id: str = Field(default_factory=lambda: new_id("tkt"))
    farmer_id: str | None = None
    intent: Intent
    query: str
    reason: str
    status: Literal["open", "closed"] = "open"
    created_at: datetime = Field(default_factory=now)


class ChannelMessage(BaseModel):
    """Idempotency record for a Twilio inbound message; stores only its reply and processing metadata."""

    id: str  # Twilio MessageSid
    sender: str
    status: Literal["processing", "completed", "failed"] = "processing"
    reply: str | None = None
    updated_at: datetime = Field(default_factory=now)


# --- request bodies -----------------------------------------------------------------------------------------


class ChatRequest(BaseModel):
    text: str
    farmer_id: str | None = None


class SellRequest(BaseModel):
    crop: str = "wheat"
    quantity_qtl: float = Field(gt=0)
    farmer_id: str | None = None


class SchemeReviewRequest(BaseModel):
    """A human acknowledgement before an unreviewed scheme can be shown to farmers."""

    reviewer: str = Field(min_length=2, max_length=100)
    sources_read: bool = False


class ClaimRequest(BaseModel):
    farmer_id: str
    crop: str
    event: Literal["hail", "heavy_rain", "flood", "other"] = "hail"
    event_date: str  # ISO date
    photo_names: list[str] = Field(default_factory=list)


class ReplayMonitorRequest(BaseModel):
    fixture_name: str


# --- response bodies ----------------------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    tinyfish_mode: Literal["live", "replay"]
    db_backend: Literal["sqlite", "supabase"]
    demo_state: str
    demo_district: str
    tinyfish_configured: bool = False
    whatsapp_configured: bool = False
    speech_to_text_configured: bool = False
    public_webhook_ready: bool = False
    watch_mode_ready: bool = False


class SchemeMatch(BaseModel):
    scheme_id: str
    name: str
    benefit: str
    estimated_value_rs: float | None = None
    eligible: bool
    missing_docs: list[str] = Field(default_factory=list)
    needs_info: list[str] = Field(default_factory=list)  # facts we do not have, so eligibility is unknown
    reasons: list[str] = Field(default_factory=list)
    deadline: str | None = None  # ISO date, only ever from a cited source
    apply_url: str
    reviewed: bool  # unreviewed schemes are never shown to farmers
    packet_url: str | None = None  # /files/<name>.pdf, the prefilled draft
    evidence: list[Evidence] = Field(default_factory=list)


class SchemesResponse(BaseModel):
    farmer_id: str
    schemes: list[SchemeMatch]
    confidence: float
    requires_farmer_confirmation: bool = True
    note: str | None = None  # why the list is empty, when it is (for example: nothing has been reviewed yet)


class ClaimResponse(BaseModel):
    claim_id: str
    status: Literal["draft"] = "draft"  # a claim is never submitted by KhetKaaj
    dossier_url: str  # /files/<name>.pdf
    alert_id: str | None = None
    intimation_deadline: str | None = None
    warnings: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float


class LedgerResponse(BaseModel):
    farmer_id: str | None = None
    total_rs: float  # confirmed entries only
    projected_rs: float  # not yet confirmed
    entries: list[LedgerEntry]
