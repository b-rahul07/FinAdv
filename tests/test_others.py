"""Other assets, liabilities, insurance: net worth = assets − liabilities; profile proposal needs confirmation."""

from datetime import date, timedelta

import pytest

from finadvisor.api import runtime as rt_mod
from finadvisor.calc.deposits import fd_value
from finadvisor.db.models import Instrument, PriceDaily
from finadvisor.market import jobs, parse
from finadvisor.portfolio.others import GOLD_REF_KEY, GOLD_REF_SOURCE, gold_reference_from_bhav
from test_api import client, login  # noqa: F401

TODAY = jobs.today_ist()


def seed_gold(rate=7500.0):
    with rt_mod.get_runtime().Session() as s:
        g = Instrument(kind="index", key=GOLD_REF_KEY, name="Gold reference", tracked=True)
        s.add_all([g, Instrument(kind="index", key="NIFTY 50", name="Nifty 50", tracked=True)])
        s.flush()
        s.add(PriceDaily(instrument_id=g.id, date=TODAY - timedelta(days=1), close=rate, source=GOLD_REF_SOURCE))
        s.commit()


def test_net_worth_and_valuations(client):
    seed_gold()
    h = login(client)
    start = (TODAY - timedelta(days=365)).isoformat()
    mat = (TODAY + timedelta(days=365)).isoformat()
    client.post("/api/others/assets", json={"kind": "fd", "name": "SBI FD", "account_last4": "12345678901",
                                            "data": {"principal": 100000, "rate_pa": 7, "start": start, "maturity": mat}}, headers=h)
    client.post("/api/others/assets", json={"kind": "savings", "name": "HDFC savings", "data": {"balance": 50000, "as_of": TODAY.isoformat()}}, headers=h)
    client.post("/api/others/assets", json={"kind": "gold_physical", "name": "Chain", "data": {"grams": 10, "purity": 916}}, headers=h)
    client.post("/api/others/assets", json={"kind": "property", "name": "Flat", "data": {"balance": 4000000}}, headers=h)
    client.post("/api/others/liabilities", json={"kind": "home", "lender": "HDFC", "outstanding": 2500000, "rate_pa": 8.5, "emi_monthly": 25000,
                                                 "account_last4": "LN-0099887766"}, headers=h)
    client.post("/api/others/insurance", json={"kind": "term", "sum_assured": 10000000}, headers=h)
    client.post("/api/others/insurance", json={"kind": "health", "sum_assured": 500000}, headers=h)
    client.post("/api/others/insurance", json={"kind": "health", "sum_assured": 300000, "employer_provided": True}, headers=h)
    o = client.get("/api/others", headers=h).json()
    fd = next(a for a in o["assets"] if a["kind"] == "fd")
    assert fd["value"] == pytest.approx(fd_value(100000, 7, date.fromisoformat(start), TODAY, date.fromisoformat(mat)))
    assert fd["account_last4"] == "8901" and "12345678901" not in str(o)
    gold = next(a for a in o["assets"] if a["kind"] == "gold_physical")
    assert gold["value"] == pytest.approx(10 * 916 / 999 * 7500) and "Sovereign Gold Bonds" in gold["source"]
    assert next(a for a in o["assets"] if a["kind"] == "property")["self_reported"]
    assert o["liabilities"][0]["account_last4"] == "7766"
    dash = client.get("/api/dashboard", headers=h).json()
    assets = sum(a["value"] for a in o["assets"])
    assert dash["net_worth"]["value"] == pytest.approx(assets - 2500000)
    assert dash["net_worth"]["self_reported"] == pytest.approx(4000000)
    assert {a["asset_class"] for a in dash["allocation"]} == {"deposits", "cash", "gold", "other"}
    # proposal: emergency savings = savings + FD; covers from policies (employer health excluded); loans
    prop = client.get("/api/profile/proposal", headers=h).json()
    assert prop["proposed"]["liquid_savings"] == pytest.approx(50000 + fd["value"], abs=0.01)
    assert prop["proposed"]["life_cover"] == 10000000 and prop["proposed"]["health_cover"] == 500000
    assert prop["proposed"]["debts"][0]["emi_monthly"] == 25000
    assert set(prop["changed"]) >= {"liquid_savings", "life_cover", "health_cover", "debts"}
    assert client.get("/api/profile", headers=h).json()["version"] is None   # nothing applied without confirmation


def test_gold_reference_from_bhav_rows():
    mk = lambda c, v: parse.BhavRow("NSE", TODAY, "SGBX", "IN0", "GB", "SGB", None, None, None, c, None, v, "STK")
    assert gold_reference_from_bhav([mk(7400, 10), mk(7500, 5), mk(7600, 3), mk(9999, 0)]) == 7500
    assert gold_reference_from_bhav([mk(7400, 10)]) is None
