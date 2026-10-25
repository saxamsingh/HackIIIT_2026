"""The safety gate: the last thing between an agent and a farmer. CLAUDE.md section 8.

An agent's answer reaches the farmer only if it has evidence, is confident enough, and states no dose.
Otherwise it is withheld: the farmer gets a neutral hand-off, a ticket is created for a human, and
nothing of the withheld answer is copied into the reply, the ticket or the response.
"""

from __future__ import annotations

from ..config import Settings
from ..db import Repository
from ..models import AgentResult, GatedResponse, Language, Ticket, Triage
from .dose import contains_dose, strings_in

HANDOFF: dict[Language, str] = {
    "en": "I cannot answer this one myself. I have passed your question to a farm expert (ticket {ticket}). "
          "They will get back to you. Please do not spray or apply anything until they do.",
    "hinglish": "Is sawal ka jawab main khud nahi de sakta. Maine aapka sawal krishi visheshagya ko bhej diya "
                "hai (ticket {ticket}). Wo aapse sampark karenge. Tab tak koi dawai ya khad na daalein.",
    "hi": "इस सवाल का जवाब मैं खुद नहीं दे सकता। मैंने आपका सवाल कृषि विशेषज्ञ को भेज दिया है (टिकट {ticket})। "
          "वे आपसे संपर्क करेंगे। तब तक कोई दवा या खाद न डालें।",
}


def reasons_to_withhold(triage: Triage, result: AgentResult | None, threshold: float) -> list[str]:
    reasons: list[str] = []
    if triage.asks_dose or triage.intent == "advisory":
        reasons.append("dose_question")
    if result is None:
        if "dose_question" not in reasons:
            reasons.append("no_answer")
        return reasons
    if not result.evidence:
        reasons.append("missing_evidence")
    if result.confidence < threshold:
        reasons.append("low_confidence")
    texts = [result.answer_en, result.answer_hi, *strings_in(result.data)]
    if any(contains_dose(t) for t in texts):
        reasons.append("dose_in_answer")
    return reasons


def pick_answer(result: AgentResult, language: Language) -> str:
    if language == "en" or not result.answer_hi:
        return result.answer_en
    return result.answer_hi


def gate(
    triage: Triage,
    result: AgentResult | None,
    repo: Repository,
    settings: Settings,
    farmer_id: str | None = None,
) -> GatedResponse:
    reasons = reasons_to_withhold(triage, result, settings.confidence_threshold)
    if not reasons:
        assert result is not None  # reasons is empty only when a result exists
        return GatedResponse(
            status="answered",
            language=triage.language,
            intent=triage.intent,
            reply=pick_answer(result, triage.language),
            agent=result.agent,
            data=result.data,
            evidence=result.evidence,
            confidence=result.confidence,
            run_id=result.run_id,
        )

    ticket = repo.create_ticket(
        Ticket(farmer_id=farmer_id, intent=triage.intent, query=triage.text, reason=",".join(reasons))
    )
    return GatedResponse(
        status="escalated",
        language=triage.language,
        intent=triage.intent,
        reply=HANDOFF[triage.language].format(ticket=ticket.id),
        ticket_id=ticket.id,
        reasons=reasons,
    )
