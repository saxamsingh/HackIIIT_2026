"""Sell agent: which mandi pays the best price after transport, with an MSP cross-check and a source for every
price line. CLAUDE.md section 7. Prices come from the ladder (Fetch, then an Agent run); the maths is in
rules/market.py; nothing about a price is hardcoded here."""

from __future__ import annotations

import logging
from datetime import date

from .. import knowledge, replies
from ..ladder import fetch_then_agent
from ..models import AgentResult, Evidence
from ..parsers import COMMODITY_WORDS, parse_agent_prices, parse_price_table
from ..rules import market
from ..tinyfish import WebClientError
from .base import AgentContext

log = logging.getLogger("khetkaaj.sell")

DEFAULT_QUANTITY_QTL = 10.0
PRICE_SCHEMA = {
    "type": "object",
    "properties": {
        "mandis": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "mandi": {"type": "string"},
                    "modal_price": {"type": "number"},
                    "arrival_date": {"type": "string"},
                },
                "required": ["mandi", "modal_price"],
            },
        }
    },
    "required": ["mandis"],
}


def _no_data() -> AgentResult:
    en, hi = replies.no_data("mandi price", "मंडी भाव")
    return AgentResult(agent="sell", answer_en=en, answer_hi=hi, confidence=0.0)


def _option_dict(o: market.Option) -> dict:
    return {
        "mandi": o.mandi,
        "modal_price": o.modal_price,
        "distance_km": o.distance_km,
        "transport_cost": o.transport_cost,
        "net_price": o.net_price,
        "distance_assumed": o.distance_assumed,
        "arrival_date": o.arrival_date.isoformat() if o.arrival_date else None,
    }


async def run(ctx: AgentContext) -> AgentResult:
    settings, farmer = ctx.settings, ctx.farmer
    cfg = knowledge.market_config(settings)
    crop = ctx.triage.crop or ctx.extra.get("crop") or (farmer.crops[0] if farmer and farmer.crops else "wheat")
    quantity = ctx.triage.quantity_qtl or ctx.extra.get("quantity_qtl")
    quantity_assumed = quantity is None
    quantity = float(quantity or DEFAULT_QUANTITY_QTL)
    district = farmer.district if farmer else settings.demo_district
    state = farmer.state if farmer else settings.demo_state

    mandis = cfg.mandis_for(district)
    if not mandis:
        log.warning("no mandi list for district %s", district)
        return _no_data()
    msp = knowledge.msp_for(settings, crop)

    commodity = COMMODITY_WORDS.get(crop, (crop,))[0].title()
    goal = (
        f"Open the mandi price report. Select state '{state}', district '{district}', commodity '{commodity}' "
        "and the most recent date. For every market listed return its name, the modal price in Rs per quintal "
        "and the arrival date, as JSON."
    )
    try:
        found = await fetch_then_agent(
            ctx.web,
            url=cfg.price_url,
            parse_page=lambda page: parse_price_table(page.text or "", crop),
            goal=goal,
            output_schema=PRICE_SCHEMA,
            parse_agent=parse_agent_prices,
            purpose=f"Mandi prices for {crop} in {district}",
            fresh=True,
        )
    except WebClientError as e:
        log.warning("price lookup failed: %s", e)
        return _no_data()
    if found is None:
        return _no_data()

    options, unmatched = market.build_options(found.data, mandis, cfg.rate_rs_per_qtl_per_km)
    kept, dropped = market.split_insane(
        options, msp.price_rs_per_qtl if msp else None, cfg.min_ratio_to_msp, cfg.max_ratio_to_msp
    )
    if not kept:
        return _no_data()

    ranked = market.rank(kept)
    best = ranked[0]
    nearest = min(kept, key=lambda o: (o.distance_km, o.mandi))
    dates = [o.arrival_date for o in kept if o.arrival_date]
    # A replay is a recording, so freshness is judged against the recording itself; live uses today's date.
    today = max(dates) if ctx.web.mode == "replay" and dates else date.today()
    stale = market.stale_options(kept, today, cfg.max_age_days)
    unknown_date = sum(1 for o in kept if o.arrival_date is None)

    confidence = market.confidence(
        n_options=len(kept),
        n_dropped=len(dropped),
        n_stale=len(stale),
        n_unknown_date=unknown_date,
        rate_assumed=cfg.rate_assumed,
        rung=found.rung,
        has_msp=msp is not None,
        min_mandis=cfg.min_mandis,
    )
    gain = market.ledger_value(best, nearest, quantity)

    warnings: list[str] = []
    if dropped:
        warnings.append("Ignored price(s) that look like unit errors: " + ", ".join(o.mandi for o in dropped))
    if stale:
        warnings.append(f"Price older than {cfg.max_age_days} days: " + ", ".join(o.mandi for o in stale))
    if unknown_date:
        warnings.append(f"{unknown_date} price(s) show no date")
    if len(kept) < cfg.min_mandis:
        warnings.append(f"Only {len(kept)} mandi(s) compared")
    if unmatched:
        warnings.append(f"{len(unmatched)} market(s) on the page are not in this district's mandi list")
    assumptions: list[str] = []
    if cfg.rate_assumed:
        assumptions.append("Freight rate per quintal per km is an assumption, not sourced")
    if any(o.distance_assumed for o in kept):
        assumptions.append("Road distances are approximate, not sourced")
    if quantity_assumed:
        assumptions.append(f"Quantity not given: assumed {DEFAULT_QUANTITY_QTL:g} quintal")

    msp_data: dict = {"price_rs_per_qtl": None, "note": f"No researched MSP for {crop}"}
    evidence = [
        found.evidence(title=f"{o.mandi} modal price", quote=o.quote) for o in ranked
    ]
    if msp:
        msp_data = {
            "price_rs_per_qtl": msp.price_rs_per_qtl,
            "marketing_season": msp.marketing_season,
            "source_url": msp.source_url,
            "quality": msp.quality,
            **market.msp_comparison(best.modal_price, msp.price_rs_per_qtl),
        }
        evidence.append(
            Evidence(source_url=msp.source_url, kind="knowledge", title=msp.source_title, quote=msp.note or None)
        )

    en, hi = replies.sell(crop, quantity, _option_dict(best), _option_dict(nearest), gain, msp_data)
    return AgentResult(
        agent="sell",
        answer_en=await replies.polish(en, settings),
        answer_hi=await replies.polish(hi, settings),
        data={
            "crop": crop,
            "district": district,
            "state": state,
            "quantity_qtl": quantity,
            "options": [_option_dict(o) for o in ranked],
            "best": _option_dict(best),
            "nearest": _option_dict(nearest),
            "gain_rs": gain,
            "ledger_value_rs": gain,
            "formula": market.formula(best, nearest, quantity, cfg.rate_rs_per_qtl_per_km, cfg.rate_assumed),
            "msp": msp_data,
            "warnings": warnings,
            "assumptions": assumptions,
            "rung": found.rung,
            "price_source": found.url,
            "data_mode": ctx.web.mode,
        },
        evidence=evidence,
        confidence=confidence,
        run_id=found.run_id,
    )
