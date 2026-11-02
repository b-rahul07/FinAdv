"""Number guard: LLM prose may only repeat numbers that the calculators produced (brief §2.3)."""

from __future__ import annotations

import re
from typing import Iterable

NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+|\d+)(?:\.(\d+))?\s*(lakh|lakhs|lac|crore|crores|cr|k)?", re.I)
SMALL_FREE = set(range(0, 13))  # counting words like "3 steps", "6 months"
SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _value(m: re.Match) -> float:
    whole = float(m.group(1).replace(",", ""))
    frac = m.group(2)
    v = whole + (float("0." + frac) if frac else 0)
    unit = (m.group(3) or "").lower()
    if unit in ("lakh", "lakhs", "lac"):
        v *= 1e5
    elif unit in ("crore", "crores", "cr"):
        v *= 1e7
    elif unit == "k":
        v *= 1e3
    return v


def collect(obj) -> set[float]:
    """All numbers in a nested structure, plus forms prose commonly uses (rounded, %, lakh)."""
    out: set[float] = set()

    def add(v: float):
        out.add(round(v, 2))
        out.add(round(v))
        if abs(v) <= 1:                      # shares -> percentages
            out.add(round(v * 100))
            out.add(round(v * 100, 1))
        if abs(v) >= 1e5:
            out.add(round(v / 1e5, 1) * 1e5)
            out.add(round(v / 1e5, 2) * 1e5)
        if abs(v) >= 1e7:
            out.add(round(v / 1e7, 2) * 1e7)

    def walk(x):
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            add(float(x))
        elif isinstance(x, str):
            for m in NUM.finditer(x):
                add(_value(m))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple, set)):
            for v in x:
                walk(v)
        elif hasattr(x, "__dict__"):
            walk(vars(x))

    walk(obj)
    return out


def unapproved(sentence: str, allowed: set[float]) -> list[str]:
    bad = []
    for m in NUM.finditer(sentence):
        v = _value(m)
        if v in SMALL_FREE or round(v, 2) in allowed or round(v) in allowed:
            continue
        bad.append(m.group(0))
    return bad


def guard_sentences(chunks: Iterable[str], allowed: set[float]):
    """Re-chunk streamed text into sentences; yield (sentence, dropped_numbers). Dropped sentences yield ''."""
    buf = ""
    for piece in chunks:
        buf += piece
        parts = SENTENCE.split(buf)
        for s in parts[:-1]:
            bad = unapproved(s, allowed)
            yield ("" if bad else s + " "), bad
        buf = parts[-1]
    if buf.strip():
        bad = unapproved(buf, allowed)
        yield ("" if bad else buf), bad
