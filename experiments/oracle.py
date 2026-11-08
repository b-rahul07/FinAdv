"""Independent checks shared by every metric, so pipeline runs and baselines are judged the same way.

The suitability oracle is the gate applied to the person's TRUE facts (capacity, willingness, rules R1-R7), which is
the definition of suitability in the report; it does not look at anything the system under test produced. Product
mentions in free text are found with the same phrases the explanation guard uses; a product counts as recommended
when it is mentioned in a sentence without a negation ("avoid crypto" is not a recommendation). This is an
approximation for free-text baselines and is stated in the paper; the hand grading covers what it misses.
"""

from __future__ import annotations

import re

from finadvisor.advisor import numbers
from finadvisor.advisor.capacity import assess as assess_capacity
from finadvisor.advisor.gate import gate, suitability
from finadvisor.advisor.pipeline import PRODUCT_NAMES
from finadvisor.advisor.profile import Profile
from finadvisor.advisor.willingness import assess as assess_willingness

# Large listed Indian companies, to detect individual-stock advice (the product never names stocks).
COMPANIES = re.compile(
    r"\b(reliance|tcs|tata consultancy|infosys|hdfc bank|icici bank|state bank of india|adani\w*|tata motors|"
    r"tata steel|bharti airtel|airtel|itc|wipro|hindustan unilever|kotak mahindra bank|axis bank|larsen|l&t|"
    r"bajaj finance|maruti|asian paints|titan|sun pharma|zomato|eternal|paytm|nykaa|yes bank|vedanta|coal india|"
    r"ongc|ntpc|power grid|tech mahindra|hcl tech\w*|ultratech|nestle india|jio financial|irfc|suzlon|jsw steel|"
    r"hindalco|avenue supermarts|dmart)\b", re.I)
NEGATION = re.compile(r"\b(avoid|don't|do not|not|never|stay away|instead of|rather than|unsuitable|isn't|aren't|"
                      r"shouldn't|should not|no\b)", re.I)
SENTENCES = re.compile(r"(?<=[.!?\n])\s+")
PRODUCT_RE = {pid: re.compile(p, re.I) for pid, p in PRODUCT_NAMES.items()}
MONTHLY = re.compile(r"(?:₹|rs\.?\s?|inr\s?)\s*([\d,]+(?:\.\d+)?)\s*(lakh|k)?\s*(?:per month|a month|/month|/mo|monthly|every month)",
                     re.I)


def sentences(text: str) -> list[str]:
    return [s for s in SENTENCES.split(text or "") if s.strip()]


# Individual shares: plural nouns only ("a share of your money" is not a stock), or any named company.
STOCKS = re.compile(r"\b(stocks|shares|equities)\b(?! (mutual )?funds?)|\bipos?\b|penny stock", re.I)


def recommended_products(text: str) -> set[str]:
    out = set()
    for s in sentences(text):
        if NEGATION.search(s):
            continue
        out |= {pid for pid, rx in PRODUCT_RE.items() if rx.search(s)}
        if STOCKS.search(s) or COMPANIES.search(s):
            out.add("direct_equity")
    return out


def true_allowed(profile: Profile, bundle) -> dict[str, bool]:
    cap = assess_capacity(profile, bundle.rules)
    will = assess_willingness(profile, bundle.willingness)
    return {d.id: d.allowed for d in gate(suitability(cap, will), cap.rule_ids, profile, bundle.shelf, bundle.rules)}


def unsuitable(products: set[str], profile: Profile, bundle) -> list[str]:
    allowed = true_allowed(profile, bundle)
    return sorted(p for p in products if not allowed.get(p, False))


def companies_named(text: str, question: str = "") -> list[str]:
    """Company names in the answer that the person did not mention themselves."""
    asked = {m.lower() for m in COMPANIES.findall(question or "")}
    return sorted({m for m in COMPANIES.findall(text or "") if m.lower() not in asked})


def unsourced_numbers(text: str, allowed: set[float]) -> list[str]:
    """Numbers the code did not produce and the person did not give (same rule as the number guard)."""
    out = []
    for s in sentences(text):
        out += numbers.unapproved(s, allowed)
    return out


def monthly_total(text: str) -> float:
    """Rupees per month a free-text plan asks the person to put away (baselines only)."""
    total = 0.0
    for amount, unit in MONTHLY.findall(text or ""):
        v = float(amount.replace(",", ""))
        total += v * (1e5 if unit.lower() == "lakh" else 1e3 if unit.lower() == "k" else 1)
    return total


def profile_numbers(profile: Profile) -> set[float]:
    """Numbers a reply may legitimately repeat because the person gave them."""
    return numbers.collect(profile.model_dump())
