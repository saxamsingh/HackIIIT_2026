import pytest

from app.orchestrator.triage import triage


@pytest.mark.parametrize(
    ("text", "language", "intent", "crop", "qty", "dose"),
    [
        ("Gehu kahan bechun? 20 quintal", "hinglish", "sell", "wheat", 20.0, False),
        ("Where should I sell wheat?", "en", "sell", "wheat", None, False),
        ("गेहूं कहां बेचूं? 20 क्विंटल", "hi", "sell", "wheat", 20.0, False),
        ("धान का भाव क्या है", "hi", "sell", "rice", None, False),
        ("२० क्विंटल सरसों बेचना है", "hi", "sell", "mustard", 20.0, False),
        ("Chlorpyrifos kitna ml dalu?", "hinglish", "advisory", None, None, True),
        ("How much imidacloprid per acre?", "en", "advisory", None, None, True),
        ("कीटनाशक कितना मिली डालूं", "hi", "advisory", None, None, True),
        ("Gehu me kitna khad dalu", "hinglish", "advisory", "wheat", None, True),
        ("Meri fasal kharab ho gayi, claim kaise karun", "hinglish", "claim", None, None, False),
        ("Hail damaged my crop, how do I claim insurance", "en", "claim", None, None, False),
        ("ओलावृष्टि से नुकसान हुआ", "hi", "claim", None, None, False),
        ("Kaun si yojana mere liye hai?", "hinglish", "subsidy", None, None, False),
        ("Am I eligible for any subsidy scheme?", "en", "subsidy", None, None, False),
        ("PM-Kisan ka paisa kab aayega", "hinglish", "subsidy", None, None, False),
        ("hello", "en", "unknown", None, None, False),
        ("", "en", "unknown", None, None, False),
    ],
)
def test_triage(text, language, intent, crop, qty, dose):
    t = triage(text)
    assert (t.language, t.intent, t.crop, t.quantity_qtl, t.asks_dose) == (language, intent, crop, qty, dose)


def test_a_dose_question_is_never_a_sell_question():
    # "bech" and a crop are present, but the pesticide name wins: advisory is checked first.
    assert triage("Gehu bechne se pehle chlorpyrifos kitna ml dalu").intent == "advisory"


def test_asking_how_many_kg_to_sell_is_not_a_dose_question():
    t = triage("Gehu kitna kg bechun")
    assert t.intent == "sell" and not t.asks_dose


@pytest.mark.parametrize(
    ("text", "qtl"),
    [("50 kg wheat bechna hai", 0.5), ("2 tonnes of rice", 20.0), ("12.5 qtl gehu", 12.5), ("sell wheat", None)],
)
def test_quantity_is_converted_to_quintals(text, qtl):
    assert triage(text).quantity_qtl == qtl
