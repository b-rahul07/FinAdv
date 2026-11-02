"""Compare FinAdvisor's adjusted 52-week high/low with NSE's published adjusted 52-week report.

Uses only the cached NSE bhavcopy files (data/market_raw/nse_bhav), so it makes at most one request (the report).

    python scripts/validate_52w.py 2026-10-30
"""

import sys
from collections import defaultdict
from datetime import date

from finadvisor.market import parse, sources
from finadvisor.market.jobs import weekdays_back
from finadvisor.portfolio import engine as E


def main(as_of: date, only: set[str] | None = None) -> None:
    rows: dict[str, list] = defaultdict(list)
    for d in weekdays_back(as_of, 400):
        p = sources._cache_path(sources.NSE_BHAV, d)
        if not p.exists():
            continue
        for r in parse.parse_bhav_udiff(sources.fetch(sources.NSE_BHAV, d).text):
            if r.series == "EQ":
                rows[r.symbol].append((r.trade_date, r.high, r.low, r.close, r.prev_close))
    report = {w.symbol: w for w in parse.parse_nse_52w(sources.fetch(sources.NSE_52W, as_of).text) if w.series == "EQ"}
    n = ok_hi = ok_lo = 0
    with_actions = []
    close_ok = []
    worst = []
    for sym, rs in rows.items():
        w = report.get(sym)
        if only and sym not in only:
            continue
        if not w or w.high is None or w.low is None or len(rs) < 200:
            continue
        rs.sort()
        acts = E.derive_actions([(d, c, p) for d, _, _, c, p in rs])
        res = E.week52([(d, h, l, c) for d, h, l, c, _ in rs], acts, as_of)
        if not res:
            continue
        lo, hi = res
        n += 1
        eh, el = abs(hi / w.high - 1), abs(lo / w.low - 1)
        ok_hi += eh <= 0.005
        ok_lo += el <= 0.005
        if acts:
            with_actions.append((sym, eh <= 0.005 and el <= 0.005, [round(a.factor, 4) for a in acts]))
        worst.append((max(eh, el), sym, round(hi, 2), w.high, round(lo, 2), w.low, len(acts)))
        closes = [c * E.factor_after(d, acts) for d, _, _, c, _ in rs if (as_of - d).days <= 364]
        close_ok.append(abs(max(closes) / w.high - 1) <= 0.005 or eh <= 0.005)
    print(f"compared {n} NSE EQ stocks as of {as_of}")
    print(f"52-week high within 0.5%: {ok_hi} ({ok_hi / n:.1%}); low within 0.5%: {ok_lo} ({ok_lo / n:.1%})")
    good = sum(1 for _, ok, _ in with_actions if ok)
    print(f"high within 0.5% using intraday high OR close: {sum(close_ok)} ({sum(close_ok) / n:.1%})")
    both = sum(1 for x in worst if x[0] <= 0.005)
    print(f"both high and low within 0.5%: {both} ({both / n:.1%}); within 2%: {sum(1 for x in worst if x[0] <= 0.02) / n:.1%}")
    print(f"stocks with a derived split/bonus: {len(with_actions)}; both ends match: {good}")
    print("examples with adjustments:", with_actions[:8])
    print("largest mismatches (err, sym, our hi, nse hi, our lo, nse lo, n_actions):")
    for x in sorted(worst, reverse=True)[:10]:
        print("  ", x)


if __name__ == "__main__":
    main(date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today(),
         set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None)
