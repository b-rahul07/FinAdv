"""Number guard: LLM prose may only repeat numbers that the calculators produced (brief §2.3)."""

from __future__ import annotations

import re
from typing import Iterable

# A number may not start inside a word or right after a dot ("v2"; "3.5" read as 5), except straight after a currency
# mark: "Rs.7,00,000" and "INR7,00,000" are amounts.
NUM = re.compile(r"(?:(?<![\w.])|(?<=\brs\.)|(?<=\brs)|(?<=\binr))(\d{1,3}(?:,\d{2,3})+|\d+)(?:\.(\d+))?\s*"
                 r"(lakh|lakhs|lac|crore|crores|cr|k)?", re.I)
SMALL_FREE = set(range(0, 13))  # counting words like "3 steps", "6 months"
SENTENCE = re.compile(r"(?<=[.!?])\s+")
# A small number is a free counting word only when nothing next to it makes it a rate, an amount or a duration:
# "Equity funds usually return 12% a year" and "double your money in 6 years" used to pass as counts.
NOT_A_COUNT_AFTER = re.compile(r"\s*(%|percent\b|per\s?cent\b|x\b|times\b|years?\b|yrs?\b|p\.?\s?a\b|"
                               r"per\s+(annum|year|month)\b|an?\s+(year|month)\b|(percentage\s+)?points?\b)", re.I)
NOT_A_COUNT_BEFORE = re.compile(r"(₹|\brs\.?|\binr)\s*$", re.I)
# Words that make a nearby small number a rate or an outcome ("an FD pays 7 per annum", "inflation runs near 6",
# "your money doubles in 6 months"). "points" is a cue too, so "3 points to remember" is dropped: the guard errs
# towards dropping a sentence.
RATE_WORDS = re.compile(r"\b(returns?|returned|interest|yields?|cagr|growth|grows?|rate|pays?|paid|doubles?|doubling|"
                        r"triples?|inflation|per annum|points?)\b", re.I)


def _is_count(sentence: str, m: re.Match) -> bool:
    if NOT_A_COUNT_AFTER.match(sentence, m.end()) or NOT_A_COUNT_BEFORE.search(sentence[:m.start()]):
        return False
    return not RATE_WORDS.search(sentence[max(0, m.start() - 25):m.end() + 25])


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
        if (v in SMALL_FREE and _is_count(sentence, m)) or round(v, 2) in allowed or round(v) in allowed:
            continue
        bad.append(m.group(0))
    return bad


def guard_sentences(chunks: Iterable[str], allowed: set[float], enforce: bool = True):
    """Re-chunk streamed text into sentences; yield (sentence, unapproved numbers). Dropped sentences yield ''.
    enforce=False (ablation A4) reports the unapproved numbers but lets every sentence through."""
    buf = ""
    for piece in chunks:
        buf += piece
        parts = SENTENCE.split(buf)
        for s in parts[:-1]:
            bad = unapproved(s, allowed)
            yield ("" if bad and enforce else s + " "), bad
        buf = parts[-1]
    if buf.strip():
        bad = unapproved(buf, allowed)
        yield ("" if bad and enforce else buf), bad
