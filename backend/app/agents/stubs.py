"""Fixed AgentResults so every route and the web app work before the real agents exist.

These are STUBS. Every number is a placeholder flagged `stub: true` and every evidence item is `assumed`,
so nothing here can be mistaken for a real price, scheme or deadline. The planner uses a stub only when the
real agent module raises NotImplementedError.
"""

from __future__ import annotations

from ..models import AgentName, AgentResult, Alert, Evidence

_MANDI_URL = "https://agmarknet.gov.in/"
_SCHEMES_URL = "https://www.myscheme.gov.in/"
_IMD_URL = "https://mausam.imd.gov.in/"


def _evidence(url: str, title: str) -> Evidence:
    return Evidence(source_url=url, kind="replay", title=title, quote="Stub placeholder", assumed=True)


def _option(mandi: str, *, modal: float, km: float, transport: float) -> dict[str, float | str]:
    return {
        "mandi": mandi,
        "modal_price": modal,
        "distance_km": km,
        "transport_cost": transport,
        "net_price": modal - transport,
    }


def sell(crop: str | None, quantity_qtl: float | None) -> AgentResult:
    crop = crop or "wheat"
    qty = quantity_qtl or 10.0
    options = [
        _option("Stub Mandi A", modal=2400.0, km=30.0, transport=12.0),
        _option("Stub Mandi B", modal=2450.0, km=60.0, transport=24.0),
        _option("Stub Mandi C", modal=2380.0, km=10.0, transport=4.0),
    ]
    best = max(options, key=lambda o: o["net_price"])
    nearest = min(options, key=lambda o: o["distance_km"])
    gain = round((best["net_price"] - nearest["net_price"]) * qty, 2)
    return AgentResult(
        agent="sell",
        answer_en=(
            f"Stub: sell {qty:g} quintal {crop} at {best['mandi']} "
            f"for about Rs {gain:g} more than the nearest mandi."
        ),
        answer_hi=f"स्टब: {qty:g} क्विंटल {crop} {best['mandi']} में बेचें, पास की मंडी से लगभग ₹{gain:g} ज़्यादा।",
        data={
            "stub": True,
            "crop": crop,
            "quantity_qtl": qty,
            "options": options,
            "best": best,
            "nearest": nearest,
            "msp": {"price_rs_per_qtl": None, "note": "MSP not sourced yet"},
            "gain_rs": gain,
            "formula": "(net price at best mandi - net price at nearest mandi) x quintals",
        },
        evidence=[_evidence(_MANDI_URL, f"{o['mandi']} price (stub)") for o in options],
        confidence=0.9,
    )


def subsidy(crop: str | None) -> AgentResult:
    schemes = [
        {
            "scheme_id": "stub-scheme-1",
            "name": "Stub income support scheme",
            "benefit": "Stub benefit text",
            "estimated_value_rs": None,
            "eligible": True,
            "missing_docs": ["Land record"],
            "deadline": None,
            "apply_url": _SCHEMES_URL,
            "reviewed": True,
            "packet_url": "/files/stub-packet.pdf",
        },
        {
            "scheme_id": "stub-scheme-2",
            "name": "Stub crop insurance scheme",
            "benefit": "Stub benefit text",
            "estimated_value_rs": None,
            "eligible": True,
            "missing_docs": [],
            "deadline": None,
            "apply_url": _SCHEMES_URL,
            "reviewed": True,
            "packet_url": "/files/stub-packet.pdf",
        },
    ]
    return AgentResult(
        agent="subsidy",
        answer_en="Stub: you may be eligible for 2 schemes. Your draft packets are ready to check.",
        answer_hi="स्टब: आप 2 योजनाओं के लिए पात्र हो सकते हैं। आवेदन के ड्राफ़्ट जांचने के लिए तैयार हैं।",
        data={"stub": True, "schemes": schemes},
        evidence=[_evidence(_SCHEMES_URL, "Scheme listing (stub)")],
        confidence=0.9,
    )


def claim(crop: str | None) -> AgentResult:
    return AgentResult(
        agent="claim",
        answer_en="Stub: your claim dossier draft is ready. Check it and submit it yourself.",
        answer_hi="स्टब: आपकी क्लेम फ़ाइल का ड्राफ़्ट तैयार है। जांचकर खुद जमा करें।",
        data={
            "stub": True,
            "claim_id": "claim_stub_1",
            "dossier_url": "/files/stub-dossier.pdf",
            "intimation_deadline": None,
            "warnings": ["Stub: photo GPS and timestamp not checked"],
        },
        evidence=[_evidence(_IMD_URL, "Weather warning (stub)")],
        confidence=0.9,
    )


def watch(alert_type: str = "hail") -> AgentResult:
    return AgentResult(
        agent="watch",
        answer_en=f"Stub: a {alert_type} warning was detected for the demo district.",
        answer_hi="स्टब: डेमो ज़िले के लिए चेतावनी मिली है।",
        data={"stub": True, "alert_type": alert_type},
        evidence=[_evidence(_IMD_URL, "District warning (stub)")],
        confidence=0.9,
    )


def alert_for(fixture_name: str, alert_type: str, source_url: str) -> Alert:
    """The Alert POST /demo/replay-monitor stores until the Watch agent is real."""
    return Alert(
        type=alert_type,  # type: ignore[arg-type]
        title=f"Stub {alert_type} alert ({fixture_name})",
        detail="Replayed from a recorded Monitor run. Stub text, not an IMD bulletin.",
        source_url=source_url,
        evidence=[Evidence(source_url=source_url, kind="monitor", title="Monitor run (replay)", assumed=True)],
    )


AGENTS: tuple[AgentName, ...] = ("sell", "subsidy", "claim", "watch")
