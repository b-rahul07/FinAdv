"""Downloads with a disk cache. Each official file is fetched at most once and kept (gzip) under
data/market_raw/<source>/, so backfilling a newly tracked instrument needs no new requests.

NSE and BSE reject non-browser clients on their public download archives, so a standard browser user agent is
sent; requests are spaced at least `MIN_INTERVAL_S` apart (brief §5: fetch politely, never more often than the
source updates)."""

from __future__ import annotations

import gzip
import io
import threading
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from finadvisor.settings import ROOT

RAW_DIR = ROOT / "data" / "market_raw"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
MIN_INTERVAL_S = 1.0

_lock = threading.Lock()
_last = 0.0


@dataclass
class Source:
    key: str
    name: str            # shown to users as the data source
    url: str             # template; {d:%Y%m%d} etc.
    zipped: bool = False
    expect: str = ""     # the file must start with this; anything else (an HTML error page) means "not published"


NSE_BHAV = Source("nse_bhav", "NSE bhavcopy",
                  "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip", zipped=True,
                  expect="TradDt")
BSE_BHAV = Source("bse_bhav", "BSE bhavcopy",
                  "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{d:%Y%m%d}_F_0000.CSV",
                  expect="TradDt")
NSE_INDICES = Source("nse_indices", "NSE Indices daily close",
                     "https://nsearchives.nseindia.com/content/indices/ind_close_all_{d:%d%m%Y}.csv", expect="Index Name")
NSE_52W = Source("nse_52w", "NSE adjusted 52-week high/low",
                 "https://nsearchives.nseindia.com/content/CM_52_wk_High_low_{d:%d%m%Y}.csv")
AMFI_NAV = Source("amfi_nav", "AMFI daily NAV", "https://portal.amfiindia.com/spages/NAVAll.txt", expect="Scheme Code")
# The JSON service behind AMFI's "TER of MF Schemes" page (undocumented; 100 rows a page, one row per scheme per day).
AMFI_TER = Source("amfi_ter", "AMFI total expense ratio (TER)", "https://www.amfiindia.com/api/populate-te-rdata-revised")
AMFI_TER_MONTHS = Source("amfi_ter_months", "AMFI TER months", "https://www.amfiindia.com/api/populate-ter-month")
MFAPI = Source("mfapi", "MFapi.in (AMFI NAV history)", "https://api.mfapi.in/mf/{code}")


class NotPublished(Exception):
    """The source has no file for that date (holiday, weekend, or not yet published)."""


@dataclass
class Fetched:
    text: str
    source: Source
    for_date: date | None
    fetched_at: datetime
    cached: bool


def _cache_path(src: Source, d: date | None) -> Path:
    stamp = d.isoformat() if d else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    return RAW_DIR / src.key / f"{stamp}.txt.gz"


def _get(url: str, params: dict | None = None, headers: dict | None = None) -> httpx.Response:
    global _last
    with _lock:
        wait = MIN_INTERVAL_S - (time.monotonic() - _last)
        if wait > 0:
            time.sleep(wait)
        _last = time.monotonic()
    return httpx.get(url, params=params, headers={"User-Agent": UA, "Accept": "*/*", **(headers or {})}, timeout=60,
                     follow_redirects=True)


def get_json(url: str, params: dict | None = None, headers: dict | None = None, tries: int = 3):
    """A JSON API call, spaced like file downloads, retried on network errors (a dropped DNS lookup once lost a
    whole run's expense ratios). Not cached: callers keep what they need."""
    for attempt in range(tries):
        try:
            r = _get(url, params, headers)
            r.raise_for_status()
            return r.json()
        except httpx.TransportError:
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def fetch(src: Source, d: date | None = None, *, use_cache: bool = True) -> Fetched:
    path = _cache_path(src, d)
    if use_cache and path.exists():
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return Fetched(gzip.decompress(path.read_bytes()).decode("utf-8", errors="replace"), src, d, mtime, True)
    r = _get(src.url.format(d=d) if d else src.url)
    if r.status_code == 404 or (r.status_code == 200 and len(r.content) < 200 and b"<html" in r.content.lower()):
        raise NotPublished(f"{src.name} has no file for {d}")
    r.raise_for_status()
    try:
        if src.zipped:
            z = zipfile.ZipFile(io.BytesIO(r.content))
            text = z.read(z.namelist()[0]).decode("utf-8", errors="replace")
        else:
            text = r.content.decode("utf-8", errors="replace")
    except zipfile.BadZipFile:
        raise NotPublished(f"{src.name}: not a file for {d}") from None
    if src.expect and not text.lstrip("\ufeff \r\n").startswith(src.expect):
        raise NotPublished(f"{src.name}: no file for {d} (got a web page instead)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(text.encode("utf-8")))
    return Fetched(text, src, d, datetime.now(timezone.utc), False)
