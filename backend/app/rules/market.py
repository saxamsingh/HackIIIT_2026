"""Selling rules: pure functions, no network, no clock except what is passed in. CLAUDE.md section 7.

Price rows come from a parsed page. Everything here decides what to do with them: match them to mandis with a
known distance, net out transport, drop rows that look like unit errors, flag stale ones, rank, compare with
MSP, and say how much to trust the result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from ..knowledge import Mandi


@dataclass(frozen=True)
class PriceRow:
    mandi: str
    modal_price: float  # Rs per quintal
    arrival_date: date | None = None
    quote: str = ""  # the source line, kept as evidence


@dataclass(frozen=True)
class Option:
    mandi: str
    modal_price: float
    distance_km: float
    transport_cost: float
    net_price: float
    distance_assumed: bool
    arrival_date: date | None
    quote: str


def transport_cost(distance_km: float, rate_rs_per_qtl_per_km: float) -> float:
    return round(distance_km * rate_rs_per_qtl_per_km, 2)


def net_price(modal_price: float, distance_km: float, rate_rs_per_qtl_per_km: float) -> float:
    return round(modal_price - transport_cost(distance_km, rate_rs_per_qtl_per_km), 2)


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", name.lower()).strip()


def match_mandi(name: str, mandis: list[Mandi]) -> Mandi | None:
    """A row's market name to a mandi we know the distance to: exact alias first, then alias as a whole word."""
    row = _norm(name)
    for m in mandis:
        if row in {_norm(a) for a in m.aliases}:
            return m
    for m in mandis:
        if any(re.search(rf"\b{re.escape(_norm(a))}\b", row) for a in m.aliases):
            return m
    return None


def build_options(
    rows: list[PriceRow], mandis: list[Mandi], rate: float
) -> tuple[list[Option], list[str]]:
    """Options for rows whose mandi has a known distance; the names of rows that did not match."""
    best_per_mandi: dict[str, Option] = {}
    unmatched: list[str] = []
    for row in rows:
        mandi = match_mandi(row.mandi, mandis)
        if mandi is None:
            unmatched.append(row.mandi)
            continue
        option = Option(
            mandi=mandi.name,
            modal_price=row.modal_price,
            distance_km=mandi.distance_km,
            transport_cost=transport_cost(mandi.distance_km, rate),
            net_price=net_price(row.modal_price, mandi.distance_km, rate),
            distance_assumed=mandi.assumed,
            arrival_date=row.arrival_date,
            quote=row.quote,
        )
        held = best_per_mandi.get(mandi.name)
        newer = held is None or (option.arrival_date or date.min) > (held.arrival_date or date.min)
        if newer:  # two rows for one mandi: keep the most recent
            best_per_mandi[mandi.name] = option
    return list(best_per_mandi.values()), unmatched


def rank(options: list[Option]) -> list[Option]:
    """Best net price first; on a tie the nearer mandi wins."""
    return sorted(options, key=lambda o: (-o.net_price, o.distance_km, o.mandi))


def msp_comparison(price: float, msp_rs_per_qtl: float) -> dict[str, float | bool]:
    diff = round(price - msp_rs_per_qtl, 2)
    return {
        "msp_rs_per_qtl": msp_rs_per_qtl,
        "difference_rs": diff,
        "difference_pct": round(100 * diff / msp_rs_per_qtl, 1),
        "below_msp": diff < 0,
    }


def split_insane(
    options: list[Option], msp_rs_per_qtl: float | None, min_ratio: float, max_ratio: float
) -> tuple[list[Option], list[Option]]:
    """Without an MSP there is nothing to check against, so nothing is dropped. With one, a modal price
    far outside the band is far more likely a unit or parsing error than a real price."""
    if msp_rs_per_qtl is None:
        return options, []
    kept = [o for o in options if min_ratio * msp_rs_per_qtl <= o.modal_price <= max_ratio * msp_rs_per_qtl]
    return kept, [o for o in options if o not in kept]


def stale_options(options: list[Option], today: date, max_age_days: int) -> list[Option]:
    return [o for o in options if o.arrival_date is not None and (today - o.arrival_date).days > max_age_days]


def confidence(
    *,
    n_options: int,
    n_dropped: int,
    n_stale: int,
    n_unknown_date: int,
    rate_assumed: bool,
    rung: str,
    has_msp: bool,
    min_mandis: int,
) -> float:
    """0 to 1. Starts high and loses points for each reason to doubt the result. The gate withholds anything
    below its threshold (0.85), so a stale price, a dropped outlier or too few mandis sends the question to a
    human, while the always-present caveats (assumed freight rate, agent rung) do not on their own."""
    score = 0.95
    if n_options == 0:
        return 0.0
    if n_stale:
        score -= 0.25
    score -= min(0.30, 0.10 * n_dropped)
    if n_options < min_mandis:
        score -= 0.10
    if n_unknown_date:
        score -= 0.05
    if rate_assumed:
        score -= 0.04
    if rung == "agent":
        score -= 0.03
    if not has_msp:
        score -= 0.05
    return round(max(0.0, min(1.0, score)), 2)


def ledger_value(best: Option, nearest: Option, quantity_qtl: float) -> float:
    return round(max(0.0, (best.net_price - nearest.net_price) * quantity_qtl), 2)


def formula(best: Option, nearest: Option, quantity_qtl: float, rate: float, rate_assumed: bool) -> str:
    value = ledger_value(best, nearest, quantity_qtl)
    caveat = " (freight rate is an assumption)" if rate_assumed else ""
    return (
        f"(net Rs {best.net_price:g} at {best.mandi} - net Rs {nearest.net_price:g} at {nearest.mandi}) "
        f"x {quantity_qtl:g} qtl = Rs {value:g}; net = modal price - Rs {rate:g} per qtl per km x distance{caveat}"
    )
