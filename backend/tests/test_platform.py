"""Ladder, replies (and the LLM guard), ledger, scripts, and the CLAUDE.md section 2 audit as tests."""

import json
import re
from pathlib import Path

import httpx
import pytest
from test_live_client import FakeSDK

from app import ladder, ledger, replies
from app.safety.dose import contains_dose
from app.scripts import create_monitors
from app.tinyfish import (
    AgentRunResult,
    BudgetExceeded,
    BudgetGuard,
    DiskCache,
    FetchedPage,
    FetchResponse,
    TinyFishClient,
    WebClientError,
)


# --- ladder -----------------------------------------------------------------------------------------------------
class ScriptedWeb:
    """A WebClient whose behaviour each test sets."""

    def __init__(self, mode="live", pages=None, fetch_error=None, run=None):
        self.mode, self.pages, self.fetch_error, self.run = mode, pages or [], fetch_error, run
        self.calls = []

    async def search(self, *a, **k):
        raise AssertionError("not used")

    async def fetch(self, urls, *, purpose=None, fresh=False):
        self.calls.append(("fetch", fresh))
        if self.fetch_error:
            raise self.fetch_error
        return FetchResponse(results=self.pages)

    async def run_agent(self, url, goal, output_schema=None, *, on_event=None):
        self.calls.append(("agent", goal))
        return self.run


def page(text="a table", url="https://x.example/"):
    return FetchedPage(url=url, text=text)


def agent_run(status="COMPLETED", result=None, run_id="r1"):
    return AgentRunResult(run_id=run_id, status=status, result=result)


async def climb(web, **kw):
    return await ladder.fetch_then_agent(
        web, url="https://x.example/", parse_page=kw.get("parse_page", lambda p: p.text if p.text == "ok" else None),
        goal="g", output_schema={}, parse_agent=kw.get("parse_agent", lambda r: r.get("v")), fresh=True,
    )


async def test_the_cheap_rung_answers_when_it_can():
    web = ScriptedWeb(pages=[page("ok")])
    got = await climb(web)
    assert got.rung == "fetch" and got.data == "ok" and got.kind == "fetch" and got.run_id is None
    assert web.calls == [("fetch", True)]  # the agent was never started


async def test_the_agent_rung_runs_only_when_the_page_cannot_be_parsed():
    web = ScriptedWeb(pages=[page("no table")], run=agent_run(result={"v": 42}))
    got = await climb(web)
    assert got.rung == "agent" and got.data == 42 and got.run_id == "r1" and got.kind == "agent"
    assert [c[0] for c in web.calls] == ["fetch", "agent"]


async def test_a_failed_fetch_escalates_but_an_exhausted_budget_does_not():
    web = ScriptedWeb(fetch_error=WebClientError("503"), run=agent_run(result={"v": 1}))
    assert (await climb(web)).rung == "agent"
    broke = ScriptedWeb(fetch_error=BudgetExceeded("spent"), run=agent_run(result={"v": 1}))
    with pytest.raises(BudgetExceeded):
        await climb(broke)
    assert [c[0] for c in broke.calls] == ["fetch"]  # no agent run is started after the budget says stop


@pytest.mark.parametrize(
    "run",
    [agent_run("FAILED"), agent_run("CANCELLED", result={"v": 1}), agent_run(result=None), agent_run(result={"x": 1})],
)
async def test_nothing_comes_back_when_the_agent_cannot_help(run):
    assert await climb(ScriptedWeb(pages=[], run=run)) is None


async def test_a_page_with_no_text_is_skipped():
    web = ScriptedWeb(pages=[FetchedPage(url="https://x.example/", text=None), page("ok")])
    assert (await climb(web)).data == "ok"


async def test_replay_answers_are_labelled_replay_never_live():
    got = await climb(ScriptedWeb(mode="replay", pages=[page("ok")]))
    assert got.kind == "replay" and got.evidence(title="t", quote="q").kind == "replay"
    ev = got.evidence(title="t", quote="q")
    assert (ev.title, ev.quote, ev.source_url) == ("t", "q", "https://x.example/")


# --- replies ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("n", "text"),
    [(0, "₹0"), (950, "₹950"), (1000, "₹1,000"), (2612, "₹2,612"), (12345, "₹12,345"), (100000, "₹1,00,000"),
     (1234567, "₹12,34,567"), (2612.4, "₹2,612"), (-1500, "-₹1,500")],
)
def test_rupees_use_indian_grouping(n, text):
    assert replies.rupees(n) == text


BEST = {"mandi": "Delhi (Azadpur)", "net_price": 2612.0}
NEAR = {"mandi": "Meerut", "net_price": 2540.0}
MSP = {"price_rs_per_qtl": 2585, "marketing_season": "2026-27"}


def test_sell_replies_carry_the_numbers_in_both_languages():
    en, hi = replies.sell("wheat", 20, BEST, NEAR, 1440, MSP)
    assert "Delhi (Azadpur)" in en and "₹2,612" in en and "₹1,440" in en and "₹2,585" in en and "2026-27" in en
    assert "गेहूं" in hi and "₹1,440" in hi and "₹2,585" in hi
    own_en, own_hi = replies.sell("wheat", 20, NEAR, NEAR, 0, None)
    assert "already pays the best price" in own_en and "₹2,540" in own_en and "MSP" not in own_en
    assert "सबसे अच्छा भाव" in own_hi


def test_no_reply_template_ever_states_a_dose():
    texts = [*replies.sell("wheat", 20, BEST, NEAR, 1440, MSP), *replies.sell("rice", 5.5, NEAR, NEAR, 0, None),
             *replies.subsidy(["PM-KISAN", "PMFBY", "KCC"], 2, 1, False), *replies.subsidy([], 0, 0, False),
             *replies.subsidy([], 0, 0, True), *replies.claim("hail", "claim_1", "2026-10-26", True, 2),
             *replies.claim("flood", "claim_1", None, False, 0), *replies.alert("hail", "Meerut"),
             *replies.alert("scheme", "Meerut"), *replies.no_data("mandi price", "मंडी भाव"), *replies.MENU.values()]
    assert len(texts) > 20 and not [t for t in texts if contains_dose(t)]


def test_subsidy_and_claim_replies():
    en, hi = replies.subsidy(["A", "B", "C", "D"], 2, 1, False)
    assert "4 scheme(s): A, B, C." in en and "2 of them need a document" in en and "nothing is submitted for you" in en
    assert "नहीं होता" in hi
    en, _ = replies.claim("hail", "claim_1", "2026-10-26", True, 1)
    assert "claim_1" in en and "supports your claim" in en and "by 2026-10-26" in en and "submit it yourself" in en


def test_the_menu_exists_in_every_language():
    assert set(replies.MENU) == {"en", "hi", "hinglish"} and all(replies.MENU.values())


@pytest.fixture
def llm_settings(settings):
    return settings.model_copy(update={"llm_phrasing": True, "anthropic_api_key": "sk-test"})


def llm(reply_text, status=200, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(status, json={"content": [{"type": "text", "text": reply_text}]})

    return httpx.MockTransport(handler)


ORIGINAL = "Sell 20 quintal wheat at Delhi (Azadpur) for about ₹2,612 per quintal. That is ₹1,440 more."


async def test_the_llm_is_off_by_default(settings):
    assert await replies.polish(ORIGINAL, settings, transport=llm("SHOULD NOT BE USED")) == ORIGINAL


async def test_the_llm_needs_a_key_as_well_as_the_flag(settings):
    on_no_key = settings.model_copy(update={"llm_phrasing": True})
    assert await replies.polish(ORIGINAL, on_no_key, transport=llm("x")) == ORIGINAL


async def test_a_faithful_rewrite_is_used_and_the_model_sees_only_the_template(llm_settings):
    seen: list = []
    friendly = "Please sell your 20 quintal wheat at Delhi (Azadpur): about ₹2,612 per quintal, ₹1,440 more."
    out = await replies.polish(ORIGINAL, llm_settings, transport=llm(friendly, seen=seen))
    assert out == friendly
    assert seen[0]["messages"] == [{"role": "user", "content": ORIGINAL}]  # nothing but the finished text
    assert seen[0]["model"] == "claude-haiku-5-5" and "Add no new facts" in seen[0]["system"]


@pytest.mark.parametrize(
    "bad",
    [
        "Sell 20 quintal wheat at Delhi for about ₹2,712 per quintal. That is ₹1,440 more.",          # changed number
        "Sell 20 quintal wheat for about ₹2,612 per quintal.",                                          # dropped a number
        ORIGINAL + " Also spray 2 ml per litre of pesticide.",                                          # added a dose
        ORIGINAL + " Also buy 5 bags of seed.",                                                         # added a number
        "",                                                                                             # empty
        ORIGINAL * 6,                                                                                   # runaway length
    ],
)
async def test_an_unfaithful_rewrite_is_discarded(llm_settings, bad):
    assert await replies.polish(ORIGINAL, llm_settings, transport=llm(bad)) == ORIGINAL


async def test_a_failing_llm_never_breaks_a_reply(llm_settings):
    assert await replies.polish(ORIGINAL, llm_settings, transport=llm("x", status=500)) == ORIGINAL

    def broken(request):
        raise httpx.ConnectError("down")

    assert await replies.polish(ORIGINAL, llm_settings, transport=httpx.MockTransport(broken)) == ORIGINAL


def test_acceptable_rewrite_compares_numbers_not_formatting():
    assert replies.acceptable_rewrite("Rs 2,612 and 20", "about 2612 and 20 qtl")
    assert not replies.acceptable_rewrite("Rs 2,612", "Rs 2,613")
    assert replies.numbers("1,000 and 2.5 and 1,000") == {"1000": 2, "2.5": 1}


# --- ledger -----------------------------------------------------------------------------------------------------
def test_projecting_the_same_value_twice_refreshes_one_entry(repo):
    a = ledger.project(repo, "f1", "sell", 1000, "formula A")
    b = ledger.project(repo, "f1", "sell", 1200, "formula A")
    assert a.id == b.id and len(repo.list_ledger("f1")) == 1 and repo.list_ledger("f1")[0].amount_rs == 1200


def test_a_different_formula_or_farmer_or_kind_is_a_new_entry(repo):
    ledger.project(repo, "f1", "sell", 1000, "A")
    ledger.project(repo, "f1", "sell", 1000, "B")
    ledger.project(repo, "f2", "sell", 1000, "A")
    ledger.project(repo, "f1", "subsidy", 1000, "A")
    assert len(repo.list_ledger()) == 4


def test_a_confirmed_entry_is_never_changed_by_a_later_projection(repo):
    first = ledger.project(repo, "f1", "sell", 1000, "A")
    repo.confirm_ledger(first.id)
    again = ledger.project(repo, "f1", "sell", 1500, "A")
    assert again.id != first.id and again.confirmed is False
    summary = ledger.summary(repo, "f1")
    assert (summary.total_rs, summary.projected_rs) == (1000, 1500)


@pytest.mark.parametrize("amount", [0, -5])
def test_nothing_is_recorded_for_zero_or_negative_value(repo, amount):
    assert ledger.project(repo, "f1", "sell", amount, "A") is None and repo.list_ledger() == []


# --- scripts ----------------------------------------------------------------------------------------------------
def test_monitor_specs_use_the_sourced_imd_url_and_the_demo_state(settings):
    settings.public_base_url = "https://khet.example.com/"
    settings.tinyfish_webhook_token = "SECRETVALUE"
    imd, search = create_monitors.build_specs(settings)
    assert imd["type"] == "fetch" and imd["config"]["url"] == "https://mausam.imd.gov.in/"
    assert search["type"] == "search" and "Uttar Pradesh" in search["config"]["query"]
    assert imd["webhook_url"] == "https://khet.example.com/webhooks/tinyfish?token=SECRETVALUE"
    shown = create_monitors.redact(imd["webhook_url"])
    assert "SECRETVALUE" not in shown and shown.endswith("token=***")


def test_apply_is_refused_until_it_could_actually_work(settings):
    assert len(create_monitors.problems(settings)) == 3  # replay mode, no https URL, no token
    live = settings.model_copy(update={"tinyfish_mode": "live", "tinyfish_api_key": "k",
                                       "public_base_url": "https://h.example", "tinyfish_webhook_token": "t"})
    assert create_monitors.problems(live) == []
    http_only = live.model_copy(update={"public_base_url": "http://h.example"})
    assert any("https" in p for p in create_monitors.problems(http_only))


def test_the_dry_run_creates_nothing_and_hides_the_token(settings, monkeypatch, capsys):
    settings.public_base_url, settings.tinyfish_webhook_token = "https://h.example", "SECRETVALUE"
    monkeypatch.setattr(create_monitors, "get_settings", lambda: settings)
    assert create_monitors.main([]) == 0
    out = capsys.readouterr().out
    assert "dry run" in out and "SECRETVALUE" not in out and "token=***" in out
    assert create_monitors.main(["--apply"]) == 2  # replay mode: refused, and says why
    assert "cannot apply" in capsys.readouterr().err


async def test_apply_creates_each_monitor_through_the_client(settings, repo, tmp_path):
    settings.public_base_url, settings.tinyfish_webhook_token = "https://h.example", "t"
    sdk = FakeSDK()
    live = settings.model_copy(update={"tinyfish_mode": "live", "tinyfish_api_key": "k"})
    client = TinyFishClient(live, BudgetGuard(1, 5), DiskCache(tmp_path, 60), repo, sdk)
    created = await create_monitors.apply(create_monitors.build_specs(settings), client)
    assert len(created) == 2 and sdk.calls["monitor"][0] == "search"  # the last one created
    assert sdk.calls["monitor"][3]["webhook_url"] == "https://h.example/webhooks/tinyfish?token=t"
    assert client.budget.free_calls == 2


async def test_smoke_live_refuses_without_a_key(monkeypatch, settings, capsys):
    from app.scripts import smoke_live

    monkeypatch.setattr(smoke_live, "get_settings", lambda: settings)
    assert await smoke_live.run() == 2 and "TINYFISH_API_KEY" in capsys.readouterr().out


# --- the CLAUDE.md section 2 audit, kept as tests ---------------------------------------------------------------
APP = Path(__file__).resolve().parent.parent / "app"
SOURCES = [p for p in APP.rglob("*") if p.suffix in {".py", ".j2"}]
ALLOWED_HOSTS = {
    "api.anthropic.com",  # the guarded rewrite (replies.polish)
    "api.twilio.com",  # WhatsApp send and media
    "meity-auth.ulcacontrib.org",  # Bhashini speech to text (voice notes)
    "mausam.imd.gov.in", "agmarknet.gov.in",  # sources named in comments and goals
    "eparlib.nic.in", "pib.gov.in", "services.india.gov.in",
    "www.myscheme.gov.in",  # a stub's source link
    "localhost",  # the default CORS origin for the dev web app
    "example.com",  # the page the live smoke test reads
}
# Twilio, Bhashini, the guarded LLM call, Supabase. Never a government portal.
ALLOWED_POST_FILES = {"channels/twilio.py", "channels/voice.py", "replies.py", "db.py"}


def hosts_in(text: str) -> set[str]:
    return {m.group(1).lower() for m in re.finditer(r"https?://([A-Za-z0-9.-]+)", text)}


def test_code_only_names_hosts_we_expect():
    unexpected = {}
    for path in SOURCES:
        extra = hosts_in(path.read_text(encoding="utf-8")) - ALLOWED_HOSTS
        if extra:
            unexpected[str(path.relative_to(APP))] = sorted(extra)
    assert unexpected == {}, "a new outbound host needs a line in ALLOWED_HOSTS and a reason"


def test_nothing_posts_to_an_external_portal():
    """KhetKaaj never submits anything: the only POSTs are to Twilio, the LLM rewrite and our own database."""
    posters = {
        str(p.relative_to(APP)).replace("\\", "/")
        for p in SOURCES
        if p.suffix == ".py"
        and re.search(r"(?<!router)\.post\(|(httpx|client)\.(put|patch|delete)\(", p.read_text(encoding="utf-8"))
    }
    assert posters <= ALLOWED_POST_FILES, posters - ALLOWED_POST_FILES


def test_no_researched_price_or_date_is_hardcoded_in_code():
    """The MSP figures and every deadline live in knowledge/*.yaml next to their source, never in code."""
    researched = {"2585", "2610", "2425", "6200", "5875", "6000", "2150", "7000"}
    API_VERSIONS = {"2023-06-01", "2010-04-01"}  # the Anthropic and Twilio API versions, not facts about farming
    iso_date = re.compile(r"(?<![\d-])20\d\d-\d\d-\d\d(?![\d-])")
    offenders = []
    for path in SOURCES:
        rel = str(path.relative_to(APP)).replace("\\", "/")
        if rel == "agents/stubs.py" or path.suffix == ".j2":  # stubs are labelled placeholders
            continue
        text = path.read_text(encoding="utf-8")
        offenders += [(rel, n) for n in researched if re.search(rf"(?<![\d.]){n}(?![\d.])", text)]
        offenders += [(rel, d) for d in iso_date.findall(text) if d not in API_VERSIONS]
    assert offenders == [], offenders


def test_only_the_rewrite_module_can_talk_to_a_model():
    users = {str(p.relative_to(APP)).replace("\\", "/") for p in SOURCES
             if p.suffix == ".py" and "anthropic" in p.read_text(encoding="utf-8").lower()}
    assert users == {"config.py", "replies.py"}


def test_stub_agents_are_labelled_so_they_cannot_pass_for_data():
    from app.agents import stubs

    for result in (stubs.sell("wheat", 10), stubs.subsidy("wheat"), stubs.claim("wheat"), stubs.watch()):
        assert result.data["stub"] is True and all(e.assumed for e in result.evidence)


def test_every_fixture_says_what_it_is():
    fixtures = Path(__file__).resolve().parent.parent / "fixtures" / "tinyfish"
    for path in fixtures.glob("*.json"):
        label = json.loads(path.read_text(encoding="utf-8")).get("_label", "")
        assert label.startswith(("ILLUSTRATIVE", "RECORDED")), path.name
