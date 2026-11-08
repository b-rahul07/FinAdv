"""Fund finder cards: the real schemes of each fund type in a plan, with facts computed by code.

Display only: the plan, gate and audit never read it. The card lists every matching scheme in a neutral order
(lowest expense ratio first) and never picks one; the language model never sees or names the schemes.
The snapshot is built by `python -m finadvisor.market.fundfinder`.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from finadvisor.configs import CONFIG_DIR, _load_yaml
from finadvisor.settings import ROOT

SNAPSHOT = ROOT / "data" / "fund_finder.json"
VERSION = "fundfinder-v1"
STALE_AFTER = timedelta(days=10)
NOTE = ("These are all the {label_lower} FinAdvisor found in AMFI's data, cheapest first. They are not a "
        "recommendation: compare them yourself, and check the fund's own documents before investing.")


def norm(name: str) -> str:
    """Scheme names differ in case and punctuation between AMFI's NAV and TER files."""
    return re.sub(r"[^a-z0-9]+", " ", name.lower().replace("&", " and ")).strip()


def ter_of(snap: dict | None, scheme_name: str) -> dict | None:
    """{"direct", "regular", "date"} expense ratios (percent) for a scheme, from AMFI via the snapshot."""
    return ((snap or {}).get("ter") or {}).get(norm(scheme_name))


@lru_cache(maxsize=4)
def load_config(version: str = VERSION) -> dict:
    data = _load_yaml(CONFIG_DIR / "fundfinder" / f"{version.removeprefix('fundfinder-')}.yaml")
    if data.get("version") != version:
        raise ValueError(f"fund finder config declares {data.get('version')!r}, expected {version!r}")
    return data


class FundFinder:
    """Reads the snapshot, re-reading it when the weekly job replaces the file."""

    def __init__(self, path: Path = SNAPSHOT):
        self.path = path
        self._snap: dict | None = None
        self._mtime: float | None = None
        self._lock = threading.Lock()

    def __call__(self) -> dict | None:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return None
        with self._lock:
            if self._snap is None or mtime != self._mtime:
                try:
                    self._snap, self._mtime = json.loads(self.path.read_text(encoding="utf-8")), mtime
                except (OSError, ValueError):
                    return self._snap
            return self._snap


def card(product_id: str, snap: dict | None, cfg: dict | None = None) -> dict | None:
    cfg = cfg or load_config()
    p = (snap or {}).get("products", {}).get(product_id)
    if not p or not p["funds"] or product_id not in cfg["products"]:
        return None
    built = datetime.fromisoformat(snap["built_at"])
    return {
        "type": "fund_finder",
        "product_id": product_id,
        "label": p["label"],
        "total": p["total"],
        "funds": p["funds"][:cfg["show"]],
        "checklist": cfg["checklist"]["all"] + cfg["checklist"].get(product_id, []),
        "links": cfg["links"],
        "note": NOTE.format(label_lower=p["label"].lower()),
        "sources": snap["sources"],
        "built_at": snap["built_at"],
        "stale": datetime.now(timezone.utc) - built > STALE_AFTER,
    }


def cards_for(products: list[str], snap: dict | None) -> list[dict]:
    """One card per mutual-fund type in `products`, in the plan's order."""
    if not snap:
        return []
    cfg = load_config()
    return [c for pid in dict.fromkeys(products) if (c := card(pid, snap, cfg))]


def record(cards: list[dict], snap: dict | None) -> dict | None:
    """What the person was shown, for advice_runs.record."""
    if not cards:
        return None
    return {"version": snap["version"], "built_at": snap["built_at"], "sources": snap["sources"],
            "shown": {c["product_id"]: [f["code"] for f in c["funds"]] for c in cards}}
