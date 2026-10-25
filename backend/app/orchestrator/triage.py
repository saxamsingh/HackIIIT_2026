"""Triage: language, intent, crop and quantity from one message. Pure functions, no network, no model.

Advisory (spraying and dosing) is checked first on purpose: a dose question must never be mistaken for
a sell or scheme question and answered by an agent.
"""

from __future__ import annotations

import re

from ..models import Intent, Language, Triage
from . import lexicon as lx

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_TOKEN = re.compile(r"[\wऀ-ॿ]+(?:-[\w]+)*", re.UNICODE)
_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_QTY = re.compile(
    r"(\d+(?:\.\d+)?)\s*(quintals?|qtl|kwintal|क्विंटल|tonnes?|tons?|टन|kgs?|kilos?|किलो)\b",
    re.IGNORECASE,
)
_TO_QUINTAL = {"quintal": 1.0, "quintals": 1.0, "qtl": 1.0, "kwintal": 1.0, "क्विंटल": 1.0,
               "tonne": 10.0, "tonnes": 10.0, "ton": 10.0, "tons": 10.0, "टन": 10.0,
               "kg": 0.01, "kgs": 0.01, "kilo": 0.01, "kilos": 0.01, "किलो": 0.01}


def normalise(text: str) -> str:
    """Lowercase and turn Devanagari digits into ASCII digits."""
    return text.translate(_DIGITS).lower().strip()


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(normalise(text))


def detect_language(text: str) -> Language:
    if _DEVANAGARI.search(text):
        return "hi"
    if set(tokens(text)) & lx.HINGLISH_WORDS:
        return "hinglish"
    return "en"


def detect_crop(text: str) -> str | None:
    for tok in tokens(text):
        if tok in lx.CROPS:
            return lx.CROPS[tok]
    return None


def detect_quantity_qtl(text: str) -> float | None:
    m = _QTY.search(normalise(text))
    if not m:
        return None
    return round(float(m.group(1)) * _TO_QUINTAL[m.group(2).lower()], 4)


def asks_dose(text: str) -> bool:
    """True for "how much of X do I use" questions and for any mention of a named pesticide."""
    toks = set(tokens(text))
    if toks & lx.PESTICIDES:
        return True
    if toks & lx.DOSE_QUESTION_WORDS and toks & (lx.DOSE_UNIT_WORDS | lx.ADVISORY_WORDS):
        return True
    if "how much" in normalise(text) and toks & (lx.DOSE_UNIT_WORDS | lx.ADVISORY_WORDS):
        return True
    return bool(re.search(r"\d\s*(ml|मिली)\b", normalise(text)))


def detect_intent(text: str, dose: bool, crop: str | None) -> Intent:
    toks = set(tokens(text))
    low = normalise(text)
    if dose or toks & lx.ADVISORY_WORDS:
        return "advisory"
    if toks & lx.CLAIM_WORDS or any(p in low for p in lx.CLAIM_PHRASES):
        return "claim"
    if toks & lx.SUBSIDY_WORDS or any(p in low for p in lx.SUBSIDY_PHRASES):
        return "subsidy"
    if toks & lx.SELL_WORDS or (crop and toks & lx.WHERE_WORDS):
        return "sell"
    return "unknown"


def triage(text: str) -> Triage:
    crop = detect_crop(text)
    dose = asks_dose(text)
    return Triage(
        text=text,
        language=detect_language(text),
        intent=detect_intent(text, dose, crop),
        crop=crop,
        quantity_qtl=detect_quantity_qtl(text),
        asks_dose=dose,
    )
