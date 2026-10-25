"""Deterministic parsers for fetched pages and Agent results. Page text is parsed here and never goes into
a prompt (CLAUDE.md section 2.3)."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from .rules.market import PriceRow

COMMODITY_WORDS: dict[str, tuple[str, ...]] = {
    "wheat": ("wheat", "gehun", "गेहूं"),
    "rice": ("paddy", "rice", "dhan", "धान"),
    "mustard": ("mustard", "rapeseed", "sarson", "सरसों"),
    "maize": ("maize", "makka", "मक्का"),
    "chickpea": ("gram", "chickpea", "chana", "चना"),
    "sugarcane": ("sugarcane", "gur", "गन्ना"),
    "potato": ("potato", "aloo", "आलू"),
    "bajra": ("bajra", "bajri", "बाजरा"),
    "soybean": ("soybean", "soyabean", "सोयाबीन"),
    "cotton": ("cotton", "kapas", "कपास"),
}
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def parse_date(text: str) -> date | None:
    """ISO, dd/mm/yyyy, dd-mm-yyyy and '24 Oct 2026'. Anything else is None, never a guess."""
    t = text.strip()
    if m := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t):
        y, mo, d = map(int, m.groups())
    elif m := re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", t):
        d, mo, y = map(int, m.groups())
    elif m := re.fullmatch(r"(\d{1,2})[ -]([A-Za-z]{3})[a-z]*[ -,]*(\d{4})", t):
        d, y = int(m.group(1)), int(m.group(3))
        mo = _MONTHS.get(m.group(2).lower(), 0)
    else:
        return None
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_price(text: str) -> float | None:
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if value > 0 else None


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_price_table(text: str, crop: str) -> list[PriceRow] | None:
    """Rows from a markdown table with a market column and a modal-price column (and optionally a commodity
    and a date column). None when the page has no such table, so the ladder can escalate."""
    words = COMMODITY_WORDS.get(crop, (crop,))
    rows: list[PriceRow] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        header = _cells(lines[i]) if lines[i].lstrip().startswith("|") else None
        if header is None:
            i += 1
            continue
        low = [h.lower() for h in header]
        market = next((n for n, h in enumerate(low) if "market" in h or "mandi" in h), None)
        modal = next((n for n, h in enumerate(low) if "modal" in h), None)
        if market is None or modal is None:
            i += 1
            continue
        commodity = next((n for n, h in enumerate(low) if "commodity" in h), None)
        when = next((n for n, h in enumerate(low) if "date" in h), None)
        i += 1
        if i < len(lines) and re.fullmatch(r"[\s|:\-]+", lines[i]):
            i += 1  # the |---|---| separator
        while i < len(lines) and lines[i].lstrip().startswith("|"):
            cells = _cells(lines[i])
            i += 1
            if len(cells) <= max(market, modal):
                continue
            if commodity is not None and not any(w in cells[commodity].lower() for w in words):
                continue
            price = parse_price(cells[modal])
            if price is None or not cells[market]:
                continue
            arrival = parse_date(cells[when]) if when is not None and when < len(cells) else None
            rows.append(PriceRow(cells[market], price, arrival, quote=" | ".join(cells)))
    return rows or None


def parse_agent_prices(result: dict[str, Any]) -> list[PriceRow] | None:
    """The Agent's `output_schema` result: {"mandis": [{"mandi", "modal_price", "arrival_date"?}]}."""
    out: list[PriceRow] = []
    for item in result.get("mandis") or []:
        if not isinstance(item, dict):
            continue
        price = parse_price(str(item.get("modal_price", "")))
        name = str(item.get("mandi") or item.get("market") or "").strip()
        if price is None or not name:
            continue
        when = parse_date(str(item["arrival_date"])) if item.get("arrival_date") else None
        out.append(PriceRow(name, price, when, quote=f"{name}: modal price {price:g} (agent)"))
    return out or None
