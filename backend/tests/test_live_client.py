"""The live TinyFish client, driven through a fake SDK. No network."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.tinyfish import (
    BudgetExceeded,
    BudgetGuard,
    DiskCache,
    ReplayClient,
    TinyFishClient,
    WebClientError,
    looks_blocked,
)

ISO = "2026-01-01T00:00:00Z"


class Dump:
    """Stands in for an SDK pydantic model."""

    def __init__(self, data):
        self._d = data

    def model_dump(self, mode=None):
        return self._d


def ev(type_, run_id="r1", **extra):
    return Dump({"type": type_, "run_id": run_id, "timestamp": ISO, **extra})


def good_events(result=None):
    return [
        ev("STARTED"),
        ev("STREAMING_URL", streaming_url="https://stream.example/1"),
        ev("PROGRESS", purpose="Opening the page"),
        ev("PROGRESS", purpose="Reading the table"),
        ev("COMPLETE", status="COMPLETED", result_json=result if result is not None else {"mandis": [1]}),
    ]


class FakeStream:
    def __init__(self, items, fail_at=None, hold=0.0, tracker=None):
        self.items, self.fail_at, self.hold, self.tracker = items, fail_at, hold, tracker

    async def __aenter__(self):
        if self.tracker:
            self.tracker["active"] += 1
            self.tracker["peak"] = max(self.tracker["peak"], self.tracker["active"])
        return self

    async def __aexit__(self, *a):
        if self.tracker:
            self.tracker["active"] -= 1

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for i, item in enumerate(self.items):
            if self.fail_at is not None and i == self.fail_at:
                raise ConnectionError("stream dropped")
            if self.hold:
                await asyncio.sleep(self.hold)
            yield item


class FakeSDK:
    def __init__(self, events=None, fail_at=None, runs=None, hold=0.0, fail_start=False):
        self.tracker = {"active": 0, "peak": 0}
        self.calls = {"search": 0, "fetch": [], "agent": []}
        events = events if events is not None else good_events()

        outer = self

        class Agent:
            def stream(self, **kw):
                outer.calls["agent"].append(kw)
                if fail_start:
                    raise ConnectionError("cannot connect")
                return FakeStream(events, fail_at, hold, outer.tracker)

        class Search:
            async def query(self, q, purpose=None):
                outer.calls["search"] += 1
                return Dump({"query": q, "results": [{"title": "t", "url": "https://x.example", "position": 1}],
                             "total_results": 1, "page": 0})

        class Fetch:
            async def get_contents(self, urls, purpose=None, **kw):
                outer.calls["fetch"].append({"urls": urls, **kw})
                return Dump({"results": [{"url": urls[0], "text": "hello", "format": "markdown"}], "errors": []})

        class Runs:
            def __init__(self, seq):
                self.seq = list(seq)

            async def get(self, run_id):
                return self.seq.pop(0) if len(self.seq) > 1 else self.seq[0]

        class Monitors:
            async def create(self, type_, config, cron, **kw):
                outer.calls["monitor"] = (type_, config, cron, kw)
                return Dump({"monitor": {"id": "m1"}, "run": {"id": "mr1"}})

        class Wallet:
            async def get(self):
                return SimpleNamespace(available_balance="12.50")

        self.agent, self.search, self.fetch = Agent(), Search(), Fetch()
        self.runs, self.monitors, self.wallet = Runs(runs or []), Monitors(), Wallet()


def make(settings, repo, sdk, tmp_path, runs=5, free=5):
    live = settings.model_copy(update={"tinyfish_mode": "live", "tinyfish_api_key": "k"})
    client = TinyFishClient(live, BudgetGuard(runs, free), DiskCache(tmp_path / "c", 60), repo, sdk)
    client.poll_interval = 0
    return client


async def test_search_is_budgeted_cached_and_recorded(settings, repo, tmp_path):
    sdk = FakeSDK()
    client = make(settings, repo, sdk, tmp_path)
    a = await client.search("wheat msp")
    b = await client.search("wheat msp")
    assert a == b and sdk.calls["search"] == 1  # the second call is a free cache hit
    assert client.budget.free_calls == 1
    runs = [r for r in repo.list_runs() if r.kind == "search"]
    assert len(runs) == 1 and runs[0].status == "COMPLETED" and runs[0].mode == "live"


async def test_fetch_fresh_skips_the_cache_and_asks_for_ttl_zero(settings, repo, tmp_path):
    sdk = FakeSDK()
    client = make(settings, repo, sdk, tmp_path)
    await client.fetch(["https://a.example"])
    await client.fetch(["https://a.example"])  # cached
    await client.fetch(["https://a.example"], fresh=True)
    assert len(sdk.calls["fetch"]) == 2
    assert sdk.calls["fetch"][0] == {"urls": ["https://a.example"]} and sdk.calls["fetch"][1]["ttl"] == 0


async def test_sdk_errors_become_web_client_errors_and_failed_runs(settings, repo, tmp_path):
    sdk = FakeSDK()

    async def boom(*a, **k):
        raise RuntimeError("bad gateway")

    sdk.search.query = boom
    client = make(settings, repo, sdk, tmp_path)
    with pytest.raises(WebClientError, match="search failed"):
        await client.search("x")
    assert [r.status for r in repo.list_runs() if r.kind == "search"] == ["FAILED"]


async def test_agent_run_stores_the_streaming_url_before_the_run_finishes(settings, repo, tmp_path):
    client = make(settings, repo, FakeSDK(), tmp_path)
    seen: dict = {}

    def on_event(e):
        if e.type == "STREAMING_URL":
            seen["row"] = repo.get_run("r1")  # looked up the instant the event arrives

    run = await client.run_agent("https://x.example", "goal", {"type": "object"}, on_event=on_event)
    assert seen["row"].streaming_url == "https://stream.example/1" and seen["row"].status == "RUNNING"
    final = repo.get_run("r1")
    assert final.status == "COMPLETED" and final.steps == 2 and final.result == {"mandis": [1]}
    assert run.status == "COMPLETED" and run.run_id == "r1" and run.num_of_steps == 2
    assert [e.type for e in run.events][-1] == "COMPLETE" and run.streaming_url == "https://stream.example/1"


async def test_a_dropped_stream_is_recovered_by_polling_the_run(settings, repo, tmp_path):
    polled = [
        SimpleNamespace(status="RUNNING"),
        SimpleNamespace(status="COMPLETED", result={"mandis": [9]}, error=None, streaming_url="https://s.example"),
    ]
    client = make(settings, repo, FakeSDK(fail_at=3, runs=polled), tmp_path)  # drops after the first PROGRESS
    run = await client.run_agent("https://x.example", "goal")
    assert run.status == "COMPLETED" and run.result == {"mandis": [9]} and run.run_id == "r1"
    assert repo.get_run("r1").status == "COMPLETED" and repo.get_run("r1").result == {"mandis": [9]}


async def test_a_polled_failure_is_reported_as_failed(settings, repo, tmp_path):
    failed = SimpleNamespace(
        status="FAILED", result=None, streaming_url=None,
        error=Dump({"category": "SYSTEM_FAILURE", "message": "infra"}),
    )
    client = make(settings, repo, FakeSDK(fail_at=2, runs=[failed]), tmp_path)
    run = await client.run_agent("u", "g")
    assert run.status == "FAILED" and run.error["category"] == "SYSTEM_FAILURE"


async def test_a_stream_that_fails_before_any_event_is_an_error_not_a_hang(settings, repo, tmp_path):
    client = make(settings, repo, FakeSDK(fail_start=True), tmp_path)
    with pytest.raises(WebClientError, match="failed to start"):
        await client.run_agent("u", "g")
    client = make(settings, repo, FakeSDK(events=[]), tmp_path)
    with pytest.raises(WebClientError, match="no events"):
        await client.run_agent("u", "g")


async def test_polling_gives_up_after_the_timeout(settings, repo, tmp_path):
    client = make(settings, repo, FakeSDK(fail_at=2, runs=[SimpleNamespace(status="RUNNING")]), tmp_path)
    client.poll_timeout = 0.05
    client.poll_interval = 0.01
    with pytest.raises(WebClientError, match="did not finish"):
        await client.run_agent("u", "g")


@pytest.mark.parametrize(
    "result",
    [{"note": "Please complete the CAPTCHA to continue"}, {"blocked": True}, {"page": "Access Denied by Cloudflare"}],
)
async def test_completed_but_blocked_is_a_failure(settings, repo, tmp_path, result):
    client = make(settings, repo, FakeSDK(events=good_events(result)), tmp_path)
    run = await client.run_agent("u", "g")
    assert run.status == "FAILED" and run.result is None and run.error["category"] == "AGENT_FAILURE"
    assert repo.get_run("r1").status == "FAILED"


def test_blocked_detection_has_no_false_positive_on_prices():
    assert not looks_blocked({"mandis": [{"mandi": "Meerut", "modal_price": 2403}]})
    assert not looks_blocked(None) and not looks_blocked({})


async def test_unknown_event_types_are_skipped(settings, repo, tmp_path):
    events = [ev("STARTED"), Dump({"type": "SOMETHING_NEW", "run_id": "r1"}), *good_events()[1:]]
    run = await make(settings, repo, FakeSDK(events=events), tmp_path).run_agent("u", "g")
    assert run.status == "COMPLETED" and "SOMETHING_NEW" not in {e.type for e in run.events}


async def test_at_most_two_agent_runs_at_once_and_the_rest_queue(settings, repo, tmp_path):
    sdk = FakeSDK(hold=0.02)
    client = make(settings, repo, sdk, tmp_path, runs=10)
    results = await asyncio.gather(*(client.run_agent("u", f"g{i}") for i in range(6)))
    assert len(results) == 6 and sdk.tracker["peak"] == 2


async def test_the_agent_budget_is_enforced_without_calling_tinyfish(settings, repo, tmp_path):
    sdk = FakeSDK()
    client = make(settings, repo, sdk, tmp_path, runs=1)
    await client.run_agent("u", "g")
    with pytest.raises(BudgetExceeded):
        await client.run_agent("u", "g2")
    assert len(sdk.calls["agent"]) == 1


async def test_record_mode_writes_a_fixture_that_replay_serves(settings, repo, tmp_path):
    settings.tinyfish_record = True
    settings.fixtures_dir = tmp_path / "fx"
    client = make(settings, repo, FakeSDK(), tmp_path)
    live = await client.run_agent("https://x.example", "my goal")
    await client.search("a query")
    files = sorted((tmp_path / "fx" / "tinyfish").glob("*.json"))
    assert len(files) == 2 and all(json.loads(f.read_text())["_label"].startswith("RECORDED") for f in files)
    replayed = await ReplayClient(tmp_path / "fx" / "tinyfish").run_agent("https://x.example", "my goal")
    assert replayed.result == live.result and replayed.streaming_url == live.streaming_url
    assert [e.type for e in replayed.events] == [e.type for e in live.events]


async def test_a_failed_run_is_not_recorded(settings, repo, tmp_path):
    settings.tinyfish_record = True
    settings.fixtures_dir = tmp_path / "fx"
    client = make(settings, repo, FakeSDK(events=good_events({"blocked": True})), tmp_path)
    await client.run_agent("u", "g")
    assert not list((tmp_path / "fx" / "tinyfish").glob("*.json"))


async def test_monitor_create_and_wallet(settings, repo, tmp_path):
    sdk = FakeSDK()
    client = make(settings, repo, sdk, tmp_path)
    out = await client.create_monitor("fetch", {"url": "https://x.example"}, "0 * * * *", "https://h.example/w",
                                       name="n", purpose="p")
    assert out["monitor"]["id"] == "m1"
    assert sdk.calls["monitor"][3]["webhook_url"] == "https://h.example/w"
    assert await client.wallet_balance() == 12.5


async def test_replay_writes_runs_too(settings, repo):
    client = ReplayClient(settings.tinyfish_fixtures_dir, repo=repo)
    a = await client.run_agent("https://agmarknet.gov.in/", "goal")
    b = await client.run_agent("https://agmarknet.gov.in/", "goal")
    assert a.run_id != b.run_id
    row = repo.get_run(a.run_id)
    assert row.mode == "replay" and row.status == "COMPLETED" and row.streaming_url and row.steps == 5
