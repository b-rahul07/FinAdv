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
NOT_A_COUNT_AFTER = re.compile(r"\s*(%|percent\b|per\s?cent\b|pc\b|x\b|times\b|years?\b|yrs?\b|p\.?\s?a\b|"
                               r"per\s+(annum|year|month)\b|an?\s+(year|month)\b|(percentage\s+)?points?\b)", re.I)
NOT_A_COUNT_BEFORE = re.compile(r"(₹|\brs\.?|\binr)\s*$", re.I)
# Words that make a nearby small number a rate or an outcome ("an FD pays 7 per annum", "inflation runs near 6",
# "your money doubles in 6 months"). "points" is a cue too, so "3 points to remember" is dropped: the guard errs
# towards dropping a sentence.
RATE_WORDS = re.compile(r"\b(returns?|returned|interest|yields?|cagr|growth|grows?|rate|pays?|paid|doubles?|doubling|"
                        r"triples?|inflation|per annum|points?)\b", re.I)
# Numbers that are part of a name, not a figure: index names ("Nifty 50", "Nifty Midcap 150", "BSE 500") and tax
# sections ("Section 80C", "80CCD(1B)", "Section 24(b)"). The paper runs of 13 Nov 2026 showed every number the guard
# caught in the model's explanations was the 50 in "Nifty 50"; amounts next to a name ("₹1,50,000 under 80C") are
# still checked.
NAMES = re.compile(
    r"\bnifty\s+(?:next\s+)?(?:50|100|200|500)\b"
    r"|\bnifty\s+(?:midcap|smallcap|largemidcap|large\s*mid\s*cap|microcap)\s*\d{2,3}\b"
    r"|\b(?:s&p\s+)?bse\s+(?:100|200|500)\b|\bsensex\s+30\b"
    r"|\b(?:section|sec\.?|u/s)\s*\d+[a-z]*(?:\(\w+\))*"
    r"|\b80(?:c|ccc|ccd|d|dd|ddb|e|ee|eea|g|gg|tta|ttb|u)\b(?:\(\w+\))*", re.I)


# Numbers written as words ("twelve percent", "double in seven years", "two lakh"): the same rules as digits, so a
# model told to use no numbers cannot spell one out instead (review, 11 Nov 2026). Ordinals ("first") are not numbers.
_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
          "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
          "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SCALE = {"hundred": 100, "thousand": 1000, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "crore": 1e7, "crores": 1e7}
WORD_NUM = re.compile(
    r"(?<![\w-])(?:(?P<tens>" + "|".join(_TENS) + r")(?:[-\s](?P<unit2>" + "|".join(_UNITS) + r"))?"
    r"|(?P<unit>" + "|".join(_UNITS) + r"))"
    r"(?:\s+(?P<half>and\s+a\s+half))?(?:\s+(?P<scale>" + "|".join(_SCALE) + r"))?\b", re.I)


def _word_value(m: re.Match) -> float:
    g = m.groupdict()
    v = float(_TENS[g["tens"].lower()] + (_UNITS[g["unit2"].lower()] if g["unit2"] else 0)) if g["tens"] \
        else float(_UNITS[g["unit"].lower()])
    if g["half"]:
        v += 0.5
    if g["scale"]:
        v *= _SCALE[g["scale"].lower()]
    return v


def _numbers(sentence: str):
    """(text, value, start, end) for every number in a sentence, digits or words."""
    for m in NUM.finditer(sentence):
        yield m.group(0), _value(m), m.start(), m.end()
    for m in WORD_NUM.finditer(sentence):
        yield m.group(0), _word_value(m), m.start(), m.end()


def _is_count(sentence: str, start: int, end: int) -> bool:
    if NOT_A_COUNT_AFTER.match(sentence, end) or NOT_A_COUNT_BEFORE.search(sentence[:start]):
        return False
    return not RATE_WORDS.search(sentence[max(0, start - 25):end + 25])


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
            for _, v, _, _ in _numbers(x):
                add(v)
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
    names = [m.span() for m in NAMES.finditer(sentence)]
    for text, v, start, end in _numbers(sentence):
        if any(a <= start < b for a, b in names):
            continue
        if (v in SMALL_FREE and _is_count(sentence, start, end)) or round(v, 2) in allowed or round(v) in allowed:
            continue
        bad.append(text)
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
