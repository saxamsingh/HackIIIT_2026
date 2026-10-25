"""Claim agent: builds a crop-damage claim dossier (a PDF) from weather evidence, photo metadata and the cited
72-hour reporting rule. It prepares a draft; it never submits a claim anywhere. CLAUDE.md sections 2.1, 7."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .. import knowledge, replies
from ..config import Settings
from ..db import Repository
from ..exif import PhotoMeta, photo_warnings
from ..ladder import fetch_then_agent
from ..models import AgentResult, Alert, AlertType, Evidence, Farmer, new_id
from ..reports import dossier_name, render_dossier
from ..rules import weather
from ..tinyfish import WebClient, WebClientError
from .base import AgentContext

log = logging.getLogger("khetkaaj.claim")

# which warning types support which claimed event
EVENT_WARNINGS: dict[str, set[str]] = {
    "hail": {"hail"},
    "heavy_rain": {"heavy_rain"},
    "flood": {"heavy_rain"},
    "other": set(),
}
EVENT_LABEL = {
    "hail": "Hailstorm",
    "heavy_rain": "Heavy rain",
    "flood": "Flood or waterlogging",
    "other": "Other crop damage",
}
WARNING_SCHEMA = {
    "type": "object",
    "properties": {"warning": {"type": "string"}},
    "required": ["warning"],
}


@dataclass
class ClaimInputs:
    farmer: Farmer
    crop: str
    event: str
    event_date: date
    photos: list[PhotoMeta] = field(default_factory=list)
    alert: Alert | None = None


@dataclass
class PreparedClaim:
    claim_id: str
    dossier_url: str
    result: AgentResult


def _location_text(p: PhotoMeta) -> str | None:
    if p.lat is not None and p.lon is not None:
        return f"{p.lat:.5f}, {p.lon:.5f}"
    if p.device_lat is not None and p.device_lon is not None:
        return f"not in the photo; phone at upload: {p.device_lat:.5f}, {p.device_lon:.5f}"
    return None


def _parse_warning(text: str, district: str) -> str | None:
    """A page is usable only if it names the district and a warning we recognise."""
    return text if weather.mentions_district(text, district) and weather.classify(text) else None


async def _weather_evidence(
    inputs: ClaimInputs, web: WebClient, settings: Settings
) -> tuple[str | None, Evidence | None]:
    """The warning text and its evidence: the alert that triggered the claim, or a fresh look at the IMD page."""
    if inputs.alert is not None:
        ev = inputs.alert.evidence[0] if inputs.alert.evidence else Evidence(
            source_url=inputs.alert.source_url, kind="monitor", quote=inputs.alert.detail
        )
        return inputs.alert.detail, ev
    district = inputs.farmer.district
    goal = (
        f"Find the latest weather warning for district '{district}' and return its full text as JSON "
        "with the key 'warning'."
    )
    try:
        found = await fetch_then_agent(
            web,
            url=knowledge.imd_url(settings),
            parse_page=lambda page: _parse_warning(page.text or "", district),
            goal=goal,
            output_schema=WARNING_SCHEMA,
            parse_agent=lambda r: _parse_warning(str(r.get("warning", "")), district),
            purpose=f"Weather warnings for {district}",
            fresh=True,
        )
    except WebClientError as e:
        log.warning("weather lookup failed: %s", e)
        return None, None
    if found is None:
        return None, None
    types = weather.classify(found.data)
    quote = weather.sentence_with(found.data, types[0]) if types else found.data[:300]
    return found.data, found.evidence(title="Weather warning", quote=quote)


async def prepare(inputs: ClaimInputs, *, repo: Repository, web: WebClient, settings: Settings) -> PreparedClaim:
    farmer = inputs.farmer
    text, weather_ev = await _weather_evidence(inputs, web, settings)

    wanted = EVENT_WARNINGS.get(inputs.event, set())
    present = set(weather.classify(text)) if text else set()
    corroborated = bool(text) and bool(wanted & present) and weather.mentions_district(text, farmer.district)
    matched_type: AlertType | None = next((t for t in ("hail", "heavy_rain") if t in wanted and t in present), None)
    quote = weather.sentence_with(text, matched_type) if (text and matched_type) else (text or "")[:300]

    rule = knowledge.intimation(settings)
    deadline = inputs.event_date + timedelta(hours=rule.hours)
    photo_issues = photo_warnings(inputs.photos, inputs.event_date)
    warnings = list(photo_issues)
    if not inputs.photos:
        warnings.append("No photos attached: add dated photos of the damaged field")
    if date.today() > deadline:
        warnings.append(
            f"The {rule.hours}-hour reporting window ended on {deadline.isoformat()}: report to your insurer "
            "straight away and explain the delay"
        )
    if not corroborated:
        warnings.append("The weather record does not clearly support this event")

    claim_id = new_id("claim")
    photo_rows = [
        {
            "name": p.name,
            "taken": p.taken_at.strftime("%Y-%m-%d %H:%M UTC") if p.taken_at else None,
            "location": _location_text(p),
        }
        for p in inputs.photos
    ]
    name = render_dossier(
        settings,
        web.mode,
        claim_id=claim_id,
        farmer=farmer,
        crop=inputs.crop,
        event_label=EVENT_LABEL.get(inputs.event, inputs.event),
        event_date=inputs.event_date.isoformat(),
        weather_quote=quote if text else "",
        weather_url=weather_ev.source_url if weather_ev else "",
        weather_kind=weather_ev.kind if weather_ev else "",
        corroboration=(
            "The record supports the claimed event."
            if corroborated
            else "The record does not clearly support the claimed event."
        ),
        intimation_deadline=deadline.isoformat(),
        intimation_source=rule.source_url,
        photos=photo_rows,
        warnings=warnings,
    )

    evidence = [weather_ev] if weather_ev else []
    if evidence:  # without a weather source there is nothing to stand behind, so the gate will withhold it
        evidence.append(
            Evidence(source_url=rule.source_url, kind="knowledge", title=rule.source_title,
                     quote=f"Report the loss within {rule.hours} hours")
        )
    # Corroborated by an official warning: confident, a little less if the photos have problems.
    # Not corroborated: below the gate's threshold, so a person looks at it.
    confidence = (0.88 if photo_issues else 0.92) if corroborated else 0.6

    en, hi = replies.claim(inputs.event, claim_id, deadline.isoformat(), corroborated, len(warnings))
    result = AgentResult(
        agent="claim",
        answer_en=await replies.polish(en, settings),
        answer_hi=await replies.polish(hi, settings),
        data={
            "claim_id": claim_id,
            "dossier_url": f"/files/{name}",
            "intimation_deadline": deadline.isoformat(),
            "warnings": warnings,
            "corroborated": corroborated,
            "event": inputs.event,
            "photos": photo_rows,
        },
        evidence=evidence,
        confidence=confidence,
        run_id=None,
    )
    return PreparedClaim(claim_id, f"/files/{dossier_name(claim_id)}", result)


async def run(ctx: AgentContext) -> AgentResult:
    req: dict[str, Any] = ctx.extra.get("claim") or {}
    farmer = ctx.farmer
    if farmer is None or not req:
        en, hi = replies.no_data("claim without a farmer and an event", "किसान और घटना के बिना क्लेम")
        return AgentResult(agent="claim", answer_en=en, answer_hi=hi, confidence=0.0)
    inputs = ClaimInputs(
        farmer=farmer,
        crop=req.get("crop") or (farmer.crops[0] if farmer.crops else "crop"),
        event=req.get("event", "hail"),
        event_date=date.fromisoformat(req["event_date"]),
        photos=req.get("photos", []),
    )
    return (await prepare(inputs, repo=ctx.repo, web=ctx.web, settings=ctx.settings)).result


async def prepare_from_alert(
    alert: Alert, farmer: Farmer, *, repo: Repository, web: WebClient, settings: Settings
) -> PreparedClaim:
    """Watch Mode's hook: a hail or heavy-rain alert starts a claim draft for the affected farmer."""
    event = "hail" if alert.type == "hail" else "heavy_rain"
    inputs = ClaimInputs(
        farmer=farmer,
        crop=farmer.crops[0] if farmer.crops else "crop",
        event=event,
        event_date=alert.created_at.date(),
        alert=alert,
    )
    return await prepare(inputs, repo=repo, web=web, settings=settings)
