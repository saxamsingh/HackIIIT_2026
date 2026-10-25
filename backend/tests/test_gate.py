import pytest

from app.models import AgentResult, Evidence, Triage
from app.safety import contains_dose, gate, reasons_to_withhold


@pytest.mark.parametrize(
    "text",
    [
        "Use 20 ml per litre of water",
        "spray 2.5ml/L twice",
        "500 gm per acre",
        "apply 1 kg/ha before sowing",
        "2 litres per acre",
        "mix 10 ml in a 15 litre pump",
        "३ ml प्रति लीटर",
        "10 मिली प्रति लीटर पानी",
        "5 ग्राम प्रति लीटर",
        "Dose: 250 mg",
        "ADD 30 ML",
        "use 2 g per litre",
    ],
)
def test_doses_are_detected(text):
    assert contains_dose(text)


@pytest.mark.parametrize(
    "text",
    [
        "Sell 20 quintal wheat at Mandi A",
        "Rs 2,492 per quintal",
        "Rs 24/kg",
        "70 km away",
        "2 acres of land",
        "Last date is 30 November",
        "18.5 mm of rain",
        "5 mandis checked",
        "Deadline in 7 days",
        "",
    ],
)
def test_ordinary_numbers_are_not_doses(text):
    assert not contains_dose(text)


def triage_for(intent="sell", text="sell wheat", language="en", asks_dose=False) -> Triage:
    return Triage(text=text, language=language, intent=intent, asks_dose=asks_dose)


def result(**over) -> AgentResult:
    base = dict(
        agent="sell",
        answer_en="Sell at Mandi A.",
        answer_hi="मंडी A में बेचें।",
        confidence=0.9,
        evidence=[Evidence(source_url="https://agmarknet.gov.in/", kind="fetch")],
    )
    return AgentResult(**{**base, **over})


def test_clean_answer_passes_in_the_farmers_language(repo, settings):
    en = gate(triage_for(language="en"), result(), repo, settings)
    hi = gate(triage_for(language="hinglish"), result(), repo, settings)
    assert en.status == "answered" and en.reply == "Sell at Mandi A."
    assert hi.status == "answered" and hi.reply == "मंडी A में बेचें।"
    assert repo.list_tickets() == []


def test_missing_evidence_is_withheld(repo, settings):
    out = gate(triage_for(), result(evidence=[]), repo, settings)
    assert out.status == "escalated" and out.reasons == ["missing_evidence"]


@pytest.mark.parametrize(("confidence", "escalated"), [(0.849, True), (0.85, False), (0.2, True)])
def test_confidence_threshold(repo, settings, confidence, escalated):
    out = gate(triage_for(), result(confidence=confidence), repo, settings)
    assert (out.status == "escalated") is escalated
    if escalated:
        assert out.reasons == ["low_confidence"]


def test_threshold_comes_from_settings(repo, settings):
    settings.confidence_threshold = 0.95
    assert gate(triage_for(), result(confidence=0.9), repo, settings).status == "escalated"


def test_dose_in_the_answer_is_withheld(repo, settings):
    out = gate(triage_for(), result(answer_en="Spray 2 ml per litre."), repo, settings)
    assert out.status == "escalated" and out.reasons == ["dose_in_answer"]


def test_dose_hidden_in_data_is_withheld(repo, settings):
    out = gate(triage_for(), result(data={"tips": [{"note": "use 5 ml/litre"}]}), repo, settings)
    assert out.reasons == ["dose_in_answer"]


def test_dose_question_is_escalated_with_no_agent_answer(repo, settings):
    t = triage_for("advisory", "Chlorpyrifos kitna ml dalu?", "hinglish", asks_dose=True)
    out = gate(t, None, repo, settings, farmer_id="farmer_demo_1")
    assert out.status == "escalated" and out.reasons == ["dose_question"]
    ticket = repo.get_ticket(out.ticket_id)
    assert ticket.query == "Chlorpyrifos kitna ml dalu?"
    assert ticket.farmer_id == "farmer_demo_1" and ticket.status == "open"


def test_a_confident_sourced_answer_to_a_dose_question_is_still_withheld(repo, settings):
    t = triage_for("advisory", "kitna ml", asks_dose=True)
    out = gate(t, result(answer_en="Use 2 ml per litre"), repo, settings)
    assert out.status == "escalated" and "dose_question" in out.reasons


def test_several_reasons_are_all_reported(repo, settings):
    out = gate(triage_for(), result(evidence=[], confidence=0.1, answer_en="10 ml/L"), repo, settings)
    assert out.reasons == ["missing_evidence", "low_confidence", "dose_in_answer"]


def test_escalation_never_leaks_the_withheld_answer(repo, settings):
    secret = "Spray 7 ml per litre of Chlorpyrifos"
    out = gate(triage_for(), result(answer_en=secret, answer_hi=secret, data={"x": secret}), repo, settings)
    ticket = repo.get_ticket(out.ticket_id)
    dumped = out.model_dump_json() + ticket.model_dump_json()
    assert "7 ml" not in dumped and "Chlorpyrifos" not in dumped
    assert out.data == {} and out.evidence == [] and out.confidence == 0.0


@pytest.mark.parametrize("language", ["en", "hinglish", "hi"])
def test_handoff_is_neutral_and_names_the_ticket(repo, settings, language):
    out = gate(triage_for("advisory", language=language, asks_dose=True), None, repo, settings)
    assert out.ticket_id in out.reply
    assert not contains_dose(out.reply)


def test_reasons_helper_is_pure(settings):
    assert reasons_to_withhold(triage_for(), result(), 0.85) == []
