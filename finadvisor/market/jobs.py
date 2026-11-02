"""Daily market-data jobs. Run after sources publish (exchanges ~6 pm IST, AMFI by ~11 pm IST):

    python -m finadvisor.market.jobs daily          # latest files, prices for tracked instruments
    python -m finadvisor.market.jobs masters        # refresh stock and fund lists

Only instruments someone holds or watches get prices stored (Supabase free tier: 500 MB). Raw files are cached
on disk, so tracking a new instrument backfills from the cache without new downloads where possible.
"""

from __future__ import annotations

import logging
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finadvisor.db.base import utcnow
from finadvisor.db.models import CorporateAction, DataJobRun, Instrument, MarketDay, PriceDaily
from finadvisor.market import parse, sources
from finadvisor.portfolio.engine import classify, derive_actions

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
BENCHMARK = "NIFTY 50"
BACKFILL_DAYS = 400   # covers the 52-week range and 1Y charts; longer history accumulates daily


def today_ist() -> date:
    return datetime.now(IST).date()


def weekdays_back(end: date, n_days: int) -> list[date]:
    """Every calendar day in the window. Exchanges hold occasional weekend sessions (Union Budget day, Muhurat
    trading), so weekends are tried too; days without a file are recorded once in market_days and skipped after."""
    return [end - timedelta(days=k) for k in range(n_days, -1, -1)]


# --------------------------------------------------------------------------- helpers

def _day_known(s: Session, source: str, d: date) -> MarketDay | None:
    return s.get(MarketDay, (source, d))


def _mark(s: Session, source: str, d: date, published: bool) -> None:
    row = s.get(MarketDay, (source, d))
    if row is None:
        s.add(MarketDay(source=source, date=d, published=published))
    else:
        row.published, row.fetched_at = published, utcnow()


def _fetch_day(s: Session, src: sources.Source, d: date) -> sources.Fetched | None:
    """Fetch one dated file. Weekdays that 404 are recorded as unpublished once the day is over in IST."""
    known = _day_known(s, src.key, d)
    if known is not None and not known.published:
        return None
    try:
        f = sources.fetch(src, d)
    except sources.NotPublished:
        if d < today_ist():
            _mark(s, src.key, d, False)
        return None
    except httpx.HTTPError as e:
        log.warning("%s %s: %s", src.name, d, e)
        return None
    _mark(s, src.key, d, True)
    return f


def _upsert_price(s: Session, iid: str, d: date, close: float, source: str, high=None, low=None, prev_close=None,
                  fetched_at=None) -> None:
    row = s.get(PriceDaily, (iid, d))
    if row is None:
        s.add(PriceDaily(instrument_id=iid, date=d, close=close, high=high, low=low, prev_close=prev_close, source=source,
                         fetched_at=fetched_at or utcnow()))
    elif row.close != close:   # a correction: keep the newest published value, note when it was fetched
        row.close, row.high, row.low, row.prev_close, row.source = close, high, low, prev_close, source
        row.fetched_at = fetched_at or utcnow()


def _kind_for(row: parse.BhavRow) -> str:
    n = row.name.upper()
    if row.series == "GB" or n.startswith("SGB"):
        return "sgb"
    if row.instrument_type == "ETF" or "ETF" in n or "BEES" in row.symbol.upper():
        return "etf"
    return "stock"


def tracked(s: Session, kinds: tuple[str, ...]) -> list[Instrument]:
    return list(s.scalars(select(Instrument).where(Instrument.tracked.is_(True), Instrument.kind.in_(kinds))))


# --------------------------------------------------------------------------- masters

def refresh_masters(s: Session, max_lookback: int = 7) -> dict:
    """Stock/ETF/SGB list from the latest NSE bhavcopy (BSE-only listings added from BSE), fund list from AMFI."""
    stats = {"stocks": 0, "funds": 0}
    by_isin = {i.isin: i for i in s.scalars(select(Instrument).where(Instrument.kind.in_(("stock", "etf", "sgb"))))}
    for src, exch in ((sources.NSE_BHAV, "NSE"), (sources.BSE_BHAV, "BSE")):
        for d in sorted(weekdays_back(today_ist(), max_lookback), reverse=True):
            f = _fetch_day(s, src, d)
            if not f:
                continue
            for r in parse.parse_bhav_udiff(f.text):
                if exch == "NSE" and r.series not in parse.NSE_EQUITY_SERIES:
                    continue
                if not r.isin:
                    continue
                inst = by_isin.get(r.isin)
                if inst is None:
                    inst = Instrument(kind=_kind_for(r), key=r.isin, isin=r.isin, symbol=r.symbol, exchange=exch, name=r.name.title())
                    s.add(inst)
                    by_isin[r.isin] = inst
                    stats["stocks"] += 1
            break
    by_code = {i.key: i for i in s.scalars(select(Instrument).where(Instrument.kind == "mf"))}
    f = sources.fetch(sources.AMFI_NAV, use_cache=False)
    for sc in parse.parse_amfi_navall(f.text):
        inst = by_code.get(sc.code)
        if inst is None:
            inst = Instrument(kind="mf", key=sc.code, isin=sc.isin_growth, name=sc.name, amc=sc.amc, category=sc.category,
                              plan=sc.plan, option=sc.option)
            s.add(inst)
            by_code[sc.code] = inst
            stats["funds"] += 1
        else:
            inst.category, inst.amc = sc.category or inst.category, sc.amc or inst.amc
    if s.scalar(select(Instrument).where(Instrument.kind == "index", Instrument.key == BENCHMARK)) is None:
        s.add(Instrument(kind="index", key=BENCHMARK, name="Nifty 50", symbol="NIFTY 50", tracked=True))
    s.flush()
    return stats


# --------------------------------------------------------------------------- prices

def _gold_ref_instrument(s: Session) -> Instrument:
    from finadvisor.portfolio.others import GOLD_REF_KEY
    inst = s.scalar(select(Instrument).where(Instrument.kind == "index", Instrument.key == GOLD_REF_KEY))
    if inst is None:
        inst = Instrument(kind="index", key=GOLD_REF_KEY, name="Gold reference (999, per gram)", tracked=True)
        s.add(inst)
        s.flush()
    return inst


def store_bhav_day(s: Session, f: sources.Fetched, wanted: dict[str, Instrument]) -> int:
    from finadvisor.portfolio.others import GOLD_REF_SOURCE, gold_reference_from_bhav
    n = 0
    rows = parse.parse_bhav_udiff(f.text)
    if f.source.key == "nse_bhav" and rows:
        ref = gold_reference_from_bhav(rows)
        if ref:
            _upsert_price(s, _gold_ref_instrument(s).id, rows[0].trade_date, ref, GOLD_REF_SOURCE, fetched_at=f.fetched_at)
    by_symbol = {(i.exchange or "NSE", i.symbol): i for i in wanted.values() if i.symbol}
    for r in rows:
        # ISINs change on splits and face-value changes; NSE symbols do not, so fall back to the symbol.
        inst = wanted.get(r.isin) or (by_symbol.get((r.exchange, r.symbol)) if r.series in parse.NSE_EQUITY_SERIES
                                      or r.exchange == "BSE" else None)
        if inst is None or (inst.exchange and inst.exchange != r.exchange and r.exchange):
            continue
        _upsert_price(s, inst.id, r.trade_date, r.close, f.source.name, r.high, r.low, r.prev_close, f.fetched_at)
        n += 1
    return n


def store_index_day(s: Session, f: sources.Fetched, bench: Instrument) -> int:
    for r in parse.parse_index_close(f.text):
        if r.name.upper() == BENCHMARK:
            _upsert_price(s, bench.id, r.trade_date, r.close, "NSE Indices daily close (price index)", fetched_at=f.fetched_at)
            return 1
    return 0


def derive_and_store_actions(s: Session, inst: Instrument) -> int:
    rows = [(p.date, p.close, p.prev_close) for p in
            s.scalars(select(PriceDaily).where(PriceDaily.instrument_id == inst.id).order_by(PriceDaily.date))]
    n = 0
    for a in derive_actions(rows):
        if s.scalar(select(CorporateAction).where(CorporateAction.instrument_id == inst.id,
                                                  CorporateAction.ex_date == a.ex_date)) is None:
            s.add(CorporateAction(instrument_id=inst.id, ex_date=a.ex_date, kind=classify(a.factor), factor=a.factor,
                                  source="derived: exchange bhavcopy previous close",
                                  note=f"previous close published on {a.ex_date} differs from the prior day's close by factor {a.factor:.4f}"))
            n += 1
    return n


def backfill_listed(s: Session, insts: list[Instrument], days: int = BACKFILL_DAYS, end: date | None = None) -> int:
    """Fill daily prices for listed instruments from the exchange archives (cached on disk). Also stores the daily
    gold reference rate from the NSE file, so it runs even when no stock is tracked."""
    end = end or today_ist()
    by_exch: dict[str, dict[str, Instrument]] = {"NSE": {}, "BSE": {}}
    if not insts:
        for d in weekdays_back(end, days):
            f = _fetch_day(s, sources.NSE_BHAV, d)
            if f:
                store_bhav_day(s, f, {})
            s.commit()
        return 0
    for i in insts:
        by_exch[i.exchange or "NSE"][i.isin] = i
    n = 0
    for exch, src in (("NSE", sources.NSE_BHAV), ("BSE", sources.BSE_BHAV)):
        wanted = by_exch[exch]
        if not wanted:
            continue
        for d in weekdays_back(end, days):
            f = _fetch_day(s, src, d)
            if f:
                n += store_bhav_day(s, f, wanted)
            s.commit()   # short transactions: the website keeps working while history loads
    for i in insts:
        derive_and_store_actions(s, i)
    return n


def backfill_index(s: Session, days: int = BACKFILL_DAYS, end: date | None = None) -> int:
    bench = s.scalar(select(Instrument).where(Instrument.kind == "index", Instrument.key == BENCHMARK))
    if bench is None:
        return 0
    have = {p for p in s.scalars(select(PriceDaily.date).where(PriceDaily.instrument_id == bench.id))}
    n = 0
    for d in weekdays_back(end or today_ist(), days):
        if d in have:
            continue
        f = _fetch_day(s, sources.NSE_INDICES, d)
        if f:
            n += store_index_day(s, f, bench)
        s.commit()
    return n


def backfill_fund(s: Session, inst: Instrument) -> int:
    """Full NAV history for one scheme from MFapi.in (which republishes AMFI's NAV history)."""
    r = httpx.get(f"https://api.mfapi.in/mf/{inst.key}", headers={"User-Agent": sources.UA}, timeout=60)
    r.raise_for_status()
    n = 0
    fetched = utcnow()
    for row in r.json().get("data", []):
        try:
            d = datetime.strptime(row["date"], "%d-%m-%Y").date()
            nav = float(row["nav"])
        except (KeyError, ValueError):
            continue
        if nav > 0:
            _upsert_price(s, inst.id, d, nav, "MFapi.in (AMFI NAV history)", fetched_at=fetched)
            n += 1
    return n


def update_funds_latest(s: Session) -> int:
    funds = {i.key: i for i in tracked(s, ("mf",))}
    if not funds:
        return 0
    f = sources.fetch(sources.AMFI_NAV, use_cache=False)
    n = 0
    for sc in parse.parse_amfi_navall(f.text):
        inst = funds.get(sc.code)
        if inst and sc.nav and sc.nav_date:
            _upsert_price(s, inst.id, sc.nav_date, sc.nav, sources.AMFI_NAV.name, fetched_at=f.fetched_at)
            n += 1
    return n


def needed_days(s: Session, inst: Instrument) -> int:
    """History must reach the earliest transaction or watch date of anyone tracking the instrument (min 400 days)."""
    from finadvisor.db.models import Transaction, WatchItem
    first = min([d for d in (s.scalar(select(func.min(Transaction.trade_date)).where(Transaction.instrument_id == inst.id)),
                             s.scalar(select(func.min(WatchItem.added_on)).where(WatchItem.instrument_id == inst.id))) if d],
                default=today_ist())
    return max(BACKFILL_DAYS, (today_ist() - first).days + 10)


def has_history(s: Session, inst: Instrument, days: int) -> bool:
    earliest = s.scalar(select(func.min(PriceDaily.date)).where(PriceDaily.instrument_id == inst.id))
    latest = s.scalar(select(func.max(PriceDaily.date)).where(PriceDaily.instrument_id == inst.id))
    if earliest is None:
        return False
    # the first available trading day may be a few days after the requested start; latest must be recent
    if (today_ist() - earliest).days < days - 20 or (today_ist() - latest).days > 7:
        return False
    if inst.kind == "mf":
        return True
    # no holes: a row for (nearly) every day the exchange published since the first row
    src = "bse_bhav" if inst.exchange == "BSE" else "nse_bhav"
    published = s.scalar(select(func.count()).select_from(MarketDay).where(
        MarketDay.source == src, MarketDay.published.is_(True), MarketDay.date >= earliest))
    rows = s.scalar(select(func.count()).select_from(PriceDaily).where(PriceDaily.instrument_id == inst.id))
    return not published or rows >= 0.9 * published


def track(s: Session, inst: Instrument) -> None:
    """Start storing prices for an instrument and backfill its history (blocking; call from a worker)."""
    if not inst.tracked:
        inst.tracked = True
        s.commit()
    days = needed_days(s, inst)
    if has_history(s, inst, days):
        return
    if inst.kind == "mf":
        backfill_fund(s, inst)
    else:
        backfill_listed(s, [inst], days=days)
    s.commit()
    backfill_index(s, days=days)


def ensure_history(s: Session) -> int:
    """Heal tracked instruments whose history is missing or short (e.g. a backfill that failed earlier)."""
    n = 0
    for inst in tracked(s, ("stock", "etf", "sgb", "mf")):
        if not has_history(s, inst, needed_days(s, inst)):
            track(s, inst)
            n += 1
    return n


def daily(s: Session, lookback_days: int = 7) -> dict:
    """Fetch the last few days' files (fills gaps after downtime) and store prices for tracked instruments."""
    run = DataJobRun(job="daily", status="ok", detail={})
    s.add(run)
    detail: dict = {}
    listed = tracked(s, ("stock", "etf", "sgb"))
    try:
        detail["listed_rows"] = backfill_listed(s, listed, days=lookback_days)
    except Exception as e:  # noqa: BLE001 - keep going; the run is marked partial
        detail["listed_error"] = repr(e)
        run.status = "partial"
    try:
        detail["index_rows"] = backfill_index(s, days=lookback_days)
    except Exception as e:  # noqa: BLE001
        detail["index_error"] = repr(e)
        run.status = "partial"
    try:
        detail["healed"] = ensure_history(s)
    except Exception as e:  # noqa: BLE001
        detail["heal_error"] = repr(e)
        run.status = "partial"
    try:
        detail["fund_rows"] = update_funds_latest(s)
    except Exception as e:  # noqa: BLE001
        detail["fund_error"] = repr(e)
        run.status = "partial"
    run.detail, run.finished_at = detail, datetime.now(timezone.utc)
    return detail


def main(argv: list[str]) -> None:
    from finadvisor.db.base import Base, make_engine, make_sessionmaker
    from finadvisor.settings import get_settings
    logging.basicConfig(level=logging.INFO)
    engine = make_engine(get_settings().database_url)
    if get_settings().database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    with make_sessionmaker(engine)() as s:
        if argv and argv[0] == "masters":
            print(refresh_masters(s))
        else:
            if s.scalar(select(Instrument).limit(1)) is None:
                print(refresh_masters(s))
            print(daily(s))
        s.commit()


if __name__ == "__main__":
    main(sys.argv[1:])
