"""Hindi and English reply templates for every intent, plus an optional, guarded LLM rewrite.

Templates are filled from structured data only. The LLM (LLM_PHRASING=1, off by default) sees nothing but
the finished template text, never a web page (CLAUDE.md section 2.3), and its output is discarded unless
it keeps every number and adds no dose.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

import httpx

from .config import Settings
from .models import Language
from .safety.dose import contains_dose

log = logging.getLogger("khetkaaj.replies")

CROP_HI = {
    "wheat": "गेहूं", "rice": "धान", "mustard": "सरसों", "maize": "मक्का", "sugarcane": "गन्ना",
    "potato": "आलू", "bajra": "बाजरा", "soybean": "सोयाबीन", "chickpea": "चना", "cotton": "कपास",
}
ALERT_LABELS = {
    "hail": ("hailstorm", "ओलावृष्टि"),
    "heavy_rain": ("heavy rain", "भारी बारिश"),
    "scheme": ("new scheme notice", "नई योजना की सूचना"),
    "price": ("price change", "भाव में बदलाव"),
}

MENU: dict[Language, str] = {
    "en": "I can help you sell your crop, find schemes, or prepare a crop-damage claim. "
    "Try: 'Where should I sell wheat? 20 quintal'.",
    "hinglish": "Main fasal bechne, yojana dhoondhne ya fasal nuksan ka claim banane me madad kar sakta hoon. "
    "Jaise: 'Gehu kahan bechun? 20 quintal'.",
    "hi": "मैं फसल बेचने, योजना खोजने या फसल नुकसान का क्लेम बनाने में मदद कर सकता हूं। "
    "जैसे: 'गेहूं कहां बेचूं? 20 क्विंटल'।",
}


def rupees(n: float) -> str:
    """Indian digit grouping: 1234567 -> ₹12,34,567."""
    whole = f"{round(n):d}"
    sign, digits = ("-", whole[1:]) if whole.startswith("-") else ("", whole)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join([*groups, tail])
    return f"{sign}₹{digits}"


def qty(n: float) -> str:
    return f"{n:g}"


def crop_hi(crop: str) -> str:
    return CROP_HI.get(crop, crop)


# --- sell -------------------------------------------------------------------------------------------------------
def sell(
    crop: str, quantity_qtl: float, best: dict, nearest: dict, gain_rs: float, msp: dict | None
) -> tuple[str, str]:
    msp_en = msp_hi = ""
    if msp and msp.get("price_rs_per_qtl"):
        price = rupees(msp["price_rs_per_qtl"])
        year = msp.get("marketing_season", "")
        msp_en = f" MSP for {year} is {price} per quintal."
        msp_hi = f" {year} का MSP {price} प्रति क्विंटल है।"
    if gain_rs > 0:
        en = (
            f"Best place to sell {qty(quantity_qtl)} quintal {crop}: {best['mandi']}, about "
            f"{rupees(best['net_price'])} per quintal after transport. That is {rupees(gain_rs)} more than "
            f"{nearest['mandi']}.{msp_en}"
        )
        hi = (
            f"{qty(quantity_qtl)} क्विंटल {crop_hi(crop)} बेचने की सबसे अच्छी जगह: {best['mandi']}, भाड़े के बाद लगभग "
            f"{rupees(best['net_price'])} प्रति क्विंटल। यह {nearest['mandi']} से {rupees(gain_rs)} ज़्यादा है।{msp_hi}"
        )
    else:
        en = (
            f"Your nearest mandi, {nearest['mandi']}, already pays the best price after transport "
            f"({rupees(nearest['net_price'])} per quintal).{msp_en}"
        )
        hi = (
            f"आपकी सबसे पास की मंडी, {nearest['mandi']}, भाड़े के बाद सबसे अच्छा भाव दे रही है "
            f"({rupees(nearest['net_price'])} प्रति क्विंटल)।{msp_hi}"
        )
    return en, hi


# --- subsidy ----------------------------------------------------------------------------------------------------
def subsidy(eligible: list[str], needs_docs: int, needs_info: int, none_reviewed: bool) -> tuple[str, str]:
    if none_reviewed:
        return (
            "No reviewed scheme list is available yet, so I cannot tell you which schemes fit you.",
            "अभी जांची हुई योजनाओं की सूची उपलब्ध नहीं है, इसलिए मैं नहीं बता सकता कि कौन सी योजना आपके लिए है।",
        )
    if not eligible:
        return (
            "I did not find a scheme you clearly qualify for from what I know about you.",
            "आपकी जानकारी के आधार पर मुझे कोई ऐसी योजना नहीं मिली जिसके लिए आप स्पष्ट रूप से पात्र हों।",
        )
    names = ", ".join(eligible[:3])
    extra_en = f" {needs_docs} of them need a document you have not listed." if needs_docs else ""
    extra_hi = f" इनमें से {needs_docs} के लिए ऐसा दस्तावेज़ चाहिए जो आपने नहीं बताया।" if needs_docs else ""
    if needs_info:
        extra_en += f" {needs_info} more depend on details I do not have."
        extra_hi += f" {needs_info} और योजनाएं उन जानकारियों पर निर्भर हैं जो मेरे पास नहीं हैं।"
    return (
        f"You may qualify for {len(eligible)} scheme(s): {names}.{extra_en} Your draft packets are ready. "
        "Check them and apply yourself; nothing is submitted for you.",
        f"आप {len(eligible)} योजना(ओं) के लिए पात्र हो सकते हैं: {names}।{extra_hi} आपके आवेदन के ड्राफ़्ट तैयार हैं। "
        "जांचकर खुद आवेदन करें; आपकी ओर से कुछ भी जमा नहीं होता।",
    )


# --- claim ------------------------------------------------------------------------------------------------------
def claim(
    event: str, claim_id: str, deadline: str | None, corroborated: bool, warnings: int
) -> tuple[str, str]:
    label_en, label_hi = ALERT_LABELS.get(event, (event, event))
    when_en = f" Report the loss to your insurer by {deadline}." if deadline else ""
    when_hi = f" नुकसान की सूचना {deadline} तक अपने बीमा कंपनी को दें।" if deadline else ""
    weather_en = (
        "The weather record supports your claim."
        if corroborated
        else "The weather record does not clearly support this event."
    )
    weather_hi = (
        "मौसम रिकॉर्ड आपके क्लेम की पुष्टि करता है।"
        if corroborated
        else "मौसम रिकॉर्ड इस घटना की साफ़ पुष्टि नहीं करता।"
    )
    warn_en = f" {warnings} thing(s) to check are listed in the dossier." if warnings else ""
    warn_hi = f" जांचने की {warnings} बातें फ़ाइल में लिखी हैं।" if warnings else ""
    return (
        f"Your {label_en} claim dossier {claim_id} is ready. {weather_en}{when_en}{warn_en} "
        "Check it and submit it yourself; KhetKaaj never submits for you.",
        f"आपकी {label_hi} के क्लेम की फ़ाइल {claim_id} तैयार है। {weather_hi}{when_hi}{warn_hi} "
        "जांचकर खुद जमा करें; KhetKaaj आपकी ओर से कुछ जमा नहीं करता।",
    )


# --- watch ------------------------------------------------------------------------------------------------------
def alert(alert_type: str, district: str) -> tuple[str, str]:
    label_en, label_hi = ALERT_LABELS.get(alert_type, (alert_type, alert_type))
    if alert_type in ("hail", "heavy_rain"):
        return (
            f"{label_en.capitalize()} warning for {district}. If your crop is damaged, take dated photos and open "
            "KhetKaaj to prepare your claim.",
            f"{district} के लिए {label_hi} की चेतावनी। फसल खराब हो तो तारीख वाली फ़ोटो लें और क्लेम बनाने के लिए "
            "KhetKaaj खोलें।",
        )
    return (
        f"New {label_en} for {district}. Open KhetKaaj to see if it applies to you.",
        f"{district} के लिए {label_hi}। देखने के लिए KhetKaaj खोलें कि यह आपके लिए है या नहीं।",
    )


def no_data(what_en: str, what_hi: str) -> tuple[str, str]:
    return (
        f"I could not get a reliable {what_en} just now. A farm expert will help instead.",
        f"अभी मुझे भरोसेमंद {what_hi} नहीं मिल पाया। इसके बजाय कृषि विशेषज्ञ आपकी मदद करेंगे।",
    )


# --- optional LLM rewrite ---------------------------------------------------------------------------------------
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_SYSTEM = (
    "You rewrite short messages for Indian farmers in simple, warm language. Keep the same language. "
    "Keep every number and name exactly. Add no new facts, advice, amounts or numbers. Reply with the "
    "rewritten message only."
)


def numbers(text: str) -> Counter[str]:
    return Counter(n.replace(",", "") for n in _NUM.findall(text))


def acceptable_rewrite(original: str, rewritten: str) -> bool:
    """Keep the rewrite only if it carries exactly the original's numbers and states no dose."""
    return (
        bool(rewritten.strip())
        and numbers(original) == numbers(rewritten)
        and not contains_dose(rewritten)
        and len(rewritten) <= 2 * len(original) + 40
    )


async def polish(text: str, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> str:
    """Return `text`, or a validated LLM rewrite of it when LLM_PHRASING is on. Never raises."""
    if not (settings.llm_phrasing and settings.anthropic_api_key):
        return text
    try:
        async with httpx.AsyncClient(transport=transport, timeout=20) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.llm_model,
                    "max_tokens": 400,
                    "system": _SYSTEM,
                    "messages": [{"role": "user", "content": text}],
                },
            )
        r.raise_for_status()
        rewritten = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    except (httpx.HTTPError, ValueError, KeyError) as e:
        log.warning("LLM rewrite skipped: %s", type(e).__name__)
        return text
    if acceptable_rewrite(text, rewritten):
        return rewritten.strip()
    log.warning("LLM rewrite rejected: numbers changed or a dose appeared")
    return text
