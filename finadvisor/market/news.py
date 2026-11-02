"""Market headlines for the advisor's "What I looked at" panel.

Headlines come from the public RSS feeds the prototype used (ET Markets, Moneycontrol) and are scored with FinBERT
(ProsusAI/finbert, the prototype's sentiment model). They are context only: news never changes a plan, and no
user data is sent anywhere (the feeds are fetched without any query).

The desk keeps one cached snapshot on disk and refreshes it in a background thread when it is older than
`max_age_s`, so an advice answer never waits for the network or the model."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

from finadvisor.settings import ROOT

log = logging.getLogger(__name__)

FEEDS = {
    "ET Markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "Moneycontrol": "https://www.moneycontrol.com/rss/MCtopnews.xml",
}
CACHE = ROOT / "data" / "news" / "latest.json"
UA = "Mozilla/5.0 (compatible; FinAdvisor/1.0; research prototype)"
FINBERT = "ProsusAI/finbert"
POSITIVE_ABOVE, NEGATIVE_BELOW = 0.2, -0.2   # the prototype's thresholds for the overall mood

# Which headlines are relevant to a product in an answer. Anything else falls back to general market news.
TOPICS: dict[str, re.Pattern] = {
    "equity": re.compile(r"\b(stocks?|shares?|sensex|nifty|equit\w*|market|ipo|smallcap|midcap|largecap)", re.I),
    "funds": re.compile(r"mutual fund|\bsip\b|\bamc\b|\bnav\b|fund", re.I),
    "gold": re.compile(r"\bgold|silver|bullion", re.I),
    "rates": re.compile(r"\brbi\b|repo|interest rate|inflation|\bfd\b|deposit|bond|yield", re.I),
    "crypto": re.compile(r"crypto|bitcoin|ethereum", re.I),
    "fno": re.compile(r"\bf&o\b|derivative|options|futures|expiry", re.I),
}
PRODUCT_TOPICS = {
    "direct_equity": "equity", "large_cap_index_fund": "equity", "flexi_cap_fund": "funds", "elss": "funds",
    "mid_small_cap_fund": "equity", "hybrid_baf": "funds", "gold_etf_fund": "gold", "fixed_deposit": "rates",
    "recurring_deposit": "rates", "short_duration_debt_fund": "rates", "liquid_fund": "rates", "ppf": "rates",
    "crypto": "crypto", "fno": "fno",
}


def _when(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def fetch(client: httpx.Client | None = None, per_feed: int = 25) -> list[dict]:
    import feedparser   # optional dependency (the prototype's)
    out: list[dict] = []
    own = client is None
    client = client or httpx.Client(timeout=15, headers={"User-Agent": UA}, follow_redirects=True)
    try:
        for name, url in FEEDS.items():
            try:
                r = client.get(url)
                r.raise_for_status()
            except httpx.HTTPError as e:
                log.warning("news feed %s unavailable: %s", name, e)
                continue
            for e in feedparser.parse(r.text).entries[:per_feed]:
                title = (getattr(e, "title", "") or "").strip()
                if title:
                    out.append({"headline": title, "source": name, "url": e.get("link") or None,
                                "published": _when(e.get("published"))})
    finally:
        if own:
            client.close()
    return out


_classifier = None
_clf_lock = threading.Lock()


def classify(headlines: list[dict]) -> list[dict]:
    """Adds FinBERT 'mood' (positive | negative | neutral) and 'confidence'. Leaves them None if the model is missing."""
    global _classifier
    try:
        with _clf_lock:
            if _classifier is None:
                from transformers import pipeline
                _classifier = pipeline("sentiment-analysis", model=FINBERT)
            res = _classifier([h["headline"] for h in headlines], truncation=True) if headlines else []
    except Exception as e:  # noqa: BLE001 - headlines are still worth showing without a mood
        log.warning("FinBERT unavailable (%s); headlines shown without mood", e)
        return [{**h, "mood": None, "confidence": None} for h in headlines]
    return [{**h, "mood": r["label"].lower(), "confidence": round(float(r["score"]), 3)} for h, r in zip(headlines, res)]


def overall(items: list[dict]) -> str | None:
    scored = [(1 if h["mood"] == "positive" else -1 if h["mood"] == "negative" else 0) * h["confidence"]
              for h in items if h.get("mood")]
    if not scored:
        return None
    m = sum(scored) / len(scored)
    return "positive" if m > POSITIVE_ABOVE else "negative" if m < NEGATIVE_BELOW else "mixed"


class NewsDesk:
    """Cached headlines; `get` is instant and never touches the network on the caller's thread."""

    def __init__(self, path: Path = CACHE, max_age_s: int = 3 * 3600, fetcher=fetch, classifier=classify,
                 isolate: bool | None = None):
        self.path, self.max_age_s = path, max_age_s
        self._fetch, self._classify = fetcher, classifier
        # Refresh in a separate process by default: loading FinBERT (PyTorch) inside the API process held the
        # interpreter for tens of seconds and stalled the first answers after a restart. Tests inject fakes in-thread.
        self.isolate = (fetcher is fetch and classifier is classify) if isolate is None else isolate
        self._lock = threading.Lock()
        self._busy = False
        self._proc: subprocess.Popen | None = None
        self._snap: dict | None = None
        self._mtime: float | None = None

    def snapshot(self) -> dict | None:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return self._snap
        if self._snap is None or mtime != self._mtime:    # re-read after a refresh (possibly by another process)
            try:
                self._snap, self._mtime = json.loads(self.path.read_text(encoding="utf-8")), mtime
            except (OSError, ValueError):
                pass
        return self._snap

    def refresh(self) -> dict:
        items = self._classify(self._fetch())
        snap = {"fetched_at": datetime.now(timezone.utc).isoformat(), "model": FINBERT, "items": items}
        if items:   # keep the last good snapshot when every feed failed
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
            self._snap = snap
        return snap

    def _refresh_bg(self) -> None:
        with self._lock:
            if self.isolate:
                if self._proc is not None and self._proc.poll() is None:
                    return
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                self._proc = subprocess.Popen([sys.executable, "-m", "finadvisor.market.news", str(self.path)],
                                              cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                              creationflags=flags)
                return
            if self._busy:
                return
            self._busy = True

        def run():
            try:
                self.refresh()
            except Exception as e:  # noqa: BLE001
                log.warning("news refresh failed: %s", e)
            finally:
                self._busy = False
        threading.Thread(target=run, name="news-refresh", daemon=True).start()

    def get(self, products: list[str], k: int = 6) -> dict:
        snap = self.snapshot()
        age = None
        if snap:
            age = time.time() - datetime.fromisoformat(snap["fetched_at"]).timestamp()
        if snap is None or age > self.max_age_s:
            self._refresh_bg()
        if not snap:
            return {"as_of": None, "stale": True, "items": [], "mood": None, "source": ", ".join(FEEDS)}
        topics = [PRODUCT_TOPICS[p] for p in products if p in PRODUCT_TOPICS]
        items = snap["items"]
        picked = [h for h in items if any(TOPICS[t].search(h["headline"]) for t in dict.fromkeys(topics))]
        seen = {h["headline"] for h in picked}
        picked += [h for h in items if h["headline"] not in seen]   # top up with general market news
        picked = picked[:k]
        return {"as_of": snap["fetched_at"], "stale": age > 2 * self.max_age_s, "items": picked,
                "mood": overall(picked), "model": snap.get("model"), "source": ", ".join(FEEDS),
                "topics": list(dict.fromkeys(topics))}


if __name__ == "__main__":   # python -m finadvisor.market.news [cache path]: one refresh (also usable from cron)
    logging.basicConfig(level=logging.WARNING)
    NewsDesk(Path(sys.argv[1]) if len(sys.argv) > 1 else CACHE, isolate=False).refresh()
