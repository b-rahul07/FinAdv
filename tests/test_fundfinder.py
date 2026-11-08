"""Fund finder: real schemes per fund type, facts from code, neutral order, never fed to the model or the plan."""

from datetime import date, timedelta

import pytest

from finadvisor.advisor import fundfinder
from finadvisor.advisor.pipeline import Advisor
from finadvisor.calc.returns import annualised_return, nav_on_or_before
from finadvisor.db.base import utcnow
from finadvisor.llm.fake import FakeLLM
from finadvisor.market import fundfinder as job
from finadvisor.market.parse import Scheme
from test_pipeline import consistent_planner, run_turn

TODAY = date(2026, 11, 6)


def daily(start: date, end: date, f):
    d, out = start, []
    while d <= end:
        if d.weekday() < 5:
            out.append((d, f(d)))
        d += timedelta(days=1)
    return out


def test_annualised_return_is_point_to_point_cagr():
    end = date(2026, 11, 6)
    navs = daily(date(2020, 11, 2), end, lambda d: 10 * 1.1 ** ((d - date(2020, 11, 6)).days / 365.25))
    assert annualised_return(navs, 1) == pytest.approx(0.10, abs=0.002)
    assert annualised_return(navs, 5) == pytest.approx(0.10, abs=0.002)
    assert annualised_return(navs[-300:], 3) is None            # younger than 3 years
    assert annualised_return([], 1) is None


def test_a_gap_at_the_start_date_means_no_return():
    navs = [(date(2025, 10, 20), 10.0), (date(2026, 11, 6), 12.0)]
    assert nav_on_or_before(navs, date(2025, 11, 6)) is None        # nearest NAV is 17 days earlier
    assert annualised_return(navs, 1) is None
    assert nav_on_or_before([(date(2025, 11, 3), 10.0)], date(2025, 11, 6)) == (date(2025, 11, 3), 10.0)


def sc(name, category, plan="Direct", option="Growth", nav_date=TODAY, code=None):
    return Scheme(code or name, None, None, name, "Some MF", category, plan, option, 10.0, nav_date)


def test_pick_keeps_fresh_direct_growth_schemes_of_each_type():
    cfg = fundfinder.load_config()
    schemes = [
        sc("A Nifty 50 Index Fund", "Index Funds - Equity Funds"),
        sc("B Nifty Next 50 Index Fund", "Index Funds - Equity Funds"),
        sc("C Nifty 50 Equal Weight Index Fund", "Other Scheme - Index Funds"),
        sc("D Nifty 50 Index Fund", "Index Funds - Equity Funds", plan="Regular"),
        sc("E Nifty 50 Index Fund", "Index Funds - Equity Funds", option="IDCW"),
        sc("F Nifty 50 Index Fund", "Index Funds - Equity Funds", nav_date=TODAY - timedelta(days=40)),
        sc("G Flexi Cap Fund", "Equity Schemes - Flexi Cap Fund", option="GROWTH"),
        sc("H Short Duration Fund", "Debt Scheme - Short Duration Fund"),
        sc("I Ultra Short Duration Fund", "Debt Scheme - Ultra Short Duration Fund"),
        sc("J Large & Mid Cap Fund", "Equity Scheme - Large & Mid Cap Fund"),
        sc("K Mid Cap Fund", "Equity Scheme - Mid Cap Fund"),
        sc("L Gold Savings Fund", "Other Scheme - FoF Domestic"),
        sc("M Silver ETF FoF", "Other Scheme - FoF Domestic"),
    ]
    got = {pid: [s.name[0] for s in v] for pid, v in job.pick(schemes, cfg, TODAY).items()}
    assert got["large_cap_index_fund"] == ["A"]
    assert got["flexi_cap_fund"] == ["G"]
    assert got["short_duration_debt_fund"] == ["H"]
    assert got["mid_small_cap_fund"] == ["K"]
    assert got["gold_etf_fund"] == ["L"]


def test_ter_keeps_the_latest_day_per_scheme(monkeypatch):
    pages = {
        1: {"meta": {"pageCount": 2}, "data": [{"Scheme_Name": "HDFC Flexi Cap Fund", "D_TER": "0.80", "TER_Date": "2026-11-02T00:00:00.000Z"}]},
        2: {"meta": {"pageCount": 2}, "data": [{"Scheme_Name": "HDFC Flexi-Cap  Fund", "D_TER": "0.74", "R_TER": "1.40",
                                                "TER_Date": "2026-11-05T00:00:00.000Z"},
                                               {"Scheme_Name": "Bad row", "D_TER": None, "TER_Date": "2026-11-05"}]},
    }

    def fake(url, params=None, headers=None):
        if "month" in url:
            return [{"MonthYear": "November-2026", "MonthNumber": "11-2026"}]
        assert params["Month"] == "11-2026" and params["MF_ID"] == "All"
        return pages[params["page"]]

    monkeypatch.setattr(job.sources, "get_json", fake)
    month, ter = job.fetch_ter(TODAY)
    assert month == "November-2026"
    assert ter[fundfinder.norm("HDFC FLEXI CAP FUND")] == {"direct": 0.74, "regular": 1.40, "date": "2026-11-05"}
    assert len(ter) == 1


def snapshot(n=12):
    funds = [{"code": str(100 + i), "name": f"Fund {i} Nifty 50 Index Fund", "amc": "X MF", "category": "Index Funds",
              "nav": 20.0 + i, "nav_date": "2026-11-05", "expense_ratio": 0.1 + i / 100, "expense_ratio_date": "2026-11-05",
              "since": "2015-01-01", "returns": {"1y": 0.08, "3y": 0.12, "5y": None}} for i in range(n)]
    return {"version": "fundfinder-v1", "built_at": utcnow().isoformat(),
            "sources": {"nav": "AMFI daily NAV, as of 05 Nov 2026", "expense_ratio": "AMFI TER, November-2026", "returns": "x"},
            "products": {"large_cap_index_fund": {"label": "Nifty 50 index funds", "total": n, "funds": funds},
                         "flexi_cap_fund": {"label": "Flexi-cap funds", "total": 0, "funds": []}}}


def test_card_lists_the_first_rows_with_checklist_links_and_sources():
    c = fundfinder.card("large_cap_index_fund", snapshot())
    assert c["type"] == "fund_finder" and c["total"] == 12 and len(c["funds"]) == 8
    assert c["funds"][0]["code"] == "100"
    assert any("same 50 companies" in x for x in c["checklist"]) and any("Direct plan" in x for x in c["checklist"])
    assert all(link["url"].startswith("https://www.amfiindia.com/") for link in c["links"])
    assert "not a recommendation" in c["note"] and not c["stale"]
    assert fundfinder.card("flexi_cap_fund", snapshot()) is None          # no schemes: no card
    assert fundfinder.card("ppf", snapshot()) is None                     # not a mutual fund
    assert fundfinder.cards_for(["large_cap_index_fund"], None) == []


def test_reader_reloads_when_the_job_replaces_the_file(tmp_path):
    import json
    p = tmp_path / "ff.json"
    r = fundfinder.FundFinder(p)
    assert r() is None
    p.write_text(json.dumps({"v": 1}))
    assert r() == {"v": 1}


def every_type():
    snap = snapshot()
    one = snap["products"]["large_cap_index_fund"]
    snap["products"] = {pid: {**one, "label": rule["label"]} for pid, rule in fundfinder.load_config()["products"].items()}
    return snap


def test_plan_answer_shows_fund_lists_and_never_gives_them_to_the_model(website_bundle, healthy):
    prompts = []
    llm = FakeLLM(consistent_planner, text_fn=lambda s, p, purpose: prompts.append(p) or "")
    out, _ = run_turn(Advisor(website_bundle, llm, funds=every_type), healthy, "Which mutual funds suit me?")
    in_plan = {m["product_id"] for b in out.advice["plan"]["buckets"] for m in b["mix"]}
    funds_in_plan = in_plan & set(fundfinder.load_config()["products"])
    assert funds_in_plan, "the healthy profile's plan should include mutual funds"
    ff = [c for c in out.cards if c["type"] == "fund_finder"]
    assert {c["product_id"] for c in ff} == funds_in_plan
    assert all(c["show"] == "main" for c in ff)
    monthly = {}
    for b in out.advice["plan"]["buckets"]:
        for m in b["mix"]:
            monthly[m["product_id"]] = monthly.get(m["product_id"], 0) + m["monthly"]
    amounts = [monthly[c["product_id"]] for c in ff]
    assert amounts == sorted(amounts, reverse=True)        # same order as the reply names them
    assert "lists its actual funds" in out.text
    assert set(out.advice["fund_finder"]["shown"]) == funds_in_plan
    assert prompts and not any("Fund 0" in p or "X MF" in p for p in prompts)


def test_fund_lists_sit_in_details_for_other_questions(website_bundle, healthy):
    out, _ = run_turn(Advisor(website_bundle, FakeLLM(consistent_planner, text_fn=lambda s, p, purpose: ""),
                              funds=every_type), healthy, "Make me a money plan")
    ff = [c for c in out.cards if c["type"] == "fund_finder"]
    assert ff and all(c["show"] == "details" for c in ff)


def test_without_a_snapshot_the_answer_keeps_the_fund_type_wording(website_bundle, healthy):
    out, _ = run_turn(Advisor(website_bundle, FakeLLM(consistent_planner, text_fn=lambda s, p, purpose: "")), healthy,
                      "Which mutual funds suit me?")
    assert not any(c["type"] == "fund_finder" for c in out.cards)
    assert "not specific schemes or fund houses" in out.text and out.advice["fund_finder"] is None
