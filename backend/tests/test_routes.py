"""Every route returns contract-shaped data. The shapes are asserted by validating against the models."""

import pytest

from app.schemes import Scheme, SchemeSource, save_discovered
from app.models import (
    Alert,
    ClaimResponse,
    Farmer,
    GatedResponse,
    HealthResponse,
    LedgerEntry,
    LedgerResponse,
    RunRecord,
    SchemesResponse,
)


def test_health(client):
    body = HealthResponse.model_validate(client.get("/health").json())
    assert body.status == "ok" and body.tinyfish_mode == "replay" and body.demo_district == "Meerut"


def test_farmers_are_seeded(client):
    farmers = [Farmer.model_validate(f) for f in client.get("/api/farmers").json()]
    assert [f.id for f in farmers] == ["farmer_demo_1", "farmer_demo_2", "farmer_demo_3"]


def test_chat_sell_is_answered_from_sourced_prices(client):
    out = GatedResponse.model_validate(
        client.post(
            "/api/chat", json={"text": "Gehu kahan bechun? 20 quintal", "farmer_id": "farmer_demo_1"}
        ).json()
    )
    assert out.status == "answered" and out.agent == "sell" and out.language == "hinglish"
    assert out.data["best"]["mandi"] == "Delhi (Azadpur)" and out.data["quantity_qtl"] == 20.0
    assert len(out.data["options"]) == 6 and out.data["msp"]["price_rs_per_qtl"] == 2585
    assert len(out.evidence) == 7  # one per price line plus the MSP source
    assert all(e.kind in ("replay", "knowledge") for e in out.evidence)  # replay is never labelled live
    assert out.data["data_mode"] == "replay" and "stub" not in out.data
    assert out.data["ledger_entry_id"]  # the projected value was recorded
    assert out.reply.startswith("20 क्विंटल")


def test_chat_dose_question_is_escalated_and_creates_a_ticket(client, repo):
    out = GatedResponse.model_validate(
        client.post(
            "/api/chat", json={"text": "Chlorpyrifos kitna ml dalu?", "farmer_id": "farmer_demo_1"}
        ).json()
    )
    assert out.status == "escalated" and out.reasons == ["dose_question"]
    assert out.data == {} and out.evidence == [] and out.agent is None
    ticket = repo.get_ticket(out.ticket_id)
    assert ticket.query == "Chlorpyrifos kitna ml dalu?" and ticket.farmer_id == "farmer_demo_1"


def test_chat_unknown_returns_a_menu_and_no_ticket(client, repo):
    out = GatedResponse.model_validate(client.post("/api/chat", json={"text": "hello"}).json())
    assert out.status == "menu" and out.ticket_id is None and "sell" in out.reply.lower()
    assert repo.list_tickets() == []


def test_chat_unknown_farmer_is_404(client):
    assert client.post("/api/chat", json={"text": "hi", "farmer_id": "zz"}).status_code == 404


def test_sell_route(client):
    body = {"crop": "wheat", "quantity_qtl": 20, "farmer_id": "farmer_demo_2"}
    out = GatedResponse.model_validate(client.post("/api/sell", json=body).json())
    assert out.status == "answered" and out.language == "hinglish" and out.data["best"]["mandi"]
    assert client.post("/api/sell", json={"crop": "wheat", "quantity_qtl": 0}).status_code == 422
    assert client.post("/api/sell", json={**body, "farmer_id": "zz"}).status_code == 404


def test_repeating_a_sell_question_does_not_inflate_the_ledger(client):
    body = {"crop": "wheat", "quantity_qtl": 20, "farmer_id": "farmer_demo_1"}
    first = client.post("/api/sell", json=body).json()["data"]["ledger_entry_id"]
    second = client.post("/api/sell", json=body).json()["data"]["ledger_entry_id"]
    ledger = client.get("/api/ledger", params={"farmer_id": "farmer_demo_1"}).json()
    assert first == second and len(ledger["entries"]) == 2  # the seeded entry and one projected sell
    assert ledger["projected_rs"] == 1440 and ledger["total_rs"] == 1800


def test_schemes_are_withheld_until_a_person_has_reviewed_them(client, repo):
    r = client.get("/api/schemes", params={"farmer_id": "farmer_demo_1"})
    out = SchemesResponse.model_validate(r.json())
    assert r.status_code == 200 and out.schemes == [] and "reviewed" in out.note  # as shipped, nothing is shown
    assert repo.list_tickets() == []  # and loading the page does not open a ticket every time


def test_schemes_once_reviewed(reviewed_client):
    out = SchemesResponse.model_validate(
        reviewed_client.get("/api/schemes", params={"farmer_id": "farmer_demo_1"}).json()
    )
    eligible = [s for s in out.schemes if s.eligible]
    assert len(eligible) >= 2 and all(s.reviewed and s.packet_url.startswith("/files/") for s in eligible)
    assert all(s.evidence for s in out.schemes)
    assert reviewed_client.get("/api/schemes").status_code == 200  # defaults to the first farmer
    assert reviewed_client.get("/api/schemes", params={"farmer_id": "zz"}).status_code == 404
    pdf = reviewed_client.get(eligible[0].packet_url)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_claim_route_builds_a_dossier(client):
    body = {"farmer_id": "farmer_demo_1", "crop": "wheat", "event": "hail", "event_date": "2026-10-23"}
    out = ClaimResponse.model_validate(client.post("/api/claim", json=body).json())
    assert out.status == "draft" and out.dossier_url.startswith("/files/dossier-claim_") and out.evidence
    assert out.intimation_deadline == "2026-10-26"
    assert client.get(out.dossier_url).content.startswith(b"%PDF")
    assert client.post("/api/claim", json={**body, "farmer_id": "zz"}).status_code == 404
    assert client.post("/api/claim", json={**body, "event": "meteor"}).status_code == 422
    assert client.post("/api/claim", json={**body, "event_date": "yesterday"}).status_code == 422


def test_claim_without_corroborating_weather_goes_to_a_person(client):
    # The recorded warning is about hail in the district, so a heavy-rain claim is not supported.
    body = {"farmer_id": "farmer_demo_1", "crop": "wheat", "event": "heavy_rain", "event_date": "2026-10-23"}
    assert client.post("/api/claim", json=body).status_code == 409


def test_ledger_total_counts_only_confirmed_entries(client):
    out = LedgerResponse.model_validate(client.get("/api/ledger", params={"farmer_id": "farmer_demo_1"}).json())
    assert out.total_rs == 1800 and out.projected_rs == 0 and len(out.entries) == 1


def test_ledger_confirm_moves_money_from_projected_to_total(client, repo):
    repo.add_ledger(LedgerEntry(id="l_new", farmer_id="farmer_demo_2", kind="sell", amount_rs=500, formula="f"))
    before = client.get("/api/ledger", params={"farmer_id": "farmer_demo_2"}).json()
    assert (before["total_rs"], before["projected_rs"]) == (0, 500)
    assert client.post("/api/ledger/l_new/confirm").json()["confirmed"] is True
    after = client.get("/api/ledger", params={"farmer_id": "farmer_demo_2"}).json()
    assert (after["total_rs"], after["projected_rs"]) == (500, 0)
    assert client.post("/api/ledger/zzz/confirm").status_code == 404


def test_replay_monitor_creates_an_alert_and_a_claim_dossier_per_farmer(client):
    created = Alert.model_validate(client.post("/demo/replay-monitor", json={"fixture_name": "hail"}).json())
    assert created.type == "hail" and created.evidence and created.claim_id and created.farmer_id
    listed = [Alert.model_validate(a) for a in client.get("/api/alerts").json()]
    assert len(listed) == 3 and all(a.claim_id for a in listed)  # one per seeded farmer in the district
    assert created.id in {a.id for a in listed}
    assert client.get(f"/files/dossier-{created.claim_id}.pdf").status_code == 200
    assert client.post("/demo/replay-monitor", json={"fixture_name": "nope"}).status_code == 404


def test_replaying_the_same_warning_twice_does_not_duplicate_alerts(client):
    client.post("/demo/replay-monitor", json={"fixture_name": "hail"})
    assert client.post("/demo/replay-monitor", json={"fixture_name": "hail"}).status_code == 409
    assert len(client.get("/api/alerts").json()) == 3


def test_alerts_can_be_filtered_by_farmer(client):
    client.post("/demo/replay-monitor", json={"fixture_name": "hail"})
    mine = client.get("/api/alerts", params={"farmer_id": "farmer_demo_2"}).json()
    assert [a["farmer_id"] for a in mine] == ["farmer_demo_2"]


def test_runs_listing_and_lookup(client):
    client.post("/api/sell", json={"crop": "wheat", "quantity_qtl": 5})
    runs = [RunRecord.model_validate(r) for r in client.get("/api/runs").json()]
    assert runs and all(r.mode == "replay" for r in runs)
    assert {r.kind for r in runs} >= {"fetch", "agent"}  # the seeded sample run and the fetch just made
    sample = RunRecord.model_validate(client.get("/api/runs/run_demo_sell").json())
    assert sample.status == "COMPLETED" and sample.streaming_url
    assert client.get("/api/runs", params={"kind": "agent", "limit": 1}).json()[0]["kind"] == "agent"
    assert client.get("/api/runs/zzz").status_code == 404


def test_webhook_token_check(client, settings):
    payload = {"run_id": "run_1", "status": "COMPLETED"}
    assert client.post("/webhooks/tinyfish", json=payload).json()["handled"] == "run"
    settings.tinyfish_webhook_token = "s3cret"  # the app shares this Settings object
    assert client.post("/webhooks/tinyfish", json=payload).status_code == 403
    assert client.post("/webhooks/tinyfish?token=wrong", json=payload).status_code == 403
    assert client.post("/webhooks/tinyfish?token=s3cret", json=payload).status_code == 200


def test_files_are_served_and_confined(client):
    pdf = client.get("/files/stub-dossier.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.get("/files/missing.pdf").status_code == 404
    for evil in ("..%2F..%2Fpyproject.toml", "%2E%2E%2Fsecret", ".env", "a%5Cb.pdf"):
        assert client.get(f"/files/{evil}").status_code == 404


def test_cors_allows_the_configured_origin(client):
    r = client.options(
        "/health", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}
    )
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


@pytest.mark.parametrize(
    "path",
    ["/health", "/api/farmers", "/api/alerts", "/api/ledger", "/api/runs", "/api/runs/run_demo_sell",
     "/api/schemes/review-queue", "/openapi.json"],
)
def test_every_get_route_responds(client, path):
    assert client.get(path).status_code == 200


def test_planner_uses_a_stub_only_when_the_agent_is_unimplemented(client, monkeypatch):
    from app.agents import sell
    from app.models import AgentResult, Evidence

    async def not_ready(ctx):
        raise NotImplementedError

    monkeypatch.setattr(sell, "run", not_ready)
    stubbed = client.post("/api/chat", json={"text": "Gehu kahan bechun?"}).json()
    assert stubbed["data"]["stub"] is True and stubbed["evidence"][0]["assumed"] is True

    async def real_sell(ctx):
        return AgentResult(
            agent="sell", answer_en="REAL answer", confidence=0.95,
            evidence=[Evidence(source_url="https://agmarknet.gov.in/", kind="fetch")],
        )

    monkeypatch.setattr(sell, "run", real_sell)
    real = client.post("/api/chat", json={"text": "Gehu kahan bechun?"}).json()
    assert real["reply"] == "REAL answer" and "stub" not in real["data"]


def test_operator_tickets_endpoint_lists_open_and_validates_status(client):
    from app.models import Ticket

    client.app.state.repo.create_ticket(
        Ticket(farmer_id="farmer_demo_1", intent="advisory", query="Dose?", reason="dose_question")
    )
    assert len(client.get("/api/tickets?status=open").json()) == 1
    assert client.get("/api/tickets?status=bad").status_code == 422


def test_scheme_review_queue_requires_named_human_acknowledgement(client, settings):
    queue = client.get("/api/schemes/review-queue")
    assert queue.status_code == 200
    candidates = queue.json()
    assert len(candidates) == 7
    assert all(not s["reviewed"] and s["sources"] for s in candidates)

    scheme_id = candidates[0]["id"]
    blocked = client.post(f"/api/schemes/{scheme_id}/review", json={"reviewer": "Reviewer", "sources_read": False})
    assert blocked.status_code == 400
    assert client.get("/api/schemes/review-queue").json()  # failed review leaves the scheme unpublished

    published = client.post(f"/api/schemes/{scheme_id}/review", json={"reviewer": "  Asha Rao  ", "sources_read": True})
    assert published.status_code == 200
    assert published.json()["reviewed"] is True
    assert published.json()["reviewed_by"] == "Asha Rao"
    assert published.json()["reviewed_at"]
    assert scheme_id not in {s["id"] for s in client.get("/api/schemes/review-queue").json()}


def test_scheme_review_route_rejects_unknown_scheme(client):
    response = client.post("/api/schemes/not-a-real-scheme/review", json={"reviewer": "Asha", "sources_read": True})
    assert response.status_code == 404


def test_reviewed_scheme_reaches_farmer_eligibility_results(client):
    review = client.post("/api/schemes/pm-kisan/review", json={"reviewer": "Asha Rao", "sources_read": True})
    assert review.status_code == 200
    response = client.get("/api/schemes", params={"farmer_id": "farmer_demo_1"})
    assert response.status_code == 200
    body = response.json()
    assert any(s["scheme_id"] == "pm-kisan" and s["reviewed"] for s in body["schemes"])
    pm_kisan = next(s for s in body["schemes"] if s["scheme_id"] == "pm-kisan")
    assert pm_kisan["packet_url"] and pm_kisan["evidence"]


def test_scheme_discovery_is_explicit_and_labeled_as_replay(client):
    response = client.post("/api/schemes/discover", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "replay"
    assert isinstance(body["count"], int)
    assert "replay" in body["note"].lower()


def test_auto_discovered_scheme_without_rules_cannot_be_published(client, settings):
    scheme = Scheme(
        id="auto-discovered-test-candidate",
        name="Unverified farmer support notice",
        benefit="Auto-discovered page summary; not verified",
        apply_url="https://example.gov.in/notice",
        sources=[SchemeSource(url="https://example.gov.in/notice", title="Notice", retrieved="2026-10-25")],
        discovered=True,
        eligibility={},
    )
    save_discovered(settings, scheme)
    response = client.post(
        f"/api/schemes/{scheme.id}/review",
        json={"reviewer": "Asha Rao", "sources_read": True},
    )
    assert response.status_code == 422
    assert "eligibility rules" in response.json()["detail"]
    assert not next(item for item in client.get("/api/schemes/review-queue").json() if item["id"] == scheme.id)["reviewed"]
