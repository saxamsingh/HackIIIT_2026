import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx
import pytest

from app.db import CHANNEL_MESSAGES, SqliteRepository, SupabaseRepository, make_repository
from app.models import Alert, ChannelMessage, Evidence, Farmer, LedgerEntry, RunRecord, Ticket, now
from app.seed import seed_demo


def farmer(**over) -> Farmer:
    base = dict(id="f1", name="Asha", state="S", district="D", crops=["wheat", "rice"], land_acres=1.5)
    return Farmer(**{**base, **over})


def test_farmer_roundtrip_keeps_json_fields(repo):
    repo.upsert_farmer(farmer())
    got = repo.get_farmer("f1")
    assert got == farmer(created_at=got.created_at) and got.crops == ["wheat", "rice"]
    assert repo.get_farmer("missing") is None


def test_upsert_replaces(repo):
    repo.upsert_farmer(farmer())
    repo.upsert_farmer(farmer(name="Asha Rani"))
    assert [f.name for f in repo.list_farmers()] == ["Asha Rani"]


def test_run_lifecycle_stores_streaming_url_and_result(repo):
    repo.save_run(RunRecord(id="r1", kind="agent", target="goal"))
    repo.update_run("r1", status="RUNNING", streaming_url="https://stream.example/1")
    done = repo.update_run("r1", status="COMPLETED", result={"mandis": [1, 2]}, steps=5)
    got = repo.get_run("r1")
    assert got.streaming_url == "https://stream.example/1"
    assert got.result == {"mandis": [1, 2]} and got.steps == 5 and got.status == "COMPLETED"
    assert done.updated_at >= got.created_at
    with pytest.raises(KeyError):
        repo.update_run("nope", status="FAILED")


def test_alerts_are_newest_first_and_area_alerts_reach_every_farmer(repo):
    ev = Evidence(source_url="https://x.example", kind="monitor")
    repo.add_alert(Alert(id="a1", type="hail", title="t1", detail="d", source_url="u", evidence=[ev]))
    repo.add_alert(Alert(id="a2", farmer_id="f1", type="price", title="t2", detail="d", source_url="u"))
    repo.add_alert(Alert(id="a3", farmer_id="f2", type="scheme", title="t3", detail="d", source_url="u"))
    assert [a.id for a in repo.list_alerts()][0] == "a3"
    assert {a.id for a in repo.list_alerts("f1")} == {"a1", "a2"}
    assert repo.list_alerts("f1")[-1].evidence[0].source_url == "https://x.example"


def test_ledger_confirm_and_filter(repo):
    repo.add_ledger(LedgerEntry(id="l1", farmer_id="f1", kind="sell", amount_rs=100, formula="x"))
    repo.add_ledger(LedgerEntry(id="l2", farmer_id="f2", kind="claim", amount_rs=50, formula="y"))
    assert repo.confirm_ledger("l1").confirmed is True
    assert [e.id for e in repo.list_ledger("f1")] == ["l1"]
    assert repo.list_ledger("f1")[0].confirmed is True and repo.list_ledger("f2")[0].confirmed is False
    with pytest.raises(KeyError):
        repo.confirm_ledger("zzz")


def test_ticket_roundtrip(repo):
    t = repo.create_ticket(Ticket(farmer_id=None, intent="advisory", query="q", reason="dose_question"))
    assert repo.get_ticket(t.id).reason == "dose_question"
    assert [x.id for x in repo.list_tickets()] == [t.id]


def test_channel_message_idempotency_claim_and_completion(repo):
    claimed, record = repo.claim_channel_message("SM123", "whatsapp:+9100")
    assert claimed and record.status == "processing"
    second, existing = repo.claim_channel_message("SM123", "whatsapp:+9100")
    assert not second and existing.status == "processing"
    repo.finish_channel_message("SM123", "hello farmer")
    third, existing = repo.claim_channel_message("SM123", "whatsapp:+9100")
    assert not third and existing.status == "completed" and existing.reply == "hello farmer"


def test_concurrent_channel_claim_only_has_one_winner(repo):
    def claim(_):
        return repo.claim_channel_message("SM_CONCURRENT", "whatsapp:+9100")[0]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(claim, range(8)))
    assert sum(results) == 1


def test_failed_channel_message_can_be_retried(repo):
    claimed, _ = repo.claim_channel_message("SM_RETRY", "whatsapp:+9100")
    assert claimed
    repo.fail_channel_message("SM_RETRY")
    claimed_again, record = repo.claim_channel_message("SM_RETRY", "whatsapp:+9100")
    assert claimed_again and record.status == "processing"


def test_old_whatsapp_deduplication_records_are_purged(repo):
    old = ChannelMessage(id="SM_OLD", sender="whatsapp:+9100", updated_at=now() - timedelta(days=10))
    recent = ChannelMessage(id="SM_RECENT", sender="whatsapp:+9100", updated_at=now())
    repo._put(CHANNEL_MESSAGES, old)
    repo._put(CHANNEL_MESSAGES, recent)
    repo.purge_channel_messages(7)
    assert repo._get(CHANNEL_MESSAGES, "SM_OLD") is None
    assert repo._get(CHANNEL_MESSAGES, "SM_RECENT") is not None


def test_seed_places_three_synthetic_farmers_in_the_demo_district(repo, settings):
    farmers = seed_demo(repo, settings)
    assert len(farmers) == 3
    assert {f.district for f in repo.list_farmers()} == {"Meerut"}
    assert {f.state for f in repo.list_farmers()} == {"Uttar Pradesh"}
    assert repo.get_run("run_demo_sell").streaming_url


def test_seed_is_idempotent(repo, settings):
    seed_demo(repo, settings)
    seed_demo(repo, settings)
    assert len(repo.list_farmers()) == 3 and len(repo.list_ledger()) == 1


def test_make_repository_picks_the_backend(settings):
    assert isinstance(make_repository(settings), SqliteRepository)
    settings.db_backend = "supabase"
    with pytest.raises(ValueError, match="SUPABASE_URL"):
        make_repository(settings)
    settings.supabase_url, settings.supabase_key = "https://x.supabase.co", "k"
    assert isinstance(make_repository(settings), SupabaseRepository)


class FakePostgrest:
    """A tiny in-memory PostgREST: enough to check the Supabase repository speaks it correctly."""

    def __init__(self):
        self.tables: dict[str, dict[str, dict]] = {}
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        table = request.url.path.rsplit("/", 1)[-1]
        rows = self.tables.setdefault(table, {})
        if request.method == "POST":
            row = json.loads(request.content)
            prefer = request.headers.get("prefer", "")
            if "ignore-duplicates" in prefer and row["id"] in rows:
                return httpx.Response(201, json=[])
            rows[row["id"]] = row
            if "return=representation" in prefer:
                return httpx.Response(201, json=[row])
            return httpx.Response(201)
        wanted = request.url.params.get("id")
        if wanted:
            return httpx.Response(200, json=[r for r in rows.values() if f"eq.{r['id']}" == wanted])
        return httpx.Response(200, json=list(rows.values()))


def test_supabase_repository_matches_sqlite_behaviour():
    fake = FakePostgrest()
    repo = SupabaseRepository("https://x.supabase.co", "secret", transport=httpx.MockTransport(fake))
    repo.upsert_farmer(farmer())
    repo.save_run(RunRecord(id="r1", kind="agent", target="g", result={"a": 1}))
    repo.update_run("r1", status="COMPLETED")
    repo.add_ledger(LedgerEntry(id="l1", farmer_id="f1", kind="sell", amount_rs=9, formula="f"))
    repo.confirm_ledger("l1")

    assert repo.get_farmer("f1").crops == ["wheat", "rice"]
    assert repo.get_run("r1").status == "COMPLETED" and repo.get_run("r1").result == {"a": 1}
    assert repo.list_ledger("f1")[0].confirmed is True
    assert repo.get_farmer("nope") is None

    post = next(r for r in fake.requests if r.method == "POST")
    assert post.headers["apikey"] == "secret" and post.headers["authorization"] == "Bearer secret"
    assert "merge-duplicates" in post.headers["prefer"] and post.url.params["on_conflict"] == "id"
    assert fake.tables["farmers"]["f1"]["crops"] == ["wheat", "rice"]  # native JSON, not a string


def test_supabase_channel_message_claims_are_idempotent():
    fake = FakePostgrest()
    repo = SupabaseRepository("https://x.supabase.co", "secret", transport=httpx.MockTransport(fake))
    first, _ = repo.claim_channel_message("SM-SUPA", "whatsapp:+9100")
    second, existing = repo.claim_channel_message("SM-SUPA", "whatsapp:+9100")
    assert first and not second and existing.status == "processing"
    repo.finish_channel_message("SM-SUPA", "done")
    third, existing = repo.claim_channel_message("SM-SUPA", "whatsapp:+9100")
    assert not third and existing.status == "completed" and existing.reply == "done"


def test_supabase_errors_are_raised(settings):
    unauthorised = httpx.MockTransport(lambda r: httpx.Response(401))
    repo = SupabaseRepository("https://x.supabase.co", "k", transport=unauthorised)
    with pytest.raises(httpx.HTTPStatusError):
        repo.list_farmers()


def test_make_repository_resolves_relative_path_against_backend_directory(settings, tmp_path, monkeypatch):
    import app.db as db_module

    monkeypatch.setattr(db_module, "BACKEND_DIR", tmp_path)
    settings.sqlite_path = __import__("pathlib").Path("./data/relative.db")
    repo = make_repository(settings)
    assert isinstance(repo, SqliteRepository)
    assert __import__("pathlib").Path(repo.path) == tmp_path / "data" / "relative.db"
    assert (tmp_path / "data" / "relative.db").exists()


def test_empty_sqlite_environment_variable_is_ignored(monkeypatch):
    from app.config import BACKEND_DIR, Settings

    monkeypatch.setenv("SQLITE_PATH", "")
    settings = Settings(_env_file=None)
    assert settings.sqlite_path == BACKEND_DIR / "khetkaaj.db"
