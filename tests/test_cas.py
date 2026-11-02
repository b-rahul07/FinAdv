"""CAS import with casparser-shaped data (no real statement in the repo). PDFs and passwords are never stored."""

import json
from datetime import date, timedelta

import pytest

from finadvisor import cas
from finadvisor.api import runtime as rt_mod
from finadvisor.db.models import CasUpload, Instrument
from test_api import client, login  # noqa: F401

D0 = date.today() - timedelta(days=400)

CAMS = {
    "file_type": "FileType.CAMS", "cas_type": "CASFileType.DETAILED",
    "statement_period": {"from": "01-Apr-2025", "to": "30-Sep-2026"},
    "investor_info": {"name": "ASHA RAO", "email": "asha@example.com", "address": "1 MG Road", "mobile": "9999999999"},
    "folios": [{
        "folio": "1234567/89", "amc": "Test MF", "PAN": "ABCDE1234F", "KYC": "OK", "PANKYC": "OK",
        "schemes": [{
            "scheme": "Test Flexi Cap Fund - Direct Plan - Growth", "advisor": "DIRECT", "rta_code": "X", "rta": "CAMS",
            "type": "EQUITY", "isin": "INF000TEST01", "amfi": "999001", "nominees": ["X"], "open": 0, "close": 150.0,
            "close_calculated": 150.0, "valuation": {"date": "2026-09-30", "nav": 60.0, "value": 9000.0, "cost": 7550.0},
            "transactions": [
                {"date": D0.isoformat(), "description": "Purchase", "amount": 5000, "units": 100, "nav": 50, "balance": 100, "type": "PURCHASE"},
                {"date": D0.isoformat(), "description": "Stamp duty", "amount": 0.25, "units": None, "nav": None, "balance": None, "type": "STAMP_DUTY_TAX"},
                {"date": (D0 + timedelta(days=31)).isoformat(), "description": "SIP", "amount": 2550, "units": 50, "nav": 51, "balance": 150, "type": "PURCHASE_SIP"},
                {"date": (D0 + timedelta(days=100)).isoformat(), "description": "Redemption", "amount": -2750, "units": -50, "nav": 55, "balance": 100, "type": "REDEMPTION"},
                {"date": (D0 + timedelta(days=130)).isoformat(), "description": "SIP", "amount": 2800, "units": 50, "nav": 56, "balance": 150, "type": "PURCHASE_SIP"},
            ]}]}],
    "parse_warnings": [],
}

NSDL = {
    "file_type": "FileType.NSDL", "statement_period": {"from": "01-Sep-2026", "to": "30-Sep-2026"},
    "investor_info": {"name": "ASHA RAO"},
    "accounts": [{"name": "ASHA RAO", "type": "NSDL", "dp_id": "IN300000", "client_id": "12345678", "folios": 1, "balance": 1,
                  "owners": [{"name": "ASHA", "PAN": "ABCDE1234F"}],
                  "equities": [{"name": "TEST CO LTD", "isin": "INE000TEST01", "num_shares": 20, "price": 105, "value": 2100}],
                  "mutual_funds": [], "bonds": []}],
}


def seed_instruments():
    with rt_mod.get_runtime().Session() as s:
        s.add_all([Instrument(kind="mf", key="999001", isin="INF000TEST01", name="Test Flexi Cap Fund - Direct Plan - Growth",
                              plan="Direct", option="Growth", tracked=True),
                   Instrument(kind="stock", key="INE000TEST01", isin="INE000TEST01", symbol="TESTCO", exchange="NSE",
                              name="Test Co Ltd", tracked=True),
                   Instrument(kind="index", key="NIFTY 50", name="Nifty 50", tracked=True)])
        s.commit()


def upload(client, h, monkeypatch, data):
    monkeypatch.setattr(cas, "read", lambda pdf, pw: data)
    monkeypatch.setattr("finadvisor.api.routes.cas._start_tracking", lambda iid: None)
    return client.post("/api/cas/preview", files={"file": ("cas.pdf", b"%PDF-1.4 fake", "application/pdf")},
                       data={"password": "ABCDE1234F"}, headers=h)


def test_cams_detailed_preview_import_and_delete(client, monkeypatch):
    seed_instruments()
    h = login(client)
    r = upload(client, h, monkeypatch, CAMS)
    assert r.status_code == 200, r.text
    p = r.json()
    blob = json.dumps(p)
    for secret in ("ABCDE1234F", "ASHA RAO", "asha@example.com", "9999999999", "1234567/89", "1 MG Road"):
        assert secret not in blob
    it = p["items"][0]
    assert it["folio_last4"] == "6789" and it["units"] == 150 and not it["needs_cost"]
    assert [t["kind"] for t in it["transactions"]] == ["buy", "buy", "sell", "buy"]
    assert it["transactions"][0]["charges"] == 0.25
    assert it["instrument"]["scheme_code"] == "999001" and it["difference"] == 150
    res = client.post(f"/api/cas/{p['id']}/import", json={"choices": [{"key": it["key"]}]}, headers=h).json()
    assert res["transactions_added"] == 4
    hold = client.get("/api/holdings", headers=h).json()["items"]
    assert hold[0]["qty"] == pytest.approx(150)
    with rt_mod.get_runtime().Session() as s:
        up = s.get(CasUpload, p["id"])
        assert up.status == "imported" and up.preview is None
    # the same statement again: everything is a duplicate
    p2 = upload(client, h, monkeypatch, CAMS).json()
    assert p2["items"][0]["difference"] == 0
    assert client.post(f"/api/cas/{p2['id']}/import", json={"choices": [{"key": it["key"]}]}, headers=h).json()["duplicates_skipped"] == 4
    hist = client.get("/api/cas", headers=h).json()
    assert len(hist) == 2 and hist[0]["status"] == "imported"
    assert client.delete(f"/api/cas/{p['id']}", headers=h).status_code == 204
    assert client.get("/api/holdings", headers=h).json()["items"] == []


def test_demat_needs_cost_and_date(client, monkeypatch):
    seed_instruments()
    h = login(client)
    p = upload(client, h, monkeypatch, NSDL).json()
    it = p["items"][0]
    assert it["needs_cost"] and it["folio_last4"] == "5678" and it["kind"] == "stock"
    r = client.post(f"/api/cas/{p['id']}/import", json={"choices": [{"key": it["key"]}]}, headers=h)
    assert r.status_code == 422 and "average cost" in r.json()["detail"]
    ok = client.post(f"/api/cas/{p['id']}/import", json={"choices": [{"key": it["key"], "avg_price": 90, "date": "2025-01-15"}]},
                     headers=h).json()
    assert ok["transactions_added"] == 1
    tx = client.get("/api/transactions", headers=h).json()[0]
    assert tx["source"] == "cas" and tx["quantity"] == 20 and tx["price"] == 90


def test_bad_password_message(client, monkeypatch):
    h = login(client)

    def boom(pdf, pw):
        raise cas.CasError("The password did not open this statement.")
    monkeypatch.setattr(cas, "read", boom)
    r = client.post("/api/cas/preview", files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")}, data={"password": "nope"}, headers=h)
    assert r.status_code == 422 and "password" in r.json()["detail"]
    r = client.post("/api/cas/preview", files={"file": ("x.pdf", b"not a pdf", "application/pdf")}, data={"password": "x"}, headers=h)
    assert r.status_code == 422


def test_last4():
    assert cas.last4("1234567/89") == "6789" and cas.last4(None) is None
