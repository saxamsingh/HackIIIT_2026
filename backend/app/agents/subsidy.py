"""Subsidy agent: which reviewed schemes the farmer qualifies for, with a prefilled draft packet for each.

Eligibility is the deterministic matcher in rules/eligibility.py over the YAML records; a scheme nobody has
reviewed is never considered. CLAUDE.md sections 2.6 and 7."""

from __future__ import annotations

import logging

from .. import replies
from ..models import AgentResult, Evidence, Farmer
from ..reports import render_packet
from ..rules.eligibility import evaluate
from ..schemes import Scheme, load_schemes
from .base import AgentContext

log = logging.getLogger("khetkaaj.subsidy")


def _evidence(scheme: Scheme) -> list[Evidence]:
    return [
        Evidence(source_url=s.url, kind="knowledge", title=s.title or scheme.name, quote=scheme.benefit)
        for s in scheme.sources
    ] or [Evidence(source_url=scheme.apply_url, kind="knowledge", title=scheme.name, quote=scheme.benefit)]


async def run(ctx: AgentContext) -> AgentResult:
    farmer: Farmer | None = ctx.farmer
    if farmer is None:
        en, hi = replies.no_data("scheme match without a farmer profile", "किसान की जानकारी के बिना योजना")
        return AgentResult(agent="subsidy", answer_en=en, answer_hi=hi, confidence=0.0)

    schemes = load_schemes(ctx.settings, reviewed_only=True)
    if not schemes:
        en, hi = replies.subsidy([], 0, 0, none_reviewed=True)
        return AgentResult(agent="subsidy", answer_en=en, answer_hi=hi, confidence=0.0)

    matches: list[dict] = []
    evidence: list[Evidence] = []
    eligible_names: list[str] = []
    needs_docs = needs_info = 0
    best_value: tuple[float, Scheme] | None = None

    for scheme in schemes:
        result = evaluate(farmer, scheme)
        packet_url = None
        if result.eligible:
            packet_url = f"/files/{render_packet(farmer, scheme, result, ctx.settings, ctx.web.mode)}"
            eligible_names.append(scheme.name)
            needs_docs += 1 if result.missing_docs else 0
            if scheme.estimated_value_rs and (best_value is None or scheme.estimated_value_rs > best_value[0]):
                best_value = (scheme.estimated_value_rs, scheme)
        elif result.status == "needs_info":
            needs_info += 1
        ev = _evidence(scheme)
        evidence.extend(ev if result.status != "ineligible" else [])
        matches.append(
            {
                "scheme_id": scheme.id,
                "name": scheme.name,
                "benefit": scheme.benefit,
                "estimated_value_rs": scheme.estimated_value_rs,
                "eligible": result.eligible,
                "missing_docs": result.missing_docs if result.status != "ineligible" else [],
                "needs_info": result.needs_info,
                "reasons": result.reasons,
                "deadline": scheme.deadline,
                "apply_url": scheme.apply_url,
                "reviewed": scheme.reviewed,
                "packet_url": packet_url,
                "evidence": [e.model_dump(mode="json") for e in ev],
            }
        )

    matches.sort(key=lambda m: (not m["eligible"], bool(m["missing_docs"]), m["name"]))
    en, hi = replies.subsidy(eligible_names, needs_docs, needs_info, none_reviewed=False)
    data: dict = {"schemes": matches, "reviewed_schemes_considered": len(schemes)}
    if best_value:
        value, scheme = best_value
        data["ledger_value_rs"] = value
        data["formula"] = f"Indicative benefit of {scheme.name}: Rs {value:g}. {scheme.value_basis}"
    return AgentResult(
        agent="subsidy",
        answer_en=await replies.polish(en, ctx.settings),
        answer_hi=await replies.polish(hi, ctx.settings),
        data=data,
        evidence=evidence,
        confidence=0.9,
    )
