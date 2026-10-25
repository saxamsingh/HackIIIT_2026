"""Weather rules, Watch Mode and the webhook shapes it accepts."""

import pytest

from app import webhooks
from app.agents import claim as claim_agent
from app.agents import watch
from app.rules import weather
from app.seed import seed_demo
from app.tinyfish import ReplayClient

HAIL = "Thunderstorm with hail likely at isolated places in Meerut. Gusty winds likely."


class RecordingNotifier:
    def __init__(self, ok=True, raises=False):
        self.sent, self.ok, self.raises = [], ok, raises

    async def send(self, phone, text):
        if self.raises:
            raise RuntimeError("provider down")
        self.sent.append((phone, text))
        return self.ok


def payload(text=HAIL, baseline=False, url="https://mausam.imd.gov.in/"):
    return {
        "monitor": {"id": "m1", "config": {"url": url}},
        "run": {"id": "mr1", "is_baseline": baseline, "results": [{"url": url, "text": text}], "errors": []},
    }


@pytest.fixture
def world(settings, repo):
    seed_demo(repo, settings)
    return {"repo": repo, "web": ReplayClient(settings.tinyfish_fixtures_dir, repo=repo), "settings": settings}


# --- weather rules ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (HAIL, ["hail"]),
        ("Heavy rain likely over Meerut", ["heavy_rain"]),
        ("Hailstorm and very heavy rain expected", ["hail", "heavy_rain"]),
        ("Heavy rain is not expected.", []),
        ("No hail is expected in Meerut.", []),
        ("Hail likely in Meerut. Heavy rain is not expected.", ["hail"]),
        ("Light drizzle only", []),
        ("मेरठ में ओलावृष्टि की संभावना", ["hail"]),
        ("भारी बारिश की संभावना नहीं है", []),
        ("", []),
    ],
)
def test_classify_ignores_negated_sentences(text, expected):
    assert weather.classify(text) == expected


def test_district_matching_is_whole_word_and_case_insensitive():
    assert weather.mentions_district("Hail in MEERUT today", "Meerut")
    assert not weather.mentions_district("Hail in Meerutpur", "Meerut")
    assert not weather.mentions_district("Hail in Hapur", "Meerut")


def test_the_evidence_sentence_is_the_warning_not_the_negation():
    text = "Heavy rain is not expected. Hail likely in Meerut."
    assert weather.sentence_with(text, "hail") == "Hail likely in Meerut."


def test_claim_actions_cite_the_72_hour_rule_and_admit_what_is_common_practice():
    actions = weather.actions_for("hail")
    assert actions[0].source_url and not actions[0].assumed
    assert actions[1].source_url is None and actions[1].assumed
    assert weather.actions_for("price") == ()


# --- Watch Mode -------------------------------------------------------------------------------------------------
async def test_a_warning_alerts_every_farmer_in_the_district_and_prepares_a_claim_for_each(world):
    notifier = RecordingNotifier()
    alerts = await watch.handle_monitor_payload(payload(), notifier=notifier, **world)
    assert [a.farmer_id for a in alerts] == ["farmer_demo_1", "farmer_demo_2", "farmer_demo_3"]
    assert all(a.type == "hail" and a.claim_id and a.evidence[0].quote == HAIL.split(". ")[0] + "." for a in alerts)
    assert all(a.evidence[0].kind == "replay" and a.source_url == "https://mausam.imd.gov.in/" for a in alerts)
    assert len({a.claim_id for a in alerts}) == 3  # a dossier per farmer


async def test_notifications_use_each_farmers_language(world):
    notifier = RecordingNotifier()
    await watch.handle_monitor_payload(payload(), notifier=notifier, **world)
    by_phone = dict(notifier.sent)
    assert "ओलावृष्टि" in by_phone["+910000000001"]          # hi
    assert "ओलावृष्टि" in by_phone["+910000000002"]          # hinglish gets Devanagari too
    assert by_phone["+910000000003"].startswith("Hailstorm warning for Meerut")  # en


async def test_a_baseline_run_is_not_news(world):
    assert await watch.handle_monitor_payload(payload(baseline=True), notifier=RecordingNotifier(), **world) == []


async def test_a_warning_for_other_districts_alerts_nobody(world):
    other = payload("Thunderstorm with hail likely at isolated places in Saharanpur.")
    assert await watch.handle_monitor_payload(other, notifier=RecordingNotifier(), **world) == []


async def test_a_negated_warning_alerts_nobody(world):
    nothing = payload("Hail is not expected in Meerut. Heavy rain is not expected either.")
    assert await watch.handle_monitor_payload(nothing, notifier=RecordingNotifier(), **world) == []


async def test_hail_and_heavy_rain_together_raise_two_alerts_per_farmer(world):
    both = payload("Hail likely in Meerut. Very heavy rain likely in Meerut.")
    alerts = await watch.handle_monitor_payload(both, notifier=RecordingNotifier(), **world)
    assert len(alerts) == 6 and {a.type for a in alerts} == {"hail", "heavy_rain"}


async def test_the_same_warning_twice_is_not_a_second_alert(world):
    first = await watch.handle_monitor_payload(payload(), notifier=RecordingNotifier(), **world)
    notifier = RecordingNotifier()
    second = await watch.handle_monitor_payload(payload(), notifier=notifier, **world)
    assert len(first) == 3 and second == [] and notifier.sent == []  # and nobody is messaged twice


async def test_a_new_warning_text_does_alert_again(world):
    await watch.handle_monitor_payload(payload(), notifier=RecordingNotifier(), **world)
    again = await watch.handle_monitor_payload(
        payload("Fresh warning: severe hail likely in Meerut tonight."), notifier=RecordingNotifier(), **world
    )
    assert len(again) == 3


async def test_a_failing_notifier_never_loses_the_alert(world):
    alerts = await watch.handle_monitor_payload(payload(), notifier=RecordingNotifier(raises=True), **world)
    assert len(alerts) == 3 and len(world["repo"].list_alerts()) == 3


async def test_a_failing_claim_preparation_never_loses_the_alert(world, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("pdf failed")

    monkeypatch.setattr(claim_agent, "prepare_from_alert", boom)
    alerts = await watch.handle_monitor_payload(payload(), notifier=RecordingNotifier(), **world)
    assert len(alerts) == 3 and all(a.claim_id is None for a in alerts)


async def test_no_notifier_is_fine(world):
    assert len(await watch.handle_monitor_payload(payload(), notifier=None, **world)) == 3


async def test_a_json_formatted_page_is_read_too(world):
    page = payload()
    page["run"]["results"][0]["text"] = {"warning": HAIL}  # a "json" format fetch returns an object
    assert len(await watch.handle_monitor_payload(page, notifier=None, **world)) == 3


async def test_an_empty_run_raises_nothing(world):
    assert await watch.handle_monitor_payload({"run": {"results": []}}, notifier=None, **world) == []


# --- webhook shapes ---------------------------------------------------------------------------------------------
def test_run_webhook_detection_and_application(repo):
    body = {"event": "run.completed", "run_id": "r9", "status": "COMPLETED",
            "data": {"goal": "g", "result": {"a": 1}, "streaming_url": "https://s.example", "steps": [1, 2, 3]}}
    assert webhooks.is_run_webhook(body)
    assert webhooks.apply_run_webhook(repo, body) == "r9"
    row = repo.get_run("r9")
    assert row.status == "COMPLETED" and row.result == {"a": 1} and row.steps == 3 and row.target == "g"
    # a later webhook for a run we saw start keeps what we already stored
    assert not webhooks.is_run_webhook({"run_id": "r1", "status": "RUNNING"})
    assert not webhooks.is_run_webhook({"monitor": {}, "run": {"results": []}, "run_id": "x", "status": "COMPLETED"})


def test_monitor_payload_is_accepted_flat_or_nested():
    flat = payload()
    assert webhooks.monitor_payload(flat) is flat
    assert webhooks.monitor_payload({"event": "monitor.run", "data": flat}) is flat
    assert webhooks.monitor_payload({"foo": "bar"}) is None
    assert webhooks.monitor_payload({"run": {"no": "results"}}) is None


def test_the_webhook_route_dispatches_each_shape(client, repo):
    run = client.post("/webhooks/tinyfish", json={"event": "run.failed", "run_id": "rX", "status": "FAILED",
                                                   "data": {"error": {"message": "x", "category": "AGENT_FAILURE"}}})
    assert run.json() == {"ok": True, "handled": "run", "run_id": "rX"}
    mon = client.post("/webhooks/tinyfish", json=payload()).json()
    assert mon["handled"] == "monitor" and len(mon["alerts"]) == 3
    assert client.post("/webhooks/tinyfish", json={"hello": "world"}).json()["handled"] == "ignored"
    assert client.post("/webhooks/tinyfish", json=[1, 2]).status_code == 422


async def test_scheme_monitor_change_creates_state_scoped_review_alerts(world):
    scheme_payload = {
        "monitor": {
            "id": "scheme-monitor",
            "name": "New agriculture scheme notices",
            "config": {"query": "new agriculture subsidy scheme notice for farmers Uttar Pradesh"},
        },
        "run": {
            "id": "scheme-run-1",
            "is_baseline": False,
            "results": [{
                "title": "UP farmer equipment subsidy notice",
                "snippet": "New agriculture scheme notice; applications open soon",
                "url": "https://upagriculture.com/notices/equipment",
            }],
        },
    }
    notifier = RecordingNotifier()
    alerts = await watch.handle_monitor_payload(scheme_payload, notifier=notifier, **world)
    assert len(alerts) == 3
    assert all(a.type == "scheme" and a.claim_id is None for a in alerts)
    assert all("not yet reviewed" in a.detail for a in alerts)
    assert all(a.source_url == "https://upagriculture.com/notices/equipment" for a in alerts)
    assert len(notifier.sent) == 3
    assert all("KhetKaaj" in message and ("scheme" in message.lower() or "योजना" in message) for _, message in notifier.sent)

    duplicate = await watch.handle_monitor_payload(scheme_payload, notifier=notifier, **world)
    assert duplicate == []
    assert len(notifier.sent) == 3


async def test_scheme_monitor_baseline_does_not_alert(world):
    scheme_payload = {
        "monitor": {"name": "New agriculture scheme notices", "config": {"query": "new scheme notice Uttar Pradesh"}},
        "run": {"id": "baseline", "is_baseline": True, "results": [{
            "title": "New subsidy notice", "url": "https://example.gov.in/notice", "snippet": "Scheme"
        }]},
    }
    assert await watch.handle_monitor_payload(scheme_payload, notifier=RecordingNotifier(), **world) == []
