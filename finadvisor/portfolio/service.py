"""Reads holdings and prices from the database and values them with the engine. The API and the advisor
both use this, so every page shows the same numbers."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from finadvisor.calc.xirr import is_annualisable, xirr
from finadvisor.db.models import CorporateAction, Instrument, PriceDaily, Transaction, WatchItem
from finadvisor.market.jobs import BENCHMARK, today_ist
from finadvisor.portfolio import engine as E

ASSET_CLASSES = ("stocks", "mutual_funds", "gold", "silver", "deposits", "retirement", "cash", "other")
RANGES = {"1M": 31, "6M": 183, "1Y": 366, "3Y": 3 * 366, "ALL": None}


def asset_class(inst: Instrument) -> str:
    text = f"{inst.name} {inst.category or ''}".lower()
    if inst.kind == "sgb" or "gold" in text:
        return "gold"
    if "silver" in text:
        return "silver"
    if inst.kind == "mf":
        return "mutual_funds"
    return "stocks"


def actions_for(s: Session, iid: str) -> list[E.Action]:
    return [E.Action(a.ex_date, a.factor) for a in
            s.scalars(select(CorporateAction).where(CorporateAction.instrument_id == iid).order_by(CorporateAction.ex_date))]


def price_rows(s: Session, iid: str, since: date | None = None) -> list[PriceDaily]:
    q = select(PriceDaily).where(PriceDaily.instrument_id == iid)
    if since:
        q = q.where(PriceDaily.date >= since)
    return list(s.scalars(q.order_by(PriceDaily.date)))


def _tx(t: Transaction) -> E.Tx:
    return E.Tx(t.trade_date, t.kind, t.quantity, t.price, t.charges or 0.0)


def holdings_raw(s: Session, user_id: str) -> dict[str, tuple[Instrument, list[Transaction]]]:
    out: dict[str, tuple[Instrument, list[Transaction]]] = {}
    for t, inst in s.execute(select(Transaction, Instrument).join(Instrument, Instrument.id == Transaction.instrument_id)
                             .where(Transaction.user_id == user_id).order_by(Transaction.trade_date)):
        out.setdefault(inst.id, (inst, []))[1].append(t)
    return out


def stale(price_date: date | None, as_of: date) -> bool:
    """More than 4 calendar days old means a missed publication, not a weekend or a single holiday."""
    return price_date is None or (as_of - price_date).days > 4


def value_holding(s: Session, inst: Instrument, txs: list[Transaction], as_of: date, tax_months: int) -> dict:
    acts = actions_for(s, inst.id)
    adj = [E.adjust_tx(_tx(t), acts) for t in txs]
    rows = price_rows(s, inst.id, since=as_of - timedelta(days=400))
    last = rows[-1] if rows else None
    prev = rows[-2] if len(rows) > 1 else None
    # prev close must be comparable with the latest close
    prev_close = (prev.close * E.factor_after(prev.date, [a for a in acts if a.ex_date <= last.date])) if prev and last else None
    pos = E.position(adj, last.close if last else None, last.date if last else None, prev_close, as_of, tax_months)
    w52 = E.week52([(r.date, r.high, r.low, r.close) for r in rows], acts, last.date) if last and inst.kind != "mf" else None
    flows = E.xirr_flows(adj, pos.value, as_of)
    first = pos.first_buy
    annualised = first is not None and is_annualisable(first, as_of)
    return {
        "instrument": instrument_dict(inst),
        "asset_class": asset_class(inst),
        "qty": pos.qty,
        "avg_price": pos.avg_price,
        "invested": pos.invested,
        "price": pos.price,
        "prev_price": pos.prev_price,
        "value": pos.value,
        "day_change": pos.day_change,
        "day_change_pct": pos.day_change_pct,
        "unrealised": pos.unrealised,
        "unrealised_pct": pos.unrealised_pct,
        "realised": pos.realised,
        "xirr": xirr(flows) if annualised and pos.value else None,
        "xirr_note": None if annualised else "Held under a year: shown as a simple return, not annualised.",
        "first_buy": first.isoformat() if first else None,
        "holding_days": pos.holding_days,
        "long_term_qty": pos.long_term_qty,
        "short_term_qty": pos.short_term_qty,
        "week52": {"low": w52[0], "high": w52[1]} if w52 else None,
        "price_source": last.source if last else None,
        "price_date": last.date.isoformat() if last else None,
        "stale": stale(last.date if last else None, as_of),
        "adjusted_for": [{"ex_date": a.ex_date.isoformat(), "factor": a.factor} for a in acts],
    }


def instrument_dict(i: Instrument) -> dict:
    return {"id": i.id, "kind": i.kind, "symbol": i.symbol, "exchange": i.exchange, "isin": i.isin, "name": i.name,
            "amc": i.amc, "category": i.category, "plan": i.plan, "option": i.option, "expense_ratio": i.expense_ratio,
            "scheme_code": i.key if i.kind == "mf" else None}


def holdings(s: Session, user_id: str, tax_cfg: dict, as_of: date | None = None) -> dict:
    as_of = as_of or today_ist()
    months = tax_cfg["equity"]["long_term_after_months"]
    items = []
    for inst, txs in holdings_raw(s, user_id).values():
        h = value_holding(s, inst, txs, as_of, months)
        if h["qty"] > 1e-9:
            items.append(h)
    total = sum(h["value"] or 0 for h in items)
    for h in items:
        h["weight"] = (h["value"] / total) if total and h["value"] is not None else None
    items.sort(key=lambda h: -(h["value"] or h["invested"]))
    return {"as_of": as_of.isoformat(), "items": items}


def summary(items: list[dict]) -> dict:
    invested = sum(h["invested"] for h in items)
    priced = [h for h in items if h["value"] is not None]
    value = sum(h["value"] for h in priced)
    day = sum(h["day_change"] or 0 for h in priced)
    return {"invested": invested, "value": value, "gain": value - sum(h["invested"] for h in priced),
            "day_change": day, "unpriced": len(items) - len(priced),
            "latest_price_date": max((h["price_date"] for h in priced if h["price_date"]), default=None)}


def portfolio_xirr(s: Session, user_id: str, value_now: float, as_of: date) -> tuple[float | None, float | None, str | None]:
    flows = []
    first = None
    for inst, txs in holdings_raw(s, user_id).values():
        acts = actions_for(s, inst.id)
        adj = [E.adjust_tx(_tx(t), acts) for t in txs]
        flows += E.xirr_flows(adj, None, as_of)
        first = min([first, *(t.date for t in adj)] if first else [t.date for t in adj])
    if not flows or not value_now:
        return None, None, None
    put_in = -sum(cf for _, cf in flows)
    simple = (value_now - put_in) / put_in if put_in > 0 else None
    if first and is_annualisable(first, as_of):
        return xirr(flows + [(as_of, value_now)]), simple, None
    return None, simple, "Invested for under a year: simple return shown, not annualised."


def series(s: Session, user_id: str, range_key: str, as_of: date | None = None) -> dict:
    as_of = as_of or today_ist()
    raw = holdings_raw(s, user_id)
    if not raw:
        return {"points": [], "benchmark_label": None}
    adj_txs: dict[str, list[E.Tx]] = {}
    prices: dict[str, list[tuple[date, float]]] = {}
    first = min(t.trade_date for _, txs in raw.values() for t in txs)
    days = RANGES.get(range_key)
    start = max(first, as_of - timedelta(days=days)) if days else first
    all_dates: set[date] = set()
    for iid, (inst, txs) in raw.items():
        acts = actions_for(s, iid)
        adj_txs[iid] = [E.adjust_tx(_tx(t), acts) for t in txs]
        rows = price_rows(s, iid, since=start - timedelta(days=10))
        prices[iid] = E.adjusted_prices([(r.date, r.close) for r in rows], acts)
        all_dates |= {r.date for r in rows if r.date >= start}
    dates = sorted(all_dates)
    pts = E.value_series(adj_txs, prices, dates)
    bench_inst = s.scalar(select(Instrument).where(Instrument.kind == "index", Instrument.key == BENCHMARK))
    bench = [(r.date, r.close) for r in price_rows(s, bench_inst.id, since=first - timedelta(days=10))] if bench_inst else []
    bench_start = None
    if bench and pts:
        # Start where both series exist: the portfolio's value that day goes "into Nifty", then every later
        # contribution or withdrawal follows on its own date.
        flows_by_day: dict[date, float] = defaultdict(float)
        for txs in adj_txs.values():
            for t in txs:
                flows_by_day[t.date] += (t.qty * t.price + t.charges) if t.kind == "buy" else -(t.qty * t.price - t.charges)
        first_lvl = bench[0][0]
        units = None
        prev_date = None
        for p in pts:
            lvl = E.last_on_or_before(bench, p["date"])
            if lvl is None or p["date"] < first_lvl or p["value"] <= 0:
                p["benchmark"] = None
                continue
            if units is None:
                units = p["value"] / lvl[1]
                bench_start = p["date"]
            else:
                for fd, amt in flows_by_day.items():
                    if prev_date < fd <= p["date"]:
                        fl = E.last_on_or_before(bench, fd)
                        units += amt / (fl or lvl)[1]
            prev_date = p["date"]
            p["benchmark"] = units * lvl[1]
    for p in pts:
        p["date"] = p["date"].isoformat()
    return {
        "points": pts,
        "benchmark_label": (f"Nifty 50 (price index) from {bench_start:%d %b %Y}: your value that day, then the same money on the same "
                            "dates. Market performance, not advice performance.") if bench_start else None,
        "benchmark_source": "NSE Indices daily close" if bench else None,
    }


def watchlist(s: Session, user_id: str) -> list[dict]:
    out = []
    for w, inst in s.execute(select(WatchItem, Instrument).join(Instrument, Instrument.id == WatchItem.instrument_id)
                             .where(WatchItem.user_id == user_id).order_by(WatchItem.added_on.desc())):
        acts = actions_for(s, inst.id)
        rows = price_rows(s, inst.id, since=min(w.added_on, today_ist() - timedelta(days=370)) - timedelta(days=10))
        series_adj = E.adjusted_prices([(r.date, r.close) for r in rows], acts)
        at_add = E.last_on_or_before(series_adj, w.added_on)
        last = rows[-1] if rows else None
        cur = series_adj[-1][1] if series_adj else None
        w52 = E.week52([(r.date, r.high, r.low, r.close) for r in rows], acts, last.date) if last and inst.kind != "mf" else None
        out.append({
            "id": w.id, "instrument": instrument_dict(inst), "added_on": w.added_on.isoformat(),
            "price_when_added": at_add[1] if at_add else None,
            "price_when_added_date": at_add[0].isoformat() if at_add else None,
            "current_price": cur, "price_date": last.date.isoformat() if last else None,
            "price_source": last.source if last else None,
            "change_since_added": (cur / at_add[1] - 1) if cur and at_add else None,
            "week52": {"low": w52[0], "high": w52[1]} if w52 else None,
            "stale": stale(last.date if last else None, today_ist()),
        })
    return out


def allocation(items: list[dict]) -> list[dict]:
    totals = {c: 0.0 for c in ASSET_CLASSES}
    for h in items:
        if h["value"]:
            totals[h["asset_class"]] += h["value"]
    t = sum(totals.values())
    return [{"asset_class": c, "value": v, "share": v / t if t else 0.0} for c, v in totals.items() if v > 0]
