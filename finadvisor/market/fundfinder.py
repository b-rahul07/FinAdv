"""Fund finder snapshot: every Direct-Growth scheme of each shelf fund type, with facts computed by code.

    python -m finadvisor.market.fundfinder        # ~10 minutes: AMFI NAVs, AMFI expense ratios, NAV histories

Writes data/fund_finder.json, which the advisor's fund finder cards read (finadvisor/advisor/fundfinder.py).
Which schemes belong to which fund type is configs/fundfinder/<version>.yaml. Run weekly; AMFI publishes expense
ratios daily and NAVs every business day.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta

from finadvisor.advisor.fundfinder import SNAPSHOT, load_config, norm
from finadvisor.calc.returns import annualised_return
from finadvisor.db.base import utcnow
from finadvisor.market import parse, sources

log = logging.getLogger(__name__)
TER_HEADERS = {"Accept": "application/json, text/plain, */*", "Referer": "https://www.amfiindia.com/ter-of-mf-schemes"}


def matches(rule: dict, name: str, category: str) -> bool:
    cat = (category or "").lower()
    if not any(c in cat for c in rule["category"]):
        return False
    if rule.get("name") and not re.search(rule["name"], name, re.I):
        return False
    return not (rule.get("not_name") and re.search(rule["not_name"], name, re.I))


def pick(schemes: list[parse.Scheme], cfg: dict, today: date) -> dict[str, list[parse.Scheme]]:
    fresh = today - timedelta(days=cfg["fresh_nav_days"])
    out: dict[str, list[parse.Scheme]] = {pid: [] for pid in cfg["products"]}
    for sc in schemes:
        if (sc.plan or "") != cfg["plan"] or not (sc.option or "").lower().startswith(cfg["option"]):
            continue
        if not sc.nav or not sc.nav_date or sc.nav_date < fresh:
            continue
        for pid, rule in cfg["products"].items():
            if matches(rule, sc.name, sc.category):
                out[pid].append(sc)
    return out


def financial_year(d: date) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{start + 1}"


def fetch_ter(today: date) -> tuple[str | None, dict[str, dict]]:
    """Latest month's TER per scheme, in percent: ("November-2026", {norm(name): {"direct", "regular", "date"}})."""
    months = sources.get_json(sources.AMFI_TER_MONTHS.url, {"year": financial_year(today)}, TER_HEADERS) or \
        sources.get_json(sources.AMFI_TER_MONTHS.url, {"year": financial_year(today - timedelta(days=40))}, TER_HEADERS)
    if not months:
        return None, {}
    month = months[0]
    out: dict[str, dict] = {}
    page, pages = 1, 1
    while page <= pages:
        j = sources.get_json(sources.AMFI_TER.url, {"MF_ID": "All", "Month": month["MonthNumber"], "strCat": "-1",
                                                     "strType": "-1", "page": page, "pageSize": 100}, TER_HEADERS)
        pages = j["meta"]["pageCount"]
        for r in j["data"]:
            try:
                direct, day = float(r["D_TER"]), r["TER_Date"][:10]
            except (KeyError, TypeError, ValueError):
                continue
            try:
                regular = float(r["R_TER"])
            except (KeyError, TypeError, ValueError):
                regular = None
            key = norm(r["Scheme_Name"])
            if key not in out or day > out[key]["date"]:   # one row per scheme per day: keep the latest
                out[key] = {"direct": direct, "regular": regular, "date": day}
        page += 1
    return month["MonthYear"], out


def nav_history(code: str) -> list[tuple[date, float]]:
    rows = sources.get_json(sources.MFAPI.url.format(code=code)).get("data", [])
    out = []
    for r in rows:
        try:
            d, nav = datetime.strptime(r["date"], "%d-%m-%Y").date(), float(r["nav"])
        except (KeyError, ValueError):
            continue
        if nav > 0:
            out.append((d, nav))
    return sorted(out)


def build(today: date | None = None) -> dict:
    cfg = load_config()
    today = today or date.today()
    navall = sources.fetch(sources.AMFI_NAV, use_cache=False)
    picked = pick(parse.parse_amfi_navall(navall.text), cfg, today)
    try:
        ter_month, ter = fetch_ter(today)
    except Exception as e:  # noqa: BLE001 - fall back to the last good figures below
        log.warning("AMFI TER unavailable: %s", e)
        ter_month, ter = None, {}
    if not ter:   # keep the previous run's expense ratios rather than showing none
        prev = previous()
        if prev.get("ter"):
            ter, ter_month = prev["ter"], prev.get("ter_month")
            log.warning("using the previous run's expense ratios (%s)", ter_month)
    histories: dict[str, list[tuple[date, float]] | None] = {}
    products = {}
    for pid, schemes in picked.items():
        rows = []
        for sc in schemes:
            if sc.code not in histories:
                try:
                    histories[sc.code] = nav_history(sc.code)
                except Exception as e:  # noqa: BLE001 - returns shown as unavailable for this scheme
                    log.warning("NAV history for %s unavailable: %s", sc.code, e)
                    histories[sc.code] = None
            hist = histories[sc.code]
            t = ter.get(norm(sc.name))
            returns = None
            if hist:
                returns = {}
                for y in (1, 3, 5):
                    r = annualised_return(hist, y)
                    returns[f"{y}y"] = round(r, 4) if r is not None else None
            rows.append({
                "code": sc.code, "name": sc.name, "amc": sc.amc, "category": sc.category,
                "nav": sc.nav, "nav_date": sc.nav_date.isoformat(),
                "expense_ratio": t["direct"] if t else None, "expense_ratio_date": t["date"] if t else None,
                "since": hist[0][0].isoformat() if hist else None,
                "returns": returns,
            })
        rows.sort(key=lambda f: (f["expense_ratio"] is None, f["expense_ratio"] or 0, f["name"].lower()))
        products[pid] = {"label": cfg["products"][pid]["label"], "total": len(rows), "funds": rows}
    return {
        "version": cfg["version"], "built_at": utcnow().isoformat(),
        "sources": {"nav": f"{sources.AMFI_NAV.name}, as of {max((sc.nav_date for v in picked.values() for sc in v), default=today):%d %b %Y}",
                    "expense_ratio": f"{sources.AMFI_TER.name}, {ter_month}" if ter_month else None,
                    "returns": f"Computed by FinAdvisor from {sources.MFAPI.name}"},
        "products": products,
        # Every scheme's Regular and Direct TER, for "what would switching to Direct save me" on funds people hold
        "ter": ter,
        "ter_month": ter_month,
    }


def previous() -> dict:
    try:
        return json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write(snap: dict) -> None:
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    tmp = SNAPSHOT.with_suffix(".tmp")
    tmp.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(SNAPSHOT)   # readers never see a half-written file


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    snap = build()
    write(snap)
    for pid, p in snap["products"].items():
        with_ter = sum(f["expense_ratio"] is not None for f in p["funds"])
        print(f"{pid:26} {p['total']:3} funds, {with_ter:3} with expense ratio")
    print("written", SNAPSHOT)


if __name__ == "__main__":
    main()
