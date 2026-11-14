"""Make a SYNTHETIC CAMS-style detailed CAS PDF for testing the CAS import (Money -> Import statement).

The statement belongs to a made-up investor and says on every page that it is a test file, not a real statement. It
uses four real funds (so the import matches them to FinAdvisor's fund list) and their real NAVs from the local price
cache (data/finadvisor.db), so the imported cost and today's value are consistent. The layout follows what casparser
reads (column header, folio line, scheme line with ISIN and registrar, opening/closing balances, NAV and valuation).

    python scripts/make_test_cas.py [out.pdf]        # password: ABCDE1234F (a made-up PAN)

Needs reportlab (dev only; not a FinAdvisor dependency).
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "ABCDE1234F"
PERIOD = (date(2025, 1, 1), date(2026, 10, 31))
VALUED = date(2026, 10, 30)

# (AMC line, folio, scheme code, scheme name, AMFI code, ISIN, registrar, transactions)
# transactions: ("buy" | "sip" | "sell", target date, rupees)
FUNDS = [
    ("PPFAS Mutual Fund", "91234567", "PPFC12", "Parag Parikh Flexi Cap Fund - Direct Plan - Growth", "122639",
     "INF879O01027", "KFINTECH",
     [("buy", date(2025, 1, 10), 25_000)] + [("sip", _d, 5_000) for _d in
                                             [date(2025 + (m - 1) // 12, (m - 1) % 12 + 1, 5) for m in range(2, 23)]]),
    ("UTI Mutual Fund", "48123456 / 12", "UTNF50", "UTI Nifty 50 Index Fund - Direct Plan - Growth", "120716",
     "INF789F01XA0", "KFINTECH",
     [("sip", date(2025 + (m - 1) // 12, (m - 1) % 12 + 1, 10), 3_000) for m in range(4, 23)]
     + [("sell", date(2026, 8, 12), 15_000)]),
    ("HDFC Mutual Fund", "1712345 / 45", "HLFDG", "HDFC Liquid Fund - Direct Plan - Growth", "119091",
     "INF179KB1HP9", "CAMS",
     [("buy", date(2025, 6, 16), 50_000), ("sell", date(2026, 3, 3), 20_000)]),
    ("Mirae Asset Mutual Fund", "79912345", "MAEL2", "Mirae Asset ELSS Tax Saver Fund - Direct Plan - Growth", "135781",
     "INF769K01DM9", "KFINTECH",
     [("buy", date(2026, 1, 15), 12_500), ("buy", date(2026, 3, 10), 12_500)]),
]

D2, D3, D4 = Decimal("0.01"), Decimal("0.001"), Decimal("0.0001")


def q(x: Decimal, step: Decimal) -> Decimal:
    return x.quantize(step, rounding=ROUND_HALF_UP)


def inr(x: Decimal, step: Decimal = D2) -> str:
    """Indian digit grouping: 1,23,456.78."""
    neg, s = x < 0, f"{abs(q(x, step)):f}"
    whole, _, frac = s.partition(".")
    head, tail = whole[:-3], whole[-3:]
    while len(head) > 2:
        tail, head = head[-2:] + "," + tail, head[:-2]
    whole = (head + "," + tail) if head else tail
    out = whole + ("." + frac if frac else "")
    return f"({out})" if neg else out


def dmy(d: date) -> str:
    return d.strftime("%d-%b-%Y")


def nav_series(db: sqlite3.Connection, amfi: str) -> list[tuple[date, Decimal]]:
    rows = db.execute("select p.date, p.close from prices_daily p join instruments i on i.id = p.instrument_id "
                      "where i.kind = 'mf' and i.key = ? order by p.date", (amfi,)).fetchall()
    if not rows:
        raise SystemExit(f"No NAV history for AMFI {amfi} in data/finadvisor.db; refresh prices first.")
    return [(date.fromisoformat(d), Decimal(str(c))) for d, c in rows]


def nav_on_or_after(series, d: date) -> tuple[date, Decimal]:
    for day, nav in series:
        if day >= d:
            return day, q(nav, D4)
    raise SystemExit(f"No NAV on or after {d}")


def nav_on_or_before(series, d: date) -> tuple[date, Decimal]:
    best = None
    for day, nav in series:
        if day <= d:
            best = (day, q(nav, D4))
    return best


def build_rows(series, txs):
    """Statement rows plus closing units, FIFO cost of what is left."""
    rows, bal, lots = [], Decimal(0), []           # lots: [units, cost]
    sip_no = 0
    for kind, target, rupees in txs:
        day, nav = nav_on_or_after(series, target)
        gross = Decimal(rupees)
        if kind in ("buy", "sip"):
            stamp = q(gross * Decimal("0.00005"), D2)
            net = gross - stamp
            units = q(net / nav, D3)
            bal += units
            lots.append([units, net])
            if kind == "sip":
                sip_no += 1
                desc = f"SIP Purchase - Instalment {sip_no}"
            else:
                desc = "Purchase"
            rows.append((day, desc, net, units, nav, bal))
            rows.append((day, "*** Stamp Duty ***", stamp, None, None, None))
        else:
            units = q(gross / nav, D3)
            bal -= units
            left = units
            while left > 0:                         # FIFO: the oldest lots are sold first
                u, c = lots[0]
                take = min(u, left)
                lots[0] = [u - take, c - c * take / u]
                left -= take
                if lots[0][0] <= 0:
                    lots.pop(0)
            rows.append((day, "Redemption", -gross, -units, nav, bal))
    cost = q(sum((c for _, c in lots), Decimal(0)), D2)
    return rows, bal, cost


class Page:
    """A4 page writer that matches the layout casparser expects."""

    X_DATE, X_TXN, X_AMT, X_UNITS, X_PRICE, X_BAL = 40, 110, 330, 400, 465, 545

    def __init__(self, c: canvas.Canvas):
        self.c, self.y, self.page = c, 0.0, 0

    def new_page(self):
        if self.page:
            self.c.showPage()
        self.page += 1
        c = self.c
        w, h = A4
        # vertical issuer marker, as on the real statements (casparser detects the issuer from it, then ignores it)
        c.saveState()
        c.setFont("Helvetica", 5)
        c.translate(14, 120)
        c.rotate(90)
        c.drawString(0, 0, "CAMSCASWS-TEST-SYNTHETIC Version:V3.4 Test-0001")
        c.restoreState()
        c.setFont("Helvetica-Bold", 8)
        c.drawRightString(w - 40, h - 30, "SYNTHETIC TEST STATEMENT - made for FinAdvisor testing, not a real statement")
        c.setFont("Helvetica", 7)
        c.drawRightString(w - 40, 25, f"Page {self.page} - test data only")
        self.y = h - 50

    def header(self):
        c = self.c
        self.y -= 18
        c.setFont("Helvetica-Bold", 8)
        c.drawString(self.X_DATE, self.y, "Date")
        c.drawString(self.X_TXN, self.y, "Transaction")
        c.drawRightString(self.X_AMT, self.y, "Amount")
        c.drawRightString(self.X_UNITS, self.y, "Units")
        c.drawRightString(self.X_PRICE, self.y, "Price")
        c.drawRightString(self.X_BAL, self.y, "Unit")
        c.setFont("Helvetica", 7)
        c.drawRightString(self.X_AMT, self.y - 9, "(INR)")
        c.drawRightString(self.X_PRICE, self.y - 9, "(INR)")
        c.setFont("Helvetica-Bold", 8)
        c.drawRightString(self.X_BAL, self.y - 9, "Balance")
        self.y -= 26

    def need(self, lines: int):
        if self.y - lines * 11 < 50:
            self.new_page()
            self.header()

    def text(self, s: str, x: float | None = None, bold: bool = False, size: float = 7.5):
        self.need(1)
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        self.c.drawString(self.X_DATE if x is None else x, self.y, s)
        self.y -= 11

    def row(self, day, desc, amount, units, price, bal):
        self.need(1)
        c = self.c
        c.setFont("Helvetica", 7.5)
        c.drawString(self.X_DATE, self.y, dmy(day))
        c.drawString(self.X_TXN, self.y, desc)
        if amount is not None:
            c.drawRightString(self.X_AMT, self.y, inr(amount))
        if units is not None:
            c.drawRightString(self.X_UNITS, self.y, inr(units, D3))
        if price is not None:
            c.drawRightString(self.X_PRICE, self.y, inr(price, D4))
        if bal is not None:
            c.drawRightString(self.X_BAL, self.y, inr(bal, D3))
        self.y -= 11


def make(out: Path, series_for=None) -> dict:
    """series_for(amfi) -> [(date, nav)]; by default the local price cache. Tests pass their own."""
    if series_for is None:
        db = sqlite3.connect(ROOT / "data" / "finadvisor.db")
        series_for = lambda amfi: nav_series(db, amfi)  # noqa: E731
    c = canvas.Canvas(str(out), pagesize=A4,
                      encrypt=StandardEncryption(PASSWORD, ownerPassword=PASSWORD + "-owner", strength=128))
    c.setTitle("Synthetic test CAS - not a real statement")
    p = Page(c)
    p.new_page()
    w, h = A4
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(w - 40, h - 60, "Consolidated Account Statement")
    c.setFont("Helvetica", 8)
    c.drawRightString(w - 40, h - 72, f"{dmy(PERIOD[0])} To {dmy(PERIOD[1])}")
    # investor block, top-left (made up)
    for s in ("Email Id: test.investor@example.com", "Test Investor", "1 Demo Street, Test Nagar",
              "Bengaluru - 560001 Karnataka India", "Mobile: +910000000000"):
        p.text(s)
    p.y -= 6
    c.setFont("Helvetica", 7)
    c.drawString(40, p.y, "This is a made-up statement for software testing. The investor, folios and PAN are fictitious.")
    p.y -= 6
    p.header()

    summary = []
    for amc, folio, code, name, amfi, isin, rta, txs in FUNDS:
        series = series_for(amfi)
        rows, close, cost = build_rows(series, txs)
        vday, vnav = nav_on_or_before(series, VALUED)
        value = q(close * vnav, D2)
        p.need(8)
        p.text(amc, bold=True, size=8.5)
        p.text(f"Folio No: {folio}   PAN: {PASSWORD}   KYC: OK   PAN: OK")
        p.text("Test Investor")
        p.text(f"{code}-{name} - ISIN: {isin}(Advisor: DIRECT) Registrar : {rta}")
        p.text("Nominee 1: Test Nominee   Nominee 2:   Nominee 3:")
        p.text("Opening Unit Balance: 0.000", x=Page.X_TXN)
        for r in rows:
            p.row(*r)
        p.text(f"Closing Unit Balance: {inr(close, D3)}      NAV on {dmy(vday)}: INR {inr(vnav, D4)}", x=Page.X_TXN)
        p.text(f"Total Cost Value: {inr(cost)}      Market Value on {dmy(vday)}: INR {inr(value)}", x=Page.X_TXN)
        p.y -= 8
        summary.append({"scheme": name, "amfi": amfi, "units": float(close), "cost": float(cost), "value": float(value),
                        "transactions": sum(1 for r in rows if r[3] is not None)})
    c.save()
    return {"file": str(out), "password": PASSWORD, "schemes": summary}


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "test-cas-synthetic.pdf"
    import json
    print(json.dumps(make(target), indent=2))
