"""Watch agent: turns a Monitor run into alerts, notifications and (for hail or heavy rain) a prepared claim.

A Monitor is TinyFish re-checking an official page on a schedule; it calls our webhook when something is
there. Only the Alert, the WhatsApp message and the claim *draft* are produced: nothing is ever submitted.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import timedelta
from typing import Any

from .. import replies
from ..channels.notify import Notifier
from ..config import Settings
from ..db import Repository
from ..models import AgentResult, Alert, AlertType, Evidence, Farmer, now
from ..rules import weather
from ..tinyfish import WebClient
from . import claim
from .base import AgentContext

log = logging.getLogger("khetkaaj.watch")
DEDUPE_WINDOW = timedelta(hours=24)


async def run(ctx: AgentContext) -> AgentResult:
    raise NotImplementedError("Watch is driven by webhooks (handle_monitor_payload), not by chat")


def _page_text(run_obj: dict[str, Any]) -> tuple[str, str]:
    """Extract text and provenance from a monitor result, whether Markdown or structured Search output."""
    texts, url = [], ""
    for result in run_obj.get("results", []):
        raw = result.get("text")
        if raw:
            texts.append(raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False))
        else:
            # Search monitors frequently return title/snippet/url fields rather than a `text` field.
            fields = [result.get(key) for key in ("title", "snippet", "description", "content")]
            flat = " — ".join(str(value).strip() for value in fields if isinstance(value, str) and value.strip())
            if flat:
                texts.append(flat)
        url = url or result.get("final_url") or result.get("url") or result.get("link") or ""
    return "\n".join(texts), url


def _is_scheme_monitor(payload: dict[str, Any]) -> bool:
    monitor = payload.get("monitor") if isinstance(payload.get("monitor"), dict) else {}
    config = monitor.get("config") if isinstance(monitor.get("config"), dict) else {}
    descriptor = " ".join(str(monitor.get(key) or "") for key in ("name", "purpose", "description"))
    descriptor += " " + " ".join(str(config.get(key) or "") for key in ("query", "purpose", "url"))
    low = descriptor.lower()
    return any(word in low for word in ("scheme", "subsidy", "yojana", "anudan", "circular"))


def _scheme_notice_title(text: str) -> str:
    """Make a short operator-readable title from a monitor result; do not infer benefit or eligibility."""
    lines = [re.sub(r"\s+", " ", line).strip(" -•\t") for line in text.splitlines()]
    useful = next((line for line in lines if line and not line.startswith("{")), "New agriculture scheme notice")
    return useful[:120]


def _already_alerted(repo: Repository, farmer_id: str, alert_type: AlertType, source_url: str, detail: str) -> bool:
    cutoff = now() - DEDUPE_WINDOW
    return any(
        a.type == alert_type and a.source_url == source_url and a.detail == detail and a.created_at >= cutoff
        for a in repo.list_alerts(farmer_id)
        if a.farmer_id == farmer_id
    )


async def _notify(notifier: Notifier | None, farmer: Farmer, alert_type: AlertType) -> None:
    if notifier is None or not farmer.phone:
        return
    en, hi = replies.alert(alert_type, farmer.district)
    text = en if farmer.language == "en" else hi
    try:
        await notifier.send(farmer.phone, text)
    except Exception:  # a failed push must never lose the alert
        log.warning("notification failed for a farmer", exc_info=True)


async def handle_monitor_payload(
    payload: dict[str, Any],
    *,
    repo: Repository,
    web: WebClient,
    settings: Settings,
    notifier: Notifier | None = None,
) -> list[Alert]:
    """Create one alert per affected farmer. A baseline run (the first look at a page) is not news."""
    run_obj = payload.get("run", {})
    if run_obj.get("is_baseline"):
        return []
    text, url = _page_text(run_obj)
    if not text:
        return []
    monitor = payload.get("monitor") if isinstance(payload.get("monitor"), dict) else {}
    monitor_config = monitor.get("config") if isinstance(monitor.get("config"), dict) else {}
    monitor_url = monitor_config.get("url") or url
    is_scheme_monitor = _is_scheme_monitor(payload)
    types = weather.classify(text)
    # Scheme-monitor Search results often don't name a district. They are routed by the configured state
    # query and are always marked as unreviewed notices, never as confirmed eligibility or a payment.
    if is_scheme_monitor and text.strip():
        types = list(dict.fromkeys([*types, "scheme"]))
    if not types:
        return []

    created: list[Alert] = []
    for farmer in repo.list_farmers():
        if "scheme" in types and farmer.state.lower() != settings.demo_state.lower():
            continue  # state-scoped scheme notices only go to farmers in the configured state
        if not is_scheme_monitor and not weather.mentions_district(text, farmer.district):
            continue  # weather warnings must name this farmer's district
        for alert_type in types:
            if alert_type == "scheme":
                # The monitor runs only on changes (baseline is excluded above). Keep a source-linked notice
                # for human review; never add an automatically discovered record to the farmer catalog.
                source = monitor_url or url
                if not source or not source.startswith(("https://", "http://")):
                    continue
                title = _scheme_notice_title(text)
                detail = (title + " — possible new scheme/circular notice. not yet reviewed; verify the official "
                          "source and eligibility before advising a farmer.")[:500]
                if _already_alerted(repo, farmer.id, alert_type, source, detail):
                    continue
                label = "New scheme notice to review"
                alert = Alert(
                    farmer_id=farmer.id,
                    type="scheme",
                    title=label,
                    detail=detail,
                    source_url=source,
                    evidence=[Evidence(
                        source_url=source,
                        kind="replay" if web.mode == "replay" else "monitor",
                        title="Scheme monitor change (human review required)",
                        quote=title,
                        run_id=run_obj.get("id"),
                    )],
                )
                repo.add_alert(alert)
                await _notify(notifier, farmer, "scheme")
                created.append(alert)
                continue
            if not weather.mentions_district(text, farmer.district):
                continue
            quote = weather.sentence_with(text, alert_type)
            if _already_alerted(repo, farmer.id, alert_type, monitor_url, quote):
                continue
            label_en = replies.ALERT_LABELS[alert_type][0].capitalize()
            alert = Alert(
                farmer_id=farmer.id,
                type=alert_type,
                title=f"{label_en} warning for {farmer.district}",
                detail=quote,
                source_url=monitor_url,
                evidence=[
                    Evidence(
                        source_url=monitor_url,
                        kind="replay" if web.mode == "replay" else "monitor",
                        title="Monitor run",
                        quote=quote,
                        run_id=run_obj.get("id"),
                    )
                ],
            )
            if alert_type in ("hail", "heavy_rain"):
                try:
                    prepared = await claim.prepare_from_alert(alert, farmer, repo=repo, web=web, settings=settings)
                    alert = alert.model_copy(update={"claim_id": prepared.claim_id})
                except Exception:
                    log.exception("could not prepare a claim for alert %s", alert.id)
            repo.add_alert(alert)
            await _notify(notifier, farmer, alert_type)
            created.append(alert)
    return created
