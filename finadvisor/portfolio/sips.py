"""SIPs found from transactions, not typed in.

A SIP is at least three buys of the same fund, each within 1% of the same amount, about a month apart. The latest
such run of a fund is its SIP: the amount, the usual day of the month, when the next instalment is expected and
whether one has been missed. `sync` keeps the `sips` table in step, so a person can say "I stopped this one" and it
stays stopped.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from finadvisor.db.models import Sip
from finadvisor.portfolio import service as P

MIN_INSTALMENTS = 3
AMOUNT_TOLERANCE = 0.01          # each instalment within 1% of the run's latest amount
GAP_DAYS = (24, 38)              # "about a month": weekends and holidays move the date a few days either way
GRACE_DAYS = 7                   # an instalment this late is missed
STOPPED_AFTER_DAYS = 45          # this long past the expected date, the SIP has stopped


@dataclass
class Found:
    amount: float
    day_of_month: int
    start: date
    last: date
    instalments: int
    next_expected: date
    status: str                  # active | missed | stopped


def detect(buys: list[tuple[date, float]], today: date) -> Found | None:
    """The SIP in one fund's buys ([(date, rupees)]), or None. Lump sums of other amounts in between are ignored."""
    best: Found | None = None
    done: list[float] = []
    for _, anchor in sorted(buys, reverse=True):
        if anchor <= 0 or any(abs(anchor - a) <= AMOUNT_TOLERANCE * a for a in done):
            continue                                                     # this amount's cluster is already examined
        done.append(anchor)
        same = sorted(d for d, a in buys if abs(a - anchor) <= AMOUNT_TOLERANCE * anchor)
        run = [same[-1]]
        for d in reversed(same[:-1]):                                    # walk back from the latest instalment
            gap = (run[0] - d).days
            if GAP_DAYS[0] <= gap <= GAP_DAYS[1]:
                run.insert(0, d)
            elif gap > GAP_DAYS[1]:
                break                                                    # a break in the run: earlier buys are another SIP
        if len(run) < MIN_INSTALMENTS:
            continue
        amounts = [a for d, a in buys if d in run and abs(a - anchor) <= AMOUNT_TOLERANCE * anchor]
        day = round(statistics.median(d.day for d in run))
        nxt = run[-1] + relativedelta(months=1)
        late = (today - nxt).days
        status = "active" if late <= GRACE_DAYS else ("missed" if late <= STOPPED_AFTER_DAYS else "stopped")
        found = Found(float(round(statistics.median(amounts))), day, run[0], run[-1], len(run), nxt, status)
        if best is None or found.last > best.last:
            best = found
    return best


def find_all(s: Session, user_id: str, today: date) -> dict[str, tuple[dict, Found]]:
    """instrument id -> (instrument, its SIP), for the funds this person has bought."""
    out = {}
    for iid, (inst, txs) in P.holdings_raw(s, user_id).items():
        if inst.kind != "mf":
            continue
        f = detect([(t.trade_date, t.quantity * t.price) for t in txs if t.kind == "buy"], today)
        if f is not None:
            out[iid] = (P.instrument_dict(inst), f)
    return out


def sync(s: Session, user_id: str, today: date) -> dict:
    """Detected SIPs written to the `sips` table and returned with the person's own on/off choice.
    A SIP the person switched off stays off; a new one starts on unless it has already stopped."""
    found = find_all(s, user_id, today)
    rows = {r.instrument_id: r for r in s.scalars(select(Sip).where(Sip.user_id == user_id))}
    items = []
    for iid, (inst, f) in found.items():
        row = rows.get(iid)
        if row is None:
            row = Sip(user_id=user_id, instrument_id=iid, amount=f.amount, day_of_month=f.day_of_month,
                      start_date=f.start, active=f.status != "stopped")
            s.add(row)
            s.flush()
        else:
            row.amount, row.day_of_month, row.start_date = f.amount, f.day_of_month, f.start
        status = f.status if row.active else "off"
        items.append({"id": row.id, "instrument": inst, "amount": f.amount, "day_of_month": f.day_of_month,
                      "since": f.start.isoformat(), "instalments": f.instalments, "last_date": f.last.isoformat(),
                      "next_expected": f.next_expected.isoformat(), "status": status, "active": row.active})
    items.sort(key=lambda x: (x["status"] != "missed", -x["amount"]))
    running = [x for x in items if x["status"] in ("active", "missed")]
    return {"items": items, "monthly_total": sum(x["amount"] for x in running), "as_of": today.isoformat(),
            "window": {"grace_days": GRACE_DAYS, "tolerance": AMOUNT_TOLERANCE, "min_instalments": MIN_INSTALMENTS}}


def window_end(found: Found) -> date:
    """The last day an instalment still counts as on time."""
    return found.next_expected + timedelta(days=GRACE_DAYS)
