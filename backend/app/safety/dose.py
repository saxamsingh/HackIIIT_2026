"""Dose detector for the safety gate: does this text state an amount of a chemical to apply?

An answer that says "2 ml per litre" is a dose, and KhetKaaj never gives one. Bare small units (ml, cc, mg)
count on their own; larger units (g, kg, litre) only count with a per-area or per-volume denominator, so
"Rs 24/kg" and "20 quintal" are not doses. Erring towards "dose" is deliberate: a false positive only
sends the farmer to a human.
"""

from __future__ import annotations

import re
from typing import Any

_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_NUM = r"\d+(?:[.,]\d+)?"
_SMALL_UNIT = r"(?:ml|mls|cc|mg|मिली|मि\.ली\.?|मिलीलीटर)"
_BIG_UNIT = r"(?:g|gm|gms|gram|grams|kg|kgs|kilo|litre|litres|liter|liters|ltr|l|ग्राम|किलो|किलोग्राम|लीटर)"
_DENOM = (
    r"(?:/|\bper\b|\bprati\b|प्रति)\s*\d*\s*"
    r"(?:acre|acres|ha|hectare|hectares|bigha|litre|litres|liter|liters|ltr|l|pump|tank|"
    r"एकड़|एकड|हेक्टेयर|बीघा|लीटर|पंप|टंकी)\b"
)

_SMALL = re.compile(rf"(?<![\w.]){_NUM}\s*{_SMALL_UNIT}(?![\w])", re.IGNORECASE)
_BIG_WITH_DENOM = re.compile(rf"(?<![\w.]){_NUM}\s*{_BIG_UNIT}\s*{_DENOM}", re.IGNORECASE)


def contains_dose(text: str) -> bool:
    t = text.translate(_DIGITS)
    return bool(_SMALL.search(t) or _BIG_WITH_DENOM.search(t))


def strings_in(value: Any) -> list[str]:
    """Every string inside a nested dict/list, so a dose hidden in `data` is found too."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings_in(v)]
    if isinstance(value, list | tuple):
        return [s for v in value for s in strings_in(v)]
    return []
