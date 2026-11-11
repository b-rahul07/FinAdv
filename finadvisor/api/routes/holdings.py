"""Holdings, transactions, watchlist, instrument detail, dashboard and data status."""

from __future__ import annotations

import logging
import threading
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from finadvisor.advisor.capacity import assess
from finadvisor.advisor.health import health_card
from finadvisor.api import store
from finadvisor.api.deps import Current, current, db, rt
from finadvisor.db.models import (DataJobRun, Instrument, InstrumentNote, MarketDay, PriceDaily, Recommendation, Transaction,
                                  WatchItem)
from finadvisor.market import jobs
from finadvisor.portfolio import engine as E
from finadvisor.portfolio import service as P

router = APIRouter(prefix="/api", tags=["holdings"])
log = logging.getLogger(__name__)
_tracking: set[str] = set()
_backfill_lock = threading.Lock()   # one backfill at a time: they share files, the calendar table and a small CPU


def _start_tracking(inst_id: str) -> None:
    """Backfill price history in the background (first time only)."""
    if inst_id in _tracking:
        return
    _tracking.add(inst_id)

    def work():
        s = rt().Session()
        try:
            with _backfill_lock:
                jobs.track(s, s.get(Instrument, inst_id))
                s.commit()
        except Exception as e:  # noqa: BLE001 - shown to the user as "price history unavailable"
            s.rollback()
            log.warning("backfill failed for %s: %s", inst_id, e)
        finally:
            s.close()
            _tracking.discard(inst_id)

    threading.Thread(target=work, daemon=True).start()


def _inst(s: Session, iid: str) -> Instrument:
    i = s.get(Instrument, iid)
    if i is None or i.kind == "index":
        raise HTTPException(404, "Instrument not found")
    return i


@router.get("/instruments/search")
def search(q: str, kind: str = "listed", me: Current = Depends(current), s: Session = Depends(db)):
    q = q.strip()
    if len(q) < 2:
        return []
    like = f"%{q}%"
    kinds = ("mf",) if kind == "mf" else ("stock", "etf", "sgb")
    stmt = select(Instrument).where(Instrument.kind.in_(kinds), or_(Instrument.name.ilike(like), Instrument.symbol.ilike(like),
                                                                  Instrument.isin == q.upper(), Instrument.key == q))
    rows = list(s.scalars(stmt.limit(200)))
    up = q.upper()

    def rank(i: Instrument):
        exact = 0 if (i.symbol or "").upper() == up else 1
        starts = 0 if (i.symbol or "").upper().startswith(up) or i.name.upper().startswith(up) else 1
        mf_pref = 0 if (i.plan == "Direct" and i.option == "Growth") else 1
        return exact, starts, mf_pref, len(i.name)
    return [P.instrument_dict(i) for i in sorted(rows, key=rank)[:20]]


class TxIn(BaseModel):
    instrument_id: str
    kind: str = Field(..., pattern="^(buy|sell)$")
    trade_date: date
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    charges: float = Field(0, ge=0)
    note: str = Field("", max_length=500)


def _check_no_oversell(s: Session, user_id: str, inst_id: str, extra: list[Transaction] | None = None, skip: str | None = None):
    txs = [t for t in s.scalars(select(Transaction).where(Transaction.user_id == user_id, Transaction.instrument_id == inst_id))
           if t.id != skip] + (extra or [])
    acts = P.actions_for(s, inst_id)
    try:
        E.fifo([E.adjust_tx(P._tx(t), acts) for t in txs])
    except ValueError as e:
        raise HTTPException(422, f"That sale is more than you held on that date ({e}).")


@router.post("/transactions")
def add_tx(body: TxIn, me: Current = Depends(current), s: Session = Depends(db)):
    inst = _inst(s, body.instrument_id)
    if body.trade_date > jobs.today_ist():
        raise HTTPException(422, "The trade date is in the future.")
    t = Transaction(user_id=me.id, **body.model_dump())
    _check_no_oversell(s, me.id, inst.id, extra=[t])
    s.add(t)
    store.track(s, me.id, "transaction_added", kind=inst.kind)
    s.commit()
    _start_tracking(inst.id)
    return {"id": t.id}


@router.get("/transactions")
def list_tx(instrument_id: str | None = None, me: Current = Depends(current), s: Session = Depends(db)):
    q = select(Transaction, Instrument).join(Instrument).where(Transaction.user_id == me.id)
    if instrument_id:
        q = q.where(Transaction.instrument_id == instrument_id)
    return [{"id": t.id, "instrument": P.instrument_dict(i), "kind": t.kind, "trade_date": t.trade_date.isoformat(),
             "quantity": t.quantity, "price": t.price, "charges": t.charges, "note": t.note, "source": t.source}
            for t, i in s.execute(q.order_by(desc(Transaction.trade_date)))]


@router.patch("/transactions/{tx_id}")
def edit_tx(tx_id: str, body: TxIn, me: Current = Depends(current), s: Session = Depends(db)):
    t = s.get(Transaction, tx_id)
    if t is None or t.user_id != me.id:
        raise HTTPException(404, "Not found")
    inst = _inst(s, body.instrument_id)
    if body.trade_date > jobs.today_ist():
        raise HTTPException(422, "The trade date is in the future.")
    new = Transaction(user_id=me.id, **body.model_dump())
    _check_no_oversell(s, me.id, inst.id, extra=[new], skip=tx_id)
    if t.instrument_id != inst.id:   # moving a buy away from an instrument can leave its later sales uncovered
        _check_no_oversell(s, me.id, t.instrument_id, skip=tx_id)
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    s.commit()
    _start_tracking(inst.id)
    return {"ok": True}


@router.delete("/transactions/{tx_id}", status_code=204)
def delete_tx(tx_id: str, me: Current = Depends(current), s: Session = Depends(db)):
    t = s.get(Transaction, tx_id)
    if t is None or t.user_id != me.id:
        raise HTTPException(404, "Not found")
    _check_no_oversell(s, me.id, t.instrument_id, skip=tx_id)
    s.delete(t)
    s.commit()


@router.get("/holdings")
def get_holdings(me: Current = Depends(current), s: Session = Depends(db)):
    h = P.holdings(s, me.id, rt().bundle.tax)
    h["summary"] = P.summary(h["items"])
    h["loading"] = sorted(_tracking)
    return h


class WatchIn(BaseModel):
    instrument_id: str
    added_on: date | None = None


@router.get("/watchlist")
def get_watchlist(me: Current = Depends(current), s: Session = Depends(db)):
    return P.watchlist(s, me.id)


@router.post("/watchlist")
def add_watch(body: WatchIn, me: Current = Depends(current), s: Session = Depends(db)):
    inst = _inst(s, body.instrument_id)
    if s.scalar(select(WatchItem).where(WatchItem.user_id == me.id, WatchItem.instrument_id == inst.id)):
        raise HTTPException(409, "Already on your watchlist")
    s.add(WatchItem(user_id=me.id, instrument_id=inst.id, added_on=body.added_on or jobs.today_ist()))
    s.commit()
    _start_tracking(inst.id)
    return {"ok": True}


@router.delete("/watchlist/{wid}", status_code=204)
def del_watch(wid: str, me: Current = Depends(current), s: Session = Depends(db)):
    w = s.get(WatchItem, wid)
    if w is None or w.user_id != me.id:
        raise HTTPException(404, "Not found")
    s.delete(w)
    s.commit()


@router.get("/instruments/{iid}")
def instrument(iid: str, range: str = "1Y", me: Current = Depends(current), s: Session = Depends(db)):
    inst = _inst(s, iid)
    days = {"1M": 31, "6M": 183, "1Y": 366, "5Y": 5 * 366}.get(range, 366)
    as_of = jobs.today_ist()
    acts = P.actions_for(s, iid)
    rows = P.price_rows(s, iid, since=as_of - timedelta(days=days))
    pts = [{"date": d.isoformat(), "close": c} for d, c in E.adjusted_prices([(r.date, r.close) for r in rows], acts)]
    earliest = s.scalar(select(func.min(PriceDaily.date)).where(PriceDaily.instrument_id == iid))
    raw = P.holdings_raw(s, me.id).get(iid)
    holding = P.value_holding(s, inst, raw[1], as_of, rt().bundle.tax["equity"]["long_term_after_months"]) if raw else None
    marks = [{"date": t.trade_date.isoformat(), "kind": t.kind, "quantity": t.quantity, "price": t.price}
             for t in (raw[1] if raw else [])]
    note = s.scalar(select(InstrumentNote).where(InstrumentNote.user_id == me.id, InstrumentNote.instrument_id == iid))
    last = rows[-1] if rows else None
    w52_rows = P.price_rows(s, iid, since=as_of - timedelta(days=400))
    w52 = E.week52([(r.date, r.high, r.low, r.close) for r in w52_rows], acts, w52_rows[-1].date) if w52_rows and inst.kind != "mf" else None
    return {
        "instrument": P.instrument_dict(inst), "range": range, "points": pts, "marks": marks, "holding": holding,
        "note": note.text if note else "", "price_source": last.source if last else None,
        "price_date": last.date.isoformat() if last else None, "history_starts": earliest.isoformat() if earliest else None,
        "week52": {"low": w52[0], "high": w52[1]} if w52 else None,
        "corporate_actions": [{"ex_date": a.ex_date.isoformat(), "factor": a.factor} for a in acts],
        "loading": iid in _tracking,
    }


class NoteIn(BaseModel):
    text: str = Field("", max_length=5000)


@router.put("/instruments/{iid}/note")
def put_note(iid: str, body: NoteIn, me: Current = Depends(current), s: Session = Depends(db)):
    _inst(s, iid)
    n = s.scalar(select(InstrumentNote).where(InstrumentNote.user_id == me.id, InstrumentNote.instrument_id == iid))
    if n is None:
        s.add(InstrumentNote(user_id=me.id, instrument_id=iid, text=body.text))
    else:
        n.text = body.text
    s.commit()
    return {"ok": True}


@router.get("/dashboard")
def dashboard(range: str = "1Y", me: Current = Depends(current), s: Session = Depends(db)):
    if range not in P.RANGES:
        raise HTTPException(422, "Unknown range")
    b = rt().bundle
    as_of = jobs.today_ist()
    h = P.holdings(s, me.id, b.tax, as_of)
    items = h["items"]
    summ = P.summary(items)
    ser = P.series(s, me.id, range, as_of)
    pts = ser["points"]
    range_change = (pts[-1]["value"] - pts[0]["value"] - (pts[-1]["net_invested"] - pts[0]["net_invested"])) if len(pts) > 1 else None
    x, simple, xnote = P.portfolio_xirr(s, me.id, summ["value"], as_of)
    movers = sorted([i for i in items if i["day_change_pct"] is not None], key=lambda i: -abs(i["day_change_pct"]))[:5]
    profile, version, _ = store.latest_profile(s, me.id)
    recs = s.scalars(select(Recommendation).where(Recommendation.user_id == me.id)
                     .order_by(desc(Recommendation.last_suggested_at)).limit(5)).all()
    oth = O.others(s, me.id, as_of)
    other_value = sum(a["value"] or 0 for a in oth["assets"])
    owed = sum(l["outstanding"] for l in oth["liabilities"])
    alloc_items = items + [{"value": a["value"], "asset_class": a["asset_class"]} for a in oth["assets"] if a["value"]]
    return {
        "as_of": as_of.isoformat(),
        "net_worth": {"assets": summ["value"] + other_value, "liabilities": owed, "value": summ["value"] + other_value - owed,
                      "market_assets": summ["value"], "other_assets": other_value,
                      "self_reported": sum(a["value"] or 0 for a in oth["assets"] if a["self_reported"]),
                      "unvalued": [a["name"] for a in oth["assets"] if a["value"] is None]},
        "day_change": summ["day_change"],
        "range": range,
        "range_change": range_change,
        "latest_price_date": summ["latest_price_date"],
        "unpriced": summ["unpriced"],
        "series": ser,
        "allocation": P.allocation(alloc_items),
        "returns": {"invested": summ["invested"], "value": summ["value"], "gain": summ["value"] - summ["invested"],
                    "xirr": x, "simple": simple, "note": xnote},
        "movers": [{"instrument": m["instrument"], "day_change_pct": m["day_change_pct"], "day_change": m["day_change"],
                    "price_date": m["price_date"]} for m in movers],
        "health": health_card(profile, assess(profile, b.rules), b.rules) if profile else None,
        "profile_version": version,
        "advice": [{"id": r.id, "title": r.title, "status": r.status, "suggested_at": r.created_at.isoformat()} for r in recs],
        "holdings_count": len(items) + len(oth["assets"]) + len(oth["liabilities"]),
    }


@router.get("/market/status")
def market_status(me: Current = Depends(current), s: Session = Depends(db)):
    out = []
    for key in ("nse_bhav", "bse_bhav", "nse_indices"):
        d = s.scalar(select(func.max(MarketDay.date)).where(MarketDay.source == key, MarketDay.published.is_(True)))
        out.append({"source": key, "latest": d.isoformat() if d else None})
    amfi = s.scalar(select(func.max(PriceDaily.date)).where(PriceDaily.source == "AMFI daily NAV"))
    out.append({"source": "amfi_nav", "latest": amfi.isoformat() if amfi else None})
    last = s.scalar(select(DataJobRun).order_by(desc(DataJobRun.created_at)).limit(1))
    return {"sources": out, "last_job": {"status": last.status, "at": last.created_at.isoformat(), "detail": last.detail} if last else None}


# --------------------------------------------------------------------------- other assets, cover, loans

from finadvisor.db.models import InsurancePolicy, Liability, OtherAsset  # noqa: E402
from finadvisor.portfolio import others as O  # noqa: E402


def _last4(x: str | None) -> str | None:
    digits = "".join(ch for ch in (x or "") if ch.isalnum())
    return digits[-4:] if digits else None


class AssetIn(BaseModel):
    kind: str = Field(..., pattern="^(" + "|".join(O.KIND_CLASS) + ")$")
    name: str = Field(..., min_length=1, max_length=200)
    data: dict = {}
    account_last4: str | None = Field(None, max_length=40)


class LiabilityIn(BaseModel):
    kind: str = Field(..., pattern="^(home|car|personal|education|bnpl|credit_card|gold|two_wheeler|other)$")
    lender: str = Field("", max_length=200)
    outstanding: float = Field(..., ge=0)
    rate_pa: float | None = Field(None, ge=0, le=100)
    emi_monthly: float = Field(0, ge=0)
    end_date: date | None = None
    as_of: date | None = None
    account_last4: str | None = Field(None, max_length=40)


class InsuranceIn(BaseModel):
    kind: str = Field(..., pattern="^(term|health)$")
    insurer: str = Field("", max_length=200)
    sum_assured: float = Field(..., gt=0)
    premium_yearly: float | None = Field(None, ge=0)
    renewal_date: date | None = None
    employer_provided: bool = False


@router.get("/others")
def get_others(me: Current = Depends(current), s: Session = Depends(db)):
    return O.others(s, me.id, jobs.today_ist())


def _own(s: Session, model, rid: str, me: Current):
    row = s.get(model, rid)
    if row is None or row.user_id != me.id:
        raise HTTPException(404, "Not found")
    return row


@router.post("/others/assets")
def add_asset(body: AssetIn, me: Current = Depends(current), s: Session = Depends(db)):
    a = OtherAsset(user_id=me.id, kind=body.kind, name=body.name, data=body.data, account_last4=_last4(body.account_last4))
    s.add(a)
    s.commit()
    return O.value_asset(a, jobs.today_ist(), O.gold_reference(s, jobs.today_ist()))


@router.patch("/others/assets/{aid}")
def edit_asset(aid: str, body: AssetIn, me: Current = Depends(current), s: Session = Depends(db)):
    a = _own(s, OtherAsset, aid, me)
    a.kind, a.name, a.data, a.account_last4 = body.kind, body.name, body.data, _last4(body.account_last4)
    s.commit()
    return {"ok": True}


@router.delete("/others/assets/{aid}", status_code=204)
def del_asset(aid: str, me: Current = Depends(current), s: Session = Depends(db)):
    s.delete(_own(s, OtherAsset, aid, me))
    s.commit()


@router.post("/others/liabilities")
def add_liability(body: LiabilityIn, me: Current = Depends(current), s: Session = Depends(db)):
    s.add(Liability(user_id=me.id, **{**body.model_dump(), "as_of": body.as_of or jobs.today_ist(),
                                      "account_last4": _last4(body.account_last4)}))
    s.commit()
    return {"ok": True}


@router.delete("/others/liabilities/{lid}", status_code=204)
def del_liability(lid: str, me: Current = Depends(current), s: Session = Depends(db)):
    s.delete(_own(s, Liability, lid, me))
    s.commit()


@router.post("/others/insurance")
def add_insurance(body: InsuranceIn, me: Current = Depends(current), s: Session = Depends(db)):
    s.add(InsurancePolicy(user_id=me.id, **body.model_dump()))
    s.commit()
    return {"ok": True}


@router.delete("/others/insurance/{pid}", status_code=204)
def del_insurance(pid: str, me: Current = Depends(current), s: Session = Depends(db)):
    s.delete(_own(s, InsurancePolicy, pid, me))
    s.commit()


@router.get("/profile/proposal")
def profile_proposal(me: Current = Depends(current), s: Session = Depends(db)):
    """Facts implied by what the user tracks, for the profile card. Nothing is applied until the user confirms."""
    p, _, _ = store.latest_profile(s, me.id)
    from finadvisor.advisor.profile import Profile
    current_profile = (p or Profile()).model_dump(mode="json")
    proposed, changed = O.profile_proposal(current_profile, O.others(s, me.id, jobs.today_ist()),
                                           P.holdings(s, me.id, rt().bundle.tax)["items"])
    return {"proposed": proposed, "changed": changed}
