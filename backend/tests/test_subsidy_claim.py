"""Eligibility, the review gate, discovery, photo EXIF, reports and the claim agent."""

import io
from datetime import UTC, date, datetime

import pytest
import yaml
from conftest import review_all
from PIL import Image

from app import cli, discovery
from app.agents import claim as claim_agent
from app.agents import subsidy
from app.agents.base import AgentContext
from app.exif import PhotoMeta, photo_warnings, read_photo
from app.models import Alert, Farmer, Triage
from app.reports import _env, dossier_name, packet_name
from app.rules.eligibility import evaluate
from app.schemes import Scheme, load_schemes, review_scheme, save_discovered, unreview_scheme
from app.seed import seed_demo
from app.tinyfish import ReplayClient

EVENT = date(2026, 10, 23)


def jpeg(taken=None, gps=True) -> bytes:
    img = Image.new("RGB", (8, 8), "green")
    exif = Image.Exif()
    if taken:
        exif[0x0132] = taken
        exif[0x8769] = {0x9003: taken}
    if gps:
        exif[0x8825] = {1: "N", 2: (28.0, 59.0, 4.2), 3: "E", 4: (77.0, 42.0, 23.0)}
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def farmer(**over) -> Farmer:
    base = dict(id="f", name="Asha", state="Uttar Pradesh", district="Meerut", crops=["wheat"], land_acres=2,
                category="small", documents=["aadhaar", "bank_passbook", "land_record", "mobile_linked_aadhaar"])
    return Farmer(**{**base, **over})


def scheme(**over) -> Scheme:
    base = dict(id="s", name="S", benefit="b", apply_url="https://x.example")
    return Scheme(**{**base, **over})


# --- eligibility ------------------------------------------------------------------------------------------------
def by_id(settings):
    return {s.id: s for s in load_schemes(settings)}


@pytest.mark.parametrize(
    ("scheme_id", "who", "status", "missing"),
    [
        ("pm-kisan", dict(), "eligible", []),
        ("pm-kisan", dict(documents=["aadhaar", "bank_passbook"]), "eligible", ["land_record", "mobile_linked_aadhaar"]),
        ("pm-kisan", dict(land_acres=0), "ineligible", []),
        ("pmfby", dict(), "eligible", []),
        ("kcc", dict(documents=["aadhaar"]), "eligible", ["bank_passbook", "land_record"]),
        ("soil-health-card", dict(documents=[]), "eligible", []),
        ("pm-kusum", dict(), "eligible", []),
        ("up-krishi-yantra", dict(), "eligible", []),
        ("up-krishi-yantra", dict(state="Bihar"), "ineligible", []),
        ("pm-kmy", dict(), "needs_info", []),                       # age is unknown, so it is not claimed
        ("pm-kmy", dict(land_acres=6.5), "ineligible", []),         # over 2 hectares, whatever the age
        ("pm-kmy", dict(land_acres=4.94), "needs_info", []),        # exactly at the limit still passes the land rule
    ],
)
def test_eligibility_of_each_shipped_scheme(settings, scheme_id, who, status, missing):
    result = evaluate(farmer(**who), by_id(settings)[scheme_id])
    assert result.status == status
    if status == "eligible":
        assert result.missing_docs == missing
    if scheme_id == "pm-kmy" and status == "needs_info":
        assert result.needs_info == ["age"]


def test_a_rule_that_fails_beats_one_that_is_unknown():
    s = scheme(eligibility={"max_land_acres": 1}, requires_facts=["age"])
    assert evaluate(farmer(), s).status == "ineligible"


def test_an_unsupported_rule_never_silently_passes():
    r = evaluate(farmer(), scheme(eligibility={"mystery": True}))
    assert r.status == "needs_info" and "mystery" in r.needs_info[0]


@pytest.mark.parametrize(
    ("rules", "who", "ok"),
    [
        ({"categories": ["small", "marginal"]}, dict(category="other"), False),
        ({"categories": ["small", "marginal"]}, dict(category="marginal"), True),
        ({"crops_any": ["rice"]}, dict(crops=["wheat"]), False),
        ({"crops_any": ["rice"]}, dict(crops=["wheat", "rice"]), True),
        ({"min_land_acres": 3}, dict(land_acres=2), False),
        ({"states": ["Punjab"]}, dict(), False),
        ({"states": ["uttar pradesh"]}, dict(), True),      # case-insensitive
        ({"states": []}, dict(), True),                     # empty list means anywhere
    ],
)
def test_each_rule_kind(rules, who, ok):
    assert evaluate(farmer(**who), scheme(eligibility=rules)).eligible is ok


# --- review gate ------------------------------------------------------------------------------------------------
def test_nothing_ships_reviewed(settings):
    assert len(load_schemes(settings)) == 7 and load_schemes(settings, reviewed_only=True) == []


def test_review_records_who_and_when_and_keeps_the_files_comments(settings):
    before = (settings.knowledge_dir / "schemes" / "pmfby.yaml").read_text(encoding="utf-8")
    s = review_scheme(settings, "pmfby", "Asha Verma", today=date(2026, 10, 24))
    after = (settings.knowledge_dir / "schemes" / "pmfby.yaml").read_text(encoding="utf-8")
    assert s.reviewed and s.reviewed_by == "Asha Verma" and s.reviewed_at == "2026-10-24"
    assert "# enrolment cut-off dates" in after and before.count("#") == after.count("#")
    assert [x.id for x in load_schemes(settings, reviewed_only=True)] == ["pmfby"]
    assert yaml.safe_load(after)["reviewed"] is True


def test_review_needs_a_name_and_a_real_scheme(settings):
    for bad in ("", "   "):
        with pytest.raises(ValueError):
            review_scheme(settings, "pmfby", bad)
    for bad_id in ("nope", "../pmfby", "PMFBY", ""):
        with pytest.raises(KeyError):
            review_scheme(settings, bad_id, "x")


def test_unreview_withdraws_the_review(settings):
    review_scheme(settings, "kcc", "A")
    s = unreview_scheme(settings, "kcc")
    assert not s.reviewed and s.reviewed_by is None and load_schemes(settings, reviewed_only=True) == []


def test_cli_list_review_all_and_errors(settings, monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    assert cli.main(["list"]) == 0
    assert capsys.readouterr().out.count("NOT reviewed") == 7
    assert cli.main(["review", "pm-kisan", "--reviewer", "Asha"]) == 0
    out = capsys.readouterr().out
    assert "reviewed pm-kisan" in out and "source: https://services.india.gov.in" in out
    assert cli.main(["review", "nope", "--reviewer", "Asha"]) == 1
    assert cli.main(["review", "--all", "--reviewer", "Asha"]) == 0
    assert len(load_schemes(settings, reviewed_only=True)) == 7
    assert cli.main(["review", "--all", "--reviewer", "Asha"]) == 0 and "nothing to review" in capsys.readouterr().out
    assert cli.main(["unreview", "pm-kisan"]) == 0
    with pytest.raises(SystemExit):
        cli.main(["review", "--reviewer", "Asha"])  # neither ids nor --all
    with pytest.raises(SystemExit):
        cli.main(["review", "pm-kisan"])  # no reviewer


# --- Subsidy agent ----------------------------------------------------------------------------------------------
@pytest.fixture
def seeded(repo, settings):
    seed_demo(repo, settings)
    return repo


def sub_ctx(settings, repo, farmer_id="farmer_demo_1"):
    web = ReplayClient(settings.tinyfish_fixtures_dir)
    f = repo.get_farmer(farmer_id) if farmer_id else None
    return AgentContext(triage=Triage(text="s", language="en", intent="subsidy"), farmer=f, repo=repo, web=web,
                        settings=settings)


async def test_with_no_reviewed_scheme_there_is_no_answer(settings, seeded):
    r = await subsidy.run(sub_ctx(settings, seeded))
    assert r.evidence == [] and r.confidence == 0.0 and "reviewed" in r.answer_en


async def test_without_a_farmer_there_is_no_answer(settings, seeded):
    review_all(settings)
    assert (await subsidy.run(sub_ctx(settings, seeded, None))).confidence == 0.0


async def test_reviewed_schemes_are_matched_with_packets_sources_and_a_cited_value(settings, seeded):
    review_all(settings)
    r = await subsidy.run(sub_ctx(settings, seeded))
    schemes = {s["scheme_id"]: s for s in r.data["schemes"]}
    assert [s["scheme_id"] for s in r.data["schemes"]][:2] != []  # eligible first
    eligible = [s for s in r.data["schemes"] if s["eligible"]]
    assert len(eligible) == 6 and schemes["pm-kmy"]["eligible"] is False and schemes["pm-kmy"]["needs_info"] == ["age"]
    assert all(s["packet_url"].startswith("/files/packet-farmer_demo_1-") for s in eligible)
    assert schemes["pm-kmy"]["packet_url"] is None
    assert all(s["deadline"] is None for s in r.data["schemes"])  # nothing cited, nothing shown
    assert r.data["ledger_value_rs"] == 6000 and "PM-KISAN" in r.data["formula"]
    assert r.confidence == 0.9 and r.evidence and all(e.kind == "knowledge" for e in r.evidence)
    assert (settings.files_dir / "packet-farmer_demo_1-pm-kisan.pdf").read_bytes().startswith(b"%PDF")


async def test_a_farmer_missing_documents_is_told_which(settings, seeded):
    review_all(settings)
    r = await subsidy.run(sub_ctx(settings, seeded, "farmer_demo_2"))
    s = {x["scheme_id"]: x for x in r.data["schemes"]}
    assert s["pm-kisan"]["eligible"] and s["pm-kisan"]["missing_docs"] == ["land_record", "mobile_linked_aadhaar"]
    assert "need a document" in r.answer_en


async def test_an_ineligible_scheme_carries_no_evidence_or_missing_docs(settings, seeded):
    review_all(settings)
    r = await subsidy.run(sub_ctx(settings, seeded, "farmer_demo_3"))  # 6.5 acres: over the pm-kmy limit
    kmy = next(x for x in r.data["schemes"] if x["scheme_id"] == "pm-kmy")
    assert kmy["eligible"] is False and kmy["missing_docs"] == [] and kmy["packet_url"] is None


def test_the_packet_template_lists_documents_sources_and_the_banner(settings):
    s = by_id(settings)["pm-kisan"]
    f = farmer(documents=["aadhaar"])
    text = _env.get_template("packet.txt.j2").render(
        farmer=f, scheme=s, reasons=["You have farmland"], generated="now", mode="replay",
        documents=[{"label": "Aadhaar card", "have": True}, {"label": "Land record", "have": False}])
    assert "Farmer verifies and submits" in text and "NOT SUBMITTED" in text
    assert "[x] Aadhaar card" in text and "[ ] Land record - you have not listed this" in text
    assert "https://pmkisan.gov.in/" in text and "Rs 6000" in text and "no deadline is cited" in text
    assert "services.india.gov.in" in text and "Data mode: replay" in text
    assert packet_name(f, s) == "packet-f-pm-kisan.pdf"
    assert dossier_name("claim_x/../y") == "dossier-claim_x-y.pdf"  # path characters cannot survive


# --- discovery --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "iso"),
    [("Last date to apply: 30 November 2026.", "2026-11-30"), ("Deadline is 5 Dec 2026", "2026-12-05"),
     ("Apply before 1 January 2027", "2027-01-01"), ("No closing date is stated.", None),
     ("last date soon", None), ("closes on 31 February 2026", None)],
)
def test_find_deadline(text, iso):
    assert discovery.find_deadline(text) == iso


async def test_discovery_writes_unreviewed_candidates_and_is_idempotent(settings):
    web = ReplayClient(settings.tinyfish_fixtures_dir)
    found = await discovery.discover(web, settings, today=date(2026, 10, 24))
    assert len(found) == 2 and all(s.discovered and not s.reviewed and s.eligibility == {} for s in found)
    assert [s.deadline for s in found] == ["2026-11-30", None]
    assert all(s.sources[0].retrieved == "2026-10-24" and s.estimated_value_rs is None for s in found)
    assert load_schemes(settings, reviewed_only=True) == []  # a discovered scheme is never shown by itself
    assert len(load_schemes(settings)) == 9
    assert await discovery.discover(web, settings) == []  # already known, nothing new


async def test_discovery_survives_a_dead_web(settings, tmp_path):
    assert await discovery.discover(ReplayClient(tmp_path), settings) == []


def test_a_discovered_record_never_overwrites_a_reviewed_one(settings):
    review_scheme(settings, "pmfby", "A")
    clash = scheme(id="pmfby", name="Impostor", apply_url="https://evil.example")
    assert save_discovered(settings, clash) is None
    assert by_id(settings)["pmfby"].name.startswith("PMFBY") and by_id(settings)["pmfby"].reviewed


# --- photos -----------------------------------------------------------------------------------------------------
def test_exif_time_and_gps_are_read():
    m = read_photo("a.jpg", jpeg("2026:10:23 10:30:00"))
    assert m.readable and m.taken_at == datetime(2026, 10, 23, 10, 30, tzinfo=UTC)
    assert round(m.lat, 4) == 28.9845 and round(m.lon, 4) == 77.7064


def test_south_and_west_are_negative():
    img = Image.new("RGB", (8, 8))
    exif = Image.Exif()
    exif[0x8825] = {1: "S", 2: (10.0, 0.0, 0.0), 3: "W", 4: (20.0, 30.0, 0.0)}
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    m = read_photo("a.jpg", buf.getvalue())
    assert m.lat == -10.0 and m.lon == -20.5


def test_a_photo_without_exif_and_a_non_image_never_raise():
    plain = read_photo("p.jpg", jpeg(taken=None, gps=False))
    assert plain.readable and plain.taken_at is None and plain.lat is None
    assert read_photo("x.pdf", b"%PDF-1.4 not an image").readable is False
    assert read_photo("empty.jpg", b"").readable is False


def test_photo_warnings():
    ok = PhotoMeta("ok.jpg", datetime(2026, 10, 23, 9, tzinfo=UTC), 28.0, 77.0)
    assert photo_warnings([ok], EVENT) == []
    early = PhotoMeta("early.jpg", datetime(2026, 10, 10, tzinfo=UTC), 28.0, 77.0)
    late = PhotoMeta("late.jpg", datetime(2026, 11, 20, tzinfo=UTC), 28.0, 77.0)
    out = photo_warnings([early, late, PhotoMeta("blank.jpg"), PhotoMeta("bad.pdf", readable=False)], EVENT)
    assert "early.jpg: taken 13 days BEFORE the event date" in out
    assert "late.jpg: taken 28 days after the event date" in out
    assert "blank.jpg: no capture time in the photo (EXIF missing)" in out
    assert "blank.jpg: no GPS location in the photo" in out and "bad.pdf: not a readable image" in out
    near = PhotoMeta("near.jpg", datetime(2026, 10, 24, 1, tzinfo=UTC), 1.0, 1.0)
    assert photo_warnings([near], EVENT) == []  # a day either side is tolerated


# --- claim ------------------------------------------------------------------------------------------------------
def form(**over):
    return {"farmer_id": "farmer_demo_1", "crop": "wheat", "event": "hail", "event_date": "2026-10-23", **over}


def test_a_claim_with_good_photos_reports_no_photo_problems(client):
    files = [("files", ("field1.jpg", jpeg("2026:10:23 10:30:00"), "image/jpeg"))]
    r = client.post("/api/claim/photos", data=form(), files=files)
    assert r.status_code == 200
    body = r.json()
    assert not any("field1.jpg" in w for w in body["warnings"]) and body["confidence"] == 0.92
    assert body["intimation_deadline"] == "2026-10-26"
    assert {e["kind"] for e in body["evidence"]} == {"replay", "knowledge"}
    assert client.get(body["dossier_url"]).content.startswith(b"%PDF")


def test_a_photo_without_exif_is_flagged_and_confidence_drops_but_stays_answerable(client):
    files = [("files", ("blank.jpg", jpeg(taken=None, gps=False), "image/jpeg"))]
    body = client.post("/api/claim/photos", data=form(), files=files).json()
    assert "blank.jpg: no capture time in the photo (EXIF missing)" in body["warnings"]
    assert "blank.jpg: no GPS location in the photo" in body["warnings"] and body["confidence"] == 0.88


def test_a_photo_from_before_the_event_is_flagged(client):
    files = [("files", ("old.jpg", jpeg("2026:09:01 10:00:00"), "image/jpeg"))]
    body = client.post("/api/claim/photos", data=form(), files=files).json()
    assert any("BEFORE the event date" in w for w in body["warnings"])


def test_no_photos_is_a_warning_not_a_failure(client):
    body = client.post("/api/claim/photos", data=form()).json()
    assert any("No photos attached" in w for w in body["warnings"])


def test_a_non_image_upload_is_flagged_not_trusted(client):
    files = [("files", ("notes.jpg", b"not an image", "image/jpeg"))]
    body = client.post("/api/claim/photos", data=form(), files=files).json()
    assert "notes.jpg: not a readable image" in body["warnings"]


def test_upload_limits_and_validation(client):
    nine = [("files", (f"{i}.jpg", jpeg(), "image/jpeg")) for i in range(9)]
    assert client.post("/api/claim/photos", data=form(), files=nine).status_code == 413
    assert client.post("/api/claim/photos", data=form(event="meteor")).status_code == 422
    assert client.post("/api/claim/photos", data=form(farmer_id="zz")).status_code == 404
    assert client.post("/api/claim/photos", data=form(event_date="x")).status_code == 422


def test_a_late_report_is_warned_about_but_still_prepared(client):
    body = client.post("/api/claim", json={**form(), "event_date": "2020-01-01"}).json()
    assert any("reporting window ended on 2020-01-04" in w for w in body["warnings"])


def test_the_dossier_names_the_72_hour_source(client):
    body = client.post("/api/claim", json=form()).json()
    quote = [e for e in body["evidence"] if e["kind"] == "knowledge"][0]
    assert quote["source_url"].endswith("AU3866.pdf") and "72 hours" in quote["quote"]


async def test_prepare_from_alert_builds_a_dossier_for_the_farmer(settings, seeded):
    alert = Alert(farmer_id="farmer_demo_1", type="hail", title="t", detail="Hail likely in Meerut.",
                  source_url="https://mausam.imd.gov.in/")
    web = ReplayClient(settings.tinyfish_fixtures_dir)
    prepared = await claim_agent.prepare_from_alert(alert, seeded.get_farmer("farmer_demo_1"), repo=seeded, web=web,
                                                    settings=settings)
    assert prepared.claim_id.startswith("claim_") and prepared.result.data["corroborated"] is True
    assert prepared.dossier_url == f"/files/dossier-{prepared.claim_id}.pdf"
    assert (settings.files_dir / f"dossier-{prepared.claim_id}.pdf").read_bytes().startswith(b"%PDF")
    assert prepared.result.confidence == 0.92 and prepared.result.evidence[0].quote == "Hail likely in Meerut."


async def test_a_claim_with_no_weather_source_has_no_evidence(settings, seeded, tmp_path):
    inputs = claim_agent.ClaimInputs(seeded.get_farmer("farmer_demo_1"), "wheat", "hail", EVENT)
    prepared = await claim_agent.prepare(inputs, repo=seeded, web=ReplayClient(tmp_path), settings=settings)
    assert prepared.result.evidence == [] and prepared.result.confidence == 0.6
    assert any("does not clearly support" in w for w in prepared.result.data["warnings"])


def test_the_dossier_template_has_the_banner_deadline_and_photo_table(settings):
    text = _env.get_template("dossier.txt.j2").render(
        claim_id="claim_1", farmer=farmer(), crop="wheat", event_label="Hailstorm", event_date="2026-10-23",
        weather_quote="Hail likely.", weather_url="https://u.example", weather_kind="replay",
        corroboration="The record supports the claimed event.", intimation_deadline="2026-10-26",
        intimation_source="https://s.example",
        photos=[{"name": "a.jpg", "taken": "2026-10-23 10:30 UTC", "location": "28.98, 77.70"}],
        warnings=["w1"], generated="now", mode="replay")
    assert "Farmer verifies and submits" in text and "by 2026-10-26 (72 hours from the event)" in text
    assert "a.jpg: taken 2026-10-23 10:30 UTC; location 28.98, 77.70" in text and "- w1" in text
    assert "14447" in text and "confirm with your insurer" in text


def test_the_phones_location_is_a_labelled_fallback_not_a_substitute(client):
    files = [("files", ("blank.jpg", jpeg("2026:10:23 10:30:00", gps=False), "image/jpeg"))]
    data = {**form(), "device_lat": "28.98", "device_lon": "77.70"}
    body = client.post("/api/claim/photos", data=data, files=files).json()
    assert "blank.jpg: no GPS in the photo; the phone's location when uploading is recorded instead" in body["warnings"]
    assert body["confidence"] == 0.88  # still counted as a photo problem


def test_a_photo_with_its_own_gps_ignores_the_phones_location(client):
    files = [("files", ("good.jpg", jpeg("2026:10:23 10:30:00"), "image/jpeg"))]
    data = {**form(), "device_lat": "1.0", "device_lon": "1.0"}
    body = client.post("/api/claim/photos", data=data, files=files).json()
    assert not any("good.jpg" in w for w in body["warnings"]) and body["confidence"] == 0.92
