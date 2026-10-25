"""Selling rules, page parsers and the Sell agent."""

from datetime import date

import pytest

from app import knowledge
from app.agents import sell
from app.agents.base import AgentContext
from app.models import Triage
from app.parsers import parse_agent_prices, parse_date, parse_price, parse_price_table
from app.rules import market
from app.rules.market import PriceRow
from app.tinyfish import ReplayClient

D = date(2026, 10, 22)


@pytest.fixture
def mandis(settings):
    return knowledge.market_config(settings).mandis_for("Meerut")


def test_market_config_uses_the_official_daily_report_url(settings):
    assert knowledge.market_config(settings).price_url == (
        "https://agmarknet.gov.in/daily-price-and-arrival-report"
    )


def rows(**prices):
    return [PriceRow(name.replace("_", " "), p, D, quote=f"{name} {p}") for name, p in prices.items()]


# --- pure rules -------------------------------------------------------------------------------------------------
def test_net_price_and_transport():
    assert market.transport_cost(70, 0.4) == 28.0
    assert market.net_price(2640, 70, 0.4) == 2612.0
    assert market.net_price(2540, 0, 0.4) == 2540.0


def test_a_far_dearer_mandi_beats_the_near_one_but_only_after_freight(mandis):
    opts, _ = market.build_options(rows(Meerut=2540, Hapur=2565, Baghpat=2560), mandis, 0.4)
    ranked = market.rank(opts)
    assert [o.mandi for o in ranked] == ["Hapur", "Meerut", "Baghpat"]
    # Baghpat pays more than Meerut at the gate (2560 v 2540) but loses once 50 km of freight is taken off.
    assert next(o for o in ranked if o.mandi == "Baghpat").net_price == 2540.0


def test_a_tie_goes_to_the_nearer_mandi(mandis):
    opts, _ = market.build_options(rows(Meerut=2540, Baghpat=2560), mandis, 0.4)
    assert [o.mandi for o in market.rank(opts)] == ["Meerut", "Baghpat"]


def test_market_names_match_aliases_and_unknown_markets_are_reported(mandis):
    opts, unmatched = market.build_options(
        [PriceRow("Azadpur", 2600), PriceRow("Hapur (UP)", 2500), PriceRow("Faraway Mandi", 2700)], mandis, 0.4
    )
    assert {o.mandi for o in opts} == {"Delhi (Azadpur)", "Hapur"} and unmatched == ["Faraway Mandi"]
    assert market.match_mandi("Muzaffarnagar", mandis).name == "Muzaffarnagar"
    assert market.match_mandi("Nowhere", mandis) is None


def test_two_rows_for_one_mandi_keep_the_newer(mandis):
    old, new = PriceRow("Hapur", 2000, date(2026, 10, 1)), PriceRow("Hapur", 2565, D)
    assert market.build_options([old, new], mandis, 0.4)[0][0].modal_price == 2565
    assert market.build_options([new, old], mandis, 0.4)[0][0].modal_price == 2565


def test_msp_comparison():
    above = market.msp_comparison(2640, 2585)
    assert above == {"msp_rs_per_qtl": 2585, "difference_rs": 55, "difference_pct": 2.1, "below_msp": False}
    assert market.msp_comparison(2400, 2585)["below_msp"] is True


def test_prices_far_from_msp_are_dropped_as_probable_unit_errors(mandis):
    opts, _ = market.build_options(rows(Meerut=25.4, Hapur=2565, Baghpat=99999), mandis, 0.4)
    kept, dropped = market.split_insane(opts, 2585, 0.6, 2.0)
    assert [o.mandi for o in kept] == ["Hapur"] and {o.mandi for o in dropped} == {"Meerut", "Baghpat"}
    assert market.split_insane(opts, None, 0.6, 2.0) == (opts, [])  # no MSP, nothing to check against


def test_staleness(mandis):
    opts, _ = market.build_options(
        [PriceRow("Hapur", 2565, date(2026, 10, 18)), PriceRow("Meerut", 2540, D), PriceRow("Baghpat", 2560)], mandis, 0.4
    )
    assert [o.mandi for o in market.stale_options(opts, D, 3)] == ["Hapur"]  # undated rows are not "stale"


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        (dict(), 0.91),                                  # typical: assumed freight rate only
        (dict(n_stale=1), 0.66),
        (dict(n_dropped=1), 0.81),
        (dict(n_dropped=5), 0.61),                       # the outlier penalty is capped
        (dict(n_options=2), 0.81),
        (dict(n_unknown_date=1), 0.86),
        (dict(rung="agent"), 0.88),
        (dict(has_msp=False), 0.86),
        (dict(n_options=0), 0.0),
    ],
)
def test_confidence(kw, expected):
    base = dict(n_options=6, n_dropped=0, n_stale=0, n_unknown_date=0, rate_assumed=True, rung="fetch",
                has_msp=True, min_mandis=3)
    assert market.confidence(**{**base, **kw}) == expected


def test_stale_data_or_outliers_fall_below_the_gate_but_normal_caveats_do_not():
    gate = 0.85
    base = dict(n_options=6, n_dropped=0, n_stale=0, n_unknown_date=0, rate_assumed=True, rung="agent",
                has_msp=True, min_mandis=3)
    assert market.confidence(**base) >= gate
    assert market.confidence(**{**base, "n_stale": 1}) < gate
    assert market.confidence(**{**base, "n_dropped": 1}) < gate
    assert market.confidence(**{**base, "n_options": 2}) < gate


def test_ledger_value_and_formula(mandis):
    opts, _ = market.build_options(rows(Meerut=2540, Delhi=2640), mandis, 0.4)
    best, near = market.rank(opts)[0], min(opts, key=lambda o: o.distance_km)
    assert market.ledger_value(best, near, 20) == 1440.0
    assert market.ledger_value(near, near, 20) == 0.0 and market.ledger_value(near, best, 20) == 0.0
    text = market.formula(best, near, 20, 0.4, True)
    assert "x 20 qtl = Rs 1440" in text and "assumption" in text


# --- parsers ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [("2026-10-22", date(2026, 10, 22)), ("22/10/2026", date(2026, 10, 22)), ("22-10-2026", date(2026, 10, 22)),
     ("22 Oct 2026", date(2026, 10, 22)), ("30 November 2026", date(2026, 11, 30)), ("soon", None),
     ("31/02/2026", None), ("", None)],
)
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


def test_parse_price():
    assert parse_price("Rs 2,540") == 2540.0 and parse_price("2540.50") == 2540.5
    assert parse_price("-") is None and parse_price("0") is None


TABLE = (
    "| Market | Commodity | Modal Price (Rs./Quintal) | Arrival Date |\n|---|---|---|---|\n"
    "| Meerut | Wheat | 2,540 | 22/10/2026 |\n| Hapur | Wheat | 2565 | 22/10/2026 |\n"
    "| Meerut | Paddy(Dhan)(Common) | 2300 | 22/10/2026 |\n| Hapur | Wheat | - | 22/10/2026 |\n"
)


def test_parse_price_table_filters_by_commodity_and_skips_bad_rows():
    parsed = parse_price_table(TABLE, "wheat")
    assert [(r.mandi, r.modal_price, r.arrival_date) for r in parsed] == [
        ("Meerut", 2540.0, date(2026, 10, 22)), ("Hapur", 2565.0, date(2026, 10, 22))]
    assert parse_price_table(TABLE, "rice")[0].modal_price == 2300.0
    assert parse_price_table(TABLE, "mustard") is None


def test_parse_price_table_needs_both_columns():
    assert parse_price_table("| Market | Notes |\n|---|---|\n| Meerut | x |", "wheat") is None
    assert parse_price_table("no table here", "wheat") is None
    no_commodity = "| Mandi | Modal |\n|---|---|\n| Meerut | 2500 |"
    assert parse_price_table(no_commodity, "wheat")[0].modal_price == 2500.0


def test_parse_agent_prices():
    got = parse_agent_prices({"mandis": [{"mandi": "A", "modal_price": "2,500", "arrival_date": "2026-10-22"},
                                         {"mandi": "", "modal_price": 1}, {"mandi": "B"}, "junk"]})
    assert [(r.mandi, r.modal_price) for r in got] == [("A", 2500.0)] and got[0].arrival_date == D
    assert parse_agent_prices({"mandis": []}) is None and parse_agent_prices({}) is None


# --- the Sell agent ---------------------------------------------------------------------------------------------
def ctx(settings, repo, web, **kw):
    farmer = repo.get_farmer("farmer_demo_1") if kw.pop("with_farmer", True) else None
    tri = Triage(text="sell", language="en", intent="sell", crop=kw.pop("crop", "wheat"),
                 quantity_qtl=kw.pop("quantity", 20.0))
    return AgentContext(triage=tri, farmer=farmer, repo=repo, web=web, settings=settings, **kw)


@pytest.fixture
def seeded(repo, settings):
    from app.seed import seed_demo

    seed_demo(repo, settings)
    return repo


async def test_sell_answers_from_the_page_with_a_source_per_price_line(settings, seeded):
    web = ReplayClient(settings.tinyfish_fixtures_dir, repo=seeded)
    r = await sell.run(ctx(settings, seeded, web))
    d = r.data
    assert d["rung"] == "fetch" and d["best"]["mandi"] == "Delhi (Azadpur)" and d["nearest"]["mandi"] == "Meerut"
    assert d["best"]["net_price"] == 2612.0 and d["gain_rs"] == d["ledger_value_rs"] == 1440.0
    assert [o["mandi"] for o in d["options"]][0] == "Delhi (Azadpur)" and len(d["options"]) == 6
    assert d["msp"]["price_rs_per_qtl"] == 2585 and d["msp"]["marketing_season"] == "2026-27"
    assert d["msp"]["below_msp"] is False and d["msp"]["quality"] == "official"
    assert any("not in this district" in w for w in d["warnings"])  # "Illustrative Other Mandi"
    assert any("Freight rate" in a for a in d["assumptions"]) and any("distances" in a for a in d["assumptions"])
    assert r.confidence == 0.91 and len(r.evidence) == 7
    assert all(e.kind == "replay" for e in r.evidence[:-1]) and r.evidence[-1].kind == "knowledge"
    assert r.evidence[1].title == "Muzaffarnagar modal price" and "2575" in r.evidence[1].quote


async def test_sell_escalates_to_the_agent_when_the_page_has_no_table(settings, seeded, tmp_path):
    import json

    empty = {"kind": "fetch", "default": True,
             "request": {"urls": ["https://agmarknet.gov.in/daily-price-and-arrival-report"]},
             "response": {"results": [{"url": "https://agmarknet.gov.in/daily-price-and-arrival-report",
                                       "text": "Select a state", "format": "markdown"}],
                          "errors": []}}
    fx = tmp_path / "fx"
    fx.mkdir()
    (fx / "fetch_empty.json").write_text(json.dumps(empty), encoding="utf-8")
    (fx / "agent_mandi.json").write_bytes((settings.tinyfish_fixtures_dir / "agent_mandi.json").read_bytes())
    r = await sell.run(ctx(settings, seeded, ReplayClient(fx, repo=seeded)))
    assert r.data["rung"] == "agent" and r.run_id and r.confidence == 0.88  # 0.91 less the agent-rung point
    assert seeded.get_run(r.run_id).streaming_url  # the viewer has something to show
    assert all(e.run_id == r.run_id for e in r.evidence[:-1])


async def test_sell_without_any_usable_data_has_no_evidence_so_the_gate_will_withhold(settings, seeded, tmp_path):
    r = await sell.run(ctx(settings, seeded, ReplayClient(tmp_path)))  # no fixtures at all
    assert r.evidence == [] and r.confidence == 0.0 and "expert" in r.answer_en


async def test_sell_flags_stale_prices_and_the_gate_withholds_them(settings, seeded, tmp_path):
    import json

    from app.orchestrator import respond

    page = json.loads((settings.tinyfish_fixtures_dir / "fetch_mandi.json").read_text(encoding="utf-8"))
    lines = page["response"]["results"][0]["text"].splitlines()
    # Only Azadpur keeps the 22 Oct date; every other row is from 10 Oct, so replay (which judges freshness
    # against the newest row) finds them 12 days old.
    page["response"]["results"][0]["text"] = "\n".join(
        line if "Azadpur" in line else line.replace("2026-10-22", "2026-10-10").replace("2026-10-21", "2026-10-10")
        for line in lines
    )
    fx = tmp_path / "fx"
    fx.mkdir()
    (fx / "fetch_mandi.json").write_text(json.dumps(page), encoding="utf-8")
    web = ReplayClient(fx, repo=seeded)
    direct = await sell.run(ctx(settings, seeded, web))
    assert any("older than 3 days" in w for w in direct.data["warnings"]) and direct.confidence == 0.66
    tri = Triage(text="sell", language="en", intent="sell", crop="wheat", quantity_qtl=20)
    out = await respond("sell", repo=seeded, web=web, settings=settings, farmer_id="farmer_demo_1", forced=tri)
    assert out.status == "escalated" and out.reasons == ["low_confidence"] and out.data == {}


async def test_sell_drops_an_implausible_price_and_escalates(settings, seeded, tmp_path):
    import json

    page = json.loads((settings.tinyfish_fixtures_dir / "fetch_mandi.json").read_text(encoding="utf-8"))
    text = page["response"]["results"][0]["text"].replace("| Hapur | Wheat | 2565 |", "| Hapur | Wheat | 25.65 |")
    page["response"]["results"][0]["text"] = text
    fx = tmp_path / "fx"
    fx.mkdir()
    (fx / "fetch_mandi.json").write_text(json.dumps(page), encoding="utf-8")
    r = await sell.run(ctx(settings, seeded, ReplayClient(fx, repo=seeded)))
    assert "Hapur" not in {o["mandi"] for o in r.data["options"]}
    assert any("unit errors" in w and "Hapur" in w for w in r.data["warnings"])
    assert r.confidence == 0.81  # below the gate: the answer would be handed to a person


async def test_sell_for_a_crop_without_an_msp_says_so_and_never_invents_one(settings, seeded):
    r = await sell.run(ctx(settings, seeded, ReplayClient(settings.tinyfish_fixtures_dir), crop="rice"))
    assert r.data["msp"]["price_rs_per_qtl"] is None and "No researched MSP" in r.data["msp"]["note"]
    assert not any(e.kind == "knowledge" for e in r.evidence)


async def test_sell_for_an_unknown_district_has_no_mandi_list(settings, seeded):
    farmer = seeded.get_farmer("farmer_demo_1").model_copy(update={"district": "Atlantis"})
    seeded.upsert_farmer(farmer)
    r = await sell.run(ctx(settings, seeded, ReplayClient(settings.tinyfish_fixtures_dir)))
    assert r.evidence == [] and r.confidence == 0.0


async def test_sell_assumes_a_quantity_only_when_none_is_given_and_says_so(settings, seeded):
    web = ReplayClient(settings.tinyfish_fixtures_dir)
    r = await sell.run(ctx(settings, seeded, web, quantity=None))
    assert r.data["quantity_qtl"] == 10.0
    assert any("assumed 10 quintal" in a for a in r.data["assumptions"])


def test_the_msp_for_the_season_on_sale_now_is_preferred(settings):
    wheat = knowledge.msp_for(settings, "wheat")
    assert wheat.price_rs_per_qtl == 2585 and wheat.quality == "official" and "pib.gov.in" in wheat.source_url
    assert knowledge.msp_for(settings, "rice") is None
