"""Weather rules: from the text of an official warning to an alert type, and what to do about it.

Pure and deterministic. The text is only ever matched against keywords, never sent to a model.

A sentence that negates ("Heavy rain is not expected", "no hail") never counts as a warning. That errs on the
safe side: a negated advice sentence ("do not go out during hail") is also skipped, which can only lead to a
claim not being corroborated and so being looked at by a person, never to one being wrongly supported."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import AlertType

_HAIL = ("hail", "hailstorm", "hailstone", "ओला", "ओले", "ओलावृष्टि")
_HEAVY_RAIN = (
    "heavy rain", "heavy to very heavy", "very heavy rain", "extremely heavy", "heavy rainfall",
    "भारी बारिश", "भारी वर्षा", "अत्यधिक वर्षा",
)
_KEYWORDS: dict[AlertType, tuple[str, ...]] = {"hail": _HAIL, "heavy_rain": _HEAVY_RAIN}
_NEGATION = re.compile(
    r"(?<!\w)(no|not|nil|never|without|unlikely|neither|nor)(?!\w)|नहीं|कोई चेतावनी नहीं", re.IGNORECASE
)
_SPLIT = re.compile(r"(?<=[.!?।\n])\s+")


def _positive_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SPLIT.split(text) if s.strip() and not _NEGATION.search(s)]


def classify(text: str) -> list[AlertType]:
    """Every alert type a non-negated sentence mentions, hail first."""
    sentences = [s.lower() for s in _positive_sentences(text)]
    return [t for t, words in _KEYWORDS.items() if any(w in s for s in sentences for w in words)]


def mentions_district(text: str, district: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(district.lower())}(?!\w)", text.lower()))


def sentence_with(text: str, alert_type: AlertType, limit: int = 300) -> str:
    """The (non-negated) sentence that triggered the alert, kept as evidence."""
    words = _KEYWORDS[alert_type]
    for part in _positive_sentences(text):
        if any(w in part.lower() for w in words):
            return part[:limit]
    return text.strip()[:limit]


@dataclass(frozen=True)
class Action:
    text_en: str
    text_hi: str
    source_url: str | None
    assumed: bool  # True when this is common practice rather than taken from an official page


# Kept deliberately small. The 72-hour rule is cited; the photo advice is common practice, so it says so.
_CLAIM_ACTIONS = (
    Action(
        "Report the loss to your insurer, bank or agriculture department within 72 hours.",
        "नुकसान की सूचना 72 घंटे के भीतर अपने बीमा कंपनी, बैंक या कृषि विभाग को दें।",
        "https://eparlib.nic.in/bitstream/123456789/977813/1/AU3866.pdf",
        False,
    ),
    Action(
        "Take dated photos of the damaged field before cleaning it up.",
        "खेत की सफाई से पहले नुकसान की तारीख वाली फ़ोटो लें।",
        None,
        True,
    ),
)
_ACTIONS: dict[AlertType, tuple[Action, ...]] = {"hail": _CLAIM_ACTIONS, "heavy_rain": _CLAIM_ACTIONS}


def actions_for(alert_type: AlertType) -> tuple[Action, ...]:
    return _ACTIONS.get(alert_type, ())
