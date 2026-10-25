import json

import pytest

from app.tinyfish import (
    AgentEvent,
    BudgetExceeded,
    BudgetGuard,
    DiskCache,
    FixtureMissing,
    ReplayClient,
    WebClientError,
    load_monitor_fixture,
    make_web_client,
)

FIXTURES = None


@pytest.fixture
def replay(settings) -> ReplayClient:
    return ReplayClient(settings.tinyfish_fixtures_dir)


async def test_replay_search_and_fetch_parse_into_models(replay):
    found = await replay.search("anything at all")  # no exact match: the kind's default answers
    assert found.results[0].url.startswith("https://") and found.total_results == 2
    page = (await replay.fetch(["https://agmarknet.gov.in/"])).results[0]
    assert "Modal Price" in page.text and page.format == "markdown"


async def test_replay_agent_streams_events_in_order_and_returns_the_result(replay):
    seen: list[AgentEvent] = []

    async def on_event(e: AgentEvent):
        seen.append(e)

    run = await replay.run_agent("https://agmarknet.gov.in/", "any goal", on_event=on_event)
    assert [e.type for e in seen][:2] == ["STARTED", "STREAMING_URL"] and seen[-1].type == "COMPLETE"
    assert next(e for e in seen if e.type == "STREAMING_URL").streaming_url == run.streaming_url
    assert run.status == "COMPLETED" and len(run.result["mandis"]) == 6 and run.num_of_steps == 5
    assert run.run_id.startswith("run_") and run.run_id != "run_replay_mandi"  # every replay is its own run


async def test_replay_agent_accepts_a_sync_callback_and_none(replay):
    got = []
    await replay.run_agent("u", "g", on_event=got.append)
    assert got
    await replay.run_agent("u", "g")  # no callback is fine


def test_complete_event_accepts_both_result_spellings():
    sdk = AgentEvent.model_validate({"type": "COMPLETE", "status": "COMPLETED", "result_json": {"a": 1}})
    rest = AgentEvent.model_validate({"type": "COMPLETE", "status": "COMPLETED", "result": {"a": 1}})
    assert sdk.result == rest.result == {"a": 1}


async def test_exact_request_beats_the_default(tmp_path):
    for name, query, title in (("a", "wheat msp", "exact"), ("b", "other", "default")):
        doc = {"kind": "search", "default": name == "b", "request": {"query": query},
               "response": {"query": query, "results": [{"title": title, "url": "https://x.example"}]}}
        (tmp_path / f"search_{name}.json").write_text(json.dumps(doc), encoding="utf-8")
    client = ReplayClient(tmp_path)
    assert (await client.search("  Wheat MSP ")).results[0].title == "exact"
    assert (await client.search("unrecorded")).results[0].title == "default"


async def test_missing_fixture_is_a_clear_error(tmp_path):
    with pytest.raises(FixtureMissing, match="search"):
        await ReplayClient(tmp_path).search("x")


def test_monitor_fixture_lookup(settings):
    payload = load_monitor_fixture(settings.tinyfish_fixtures_dir, "hail")
    assert "hail" in payload["run"]["results"][0]["text"] and payload["run"]["results"][0]["url"]
    with pytest.raises(FixtureMissing, match="nope"):
        load_monitor_fixture(settings.tinyfish_fixtures_dir, "nope")


def test_there_is_a_fixture_for_every_tinyfish_kind(settings):
    kinds = {
        json.loads(p.read_text(encoding="utf-8"))["kind"] for p in settings.tinyfish_fixtures_dir.glob("*.json")
    }
    assert kinds == {"search", "fetch", "agent", "monitor"}


def test_disk_cache_roundtrip_and_ttl(tmp_path, monkeypatch):
    cache = DiskCache(tmp_path, ttl_seconds=60)
    req = {"query": "wheat", "n": 1}
    assert cache.get("search", req) is None
    cache.put("search", req, {"results": [1]})
    assert cache.get("search", req) == {"results": [1]}
    assert cache.get("search", {"query": "rice"}) is None
    assert cache.get("fetch", req) is None  # the kind is part of the key
    import time

    real = time.time()
    monkeypatch.setattr(time, "time", lambda: real + 61)
    assert cache.get("search", req) is None


def test_disk_cache_ignores_a_corrupt_file(tmp_path):
    cache = DiskCache(tmp_path, 60)
    cache.put("fetch", {"u": 1}, "v")
    next(tmp_path.glob("*.json")).write_text("{not json", encoding="utf-8")
    assert cache.get("fetch", {"u": 1}) is None


def test_budget_guard_caps_each_class_of_call():
    guard = BudgetGuard(max_agent_runs=2, max_free_calls=3)
    guard.charge("agent")
    guard.charge("agent")
    with pytest.raises(BudgetExceeded, match="agent"):
        guard.charge("agent")
    for kind in ("search", "fetch", "monitor"):
        guard.charge(kind)
    with pytest.raises(BudgetExceeded, match="search/fetch"):
        guard.charge("search")
    assert guard.usage() == {"agent_runs": 2, "max_agent_runs": 2, "free_calls": 3, "max_free_calls": 3}


def test_a_refused_call_is_not_counted():
    guard = BudgetGuard(1, 1)
    guard.charge("agent")
    for _ in range(3):
        with pytest.raises(BudgetExceeded):
            guard.charge("agent")
    assert guard.agent_runs == 1


def test_live_client_needs_a_key(settings):
    settings.tinyfish_mode = "live"
    with pytest.raises(WebClientError, match="TINYFISH_API_KEY"):
        make_web_client(settings)


def test_replay_is_the_default_mode(settings):
    assert make_web_client(settings).mode == "replay"
