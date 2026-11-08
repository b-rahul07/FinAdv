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
# Negation governs only the product right after it in the same clause ("avoid crypto"), not the whole sentence:
# "Don't wait: start a small-cap SIP" and "choose a no-cost EMI and invest the rest in crypto" recommend products.
NEGATION = re.compile(r"\b(avoid(?:ing)?|don'?t|do not|does not|doesn'?t|not|never|nor|no(?!-)|stay away from|"
                      r"steer clear of|skip|instead of|rather than|unsuitable|isn'?t|aren'?t|shouldn'?t|should not|"
                      r"can'?t|cannot|without|stop|exit|keep away from|other than|before|"   # "before buying X"
                      # the person's own words echoed back, and harm reduction for a choice they make anyway
                      r"you asked about|you mentioned|if you (?:still )?(?:want|decide|choose|insist) to)\b", re.I)
NEG_WINDOW = 6   # words between the negation and the product it governs
# Clause boundaries: a negation never crosses these.
CLAUSE = re.compile(r"[;:()]|\s[-–—]\s|\b(?:but|however|though|although|whereas|yet|while|then|so)\b|"
                    r"\band\s+(?=(?:put|invest|buy|start|choose|keep|add|use|go|consider|pick|move|allocate|park|try|"
                    r"get|open|hold|begin|switch|shift)\b)", re.I)
# Within a clause, a negation carries across commas into a list ("avoid crypto, small caps and F&O") but not into a
# part with its own instruction ("avoid FDs, buy Reliance shares").
RECOMMEND = re.compile(r"\b(put|invest|buy|start|choose|keep|add|use|go for|consider|pick|move|allocate|park|try|"
                       r"get|open|hold|begin|switch|shift|you can|you could|you should)\b", re.I)
# A mention followed by a warning is not a recommendation: "crypto is not regulated", "small caps are too risky".
WARNING_AFTER = re.compile(r"^\W*(?:\w+\W+){0,2}?(?:(?:is|are|can be|remains?)\s+(?:\w+\s+)?"
                           r"(?:not|risky|riskier|speculative|unregulated|volatile|unsuitable|dangerous|a gamble|"
                           r"gambling|too|unsafe|high[- ]risk|personali[sz]ed advice)|lost|lose|loses|losing)\b",
                           re.I)   # "F&O traders lost money"; "choosing specific shares is personalised advice"
# A clause that rules out what the clause before it named: "an index fund gets you that; today it is rated Very High
# risk, above what your profile allows".
DISQUALIFY = re.compile(r"above what your profile allows|not (?:yet )?suitable for you|isn'?t suitable for you|"
                        r"doesn'?t suit you|does not suit you|outside (?:what )?your (?:risk|profile)", re.I)
SENTENCES = re.compile(r"(?<=[.!?\n])\s+")
# The explanation guard's product phrases, plus wordings free-text baselines use that the guard never meets
# ("Trading options: ₹10,000 per month" from qwen2.5:3b, 9 Nov).
# A generic "equity mutual fund" is read as a diversified equity fund (flexi-cap: same Very High riskometer); a
# generic "debt mutual fund" as a short-duration debt fund. Stated in the paper; the hand labels check it.
ORACLE_EXTRA = {"fno": r"trading options|options? trading|derivatives|intraday",
                "crypto": r"cryptocurrenc\w*|ethereum|\bdogecoin",
                "flexi_cap_fund": r"\bequity (?:mutual )?funds?\b|diversified equity|\bequity sips?\b|\bequity mfs?\b",
                "short_duration_debt_fund": r"\bdebt mutual funds?\b"}
PRODUCT_RE = {pid: re.compile(p + (f"|{ORACLE_EXTRA[pid]}" if pid in ORACLE_EXTRA else ""), re.I)
              for pid, p in PRODUCT_NAMES.items()}
MONTHLY = re.compile(r"(?:₹|rs\.?\s?|inr\s?)\s*([\d,]+(?:\.\d+)?)\s*(lakh|k)?\s*(?:per month|a month|/month|/mo|monthly|every month)",
                     re.I)


def sentences(text: str) -> list[str]:
    return [s for s in SENTENCES.split(text or "") if s.strip()]


# Individual shares: plural nouns only ("a share of your money" is not a stock), or any named company.
STOCKS = re.compile(r"\b(stocks|shares|equities)\b(?! (mutual )?funds?)|\bipos?\b|penny stock", re.I)


def _mentions(part: str):
    """(product id, start, end) for every product, stock or company mention in a piece of text."""
    for pid, rx in PRODUCT_RE.items():
        for m in rx.finditer(part):
            yield pid, m.start(), m.end()
    for rx in (STOCKS, COMPANIES):
        for m in rx.finditer(part):
            yield "direct_equity", m.start(), m.end()


def _negated(part: str, start: int, inherited: bool) -> bool:
    before = part[:start]
    for m in NEGATION.finditer(before):
        if len(before[m.end():].split()) <= NEG_WINDOW:
            return True
    return inherited


def _clauses(sentence: str) -> list[tuple[str, str | None]]:
    """(clause, the boundary before it) for a sentence."""
    out, last, delim = [], 0, None
    for m in CLAUSE.finditer(sentence):
        out.append((sentence[last:m.start()], delim))
        delim, last = m.group(0).strip().lower(), m.end()
    out.append((sentence[last:], delim))
    return out


def clause_parts(sentence: str):
    """Yield (clause index, comma part, inherited negation) for a sentence. A negation carries across commas into a
    list, and across a colon into the list it introduces ("not used for now: NPS, gold funds"), but never into a
    part with an instruction of its own ("don't wait: start a SIP")."""
    carry = False
    for ci, (clause, delim) in enumerate(_clauses(sentence)):
        if delim != ":":
            carry = False
        if not clause.strip():
            continue
        for part in clause.split(","):
            # an instruction no negation governs ("buy Reliance shares") starts afresh; "do not invest in" does not
            free = [m for m in RECOMMEND.finditer(part) if not _negated(part, m.start(), False)]
            inherited = carry and not free
            yield ci, part, inherited
            negs = list(NEGATION.finditer(part))
            last_neg = negs[-1].end() if negs else -1
            carry = (inherited or bool(negs)) and not any(m.start() > last_neg for m in free)


def recommended_products(text: str) -> set[str]:
    """Products (and individual stocks, as direct_equity) the text recommends: mentioned without a negation that
    governs them, not followed by a warning, and not ruled out by the next clause. Measured against hand labels
    (experiments/grading.py oracle-score)."""
    out = set()
    for s in sentences(text):
        parts = list(clause_parts(s))
        ruled_out = {ci - 1 for ci, part, _ in parts if DISQUALIFY.search(part) and not any(_mentions(part))}
        for ci, part, inherited in parts:
            if ci in ruled_out:
                continue
            for pid, start, end in _mentions(part):
                if _negated(part, start, inherited) or WARNING_AFTER.match(part[end:]):
                    continue
                out.add(pid)
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


def monthly_amounts(text: str, own: set[float] = frozenset()) -> tuple[list[float], list[float]]:
    """(amounts the text asks the person to put away each month, amounts left out because they are the person's own
    figures). "With your ₹50,000 a month salary, put ₹10,000 a month in a SIP" puts away ₹10,000, not ₹60,000.
    A plan amount that happens to equal one of the person's figures is left out too (stated in the paper)."""
    kept, skipped = [], []
    for amount, unit in MONTHLY.findall(text or ""):
        v = float(amount.replace(",", "")) * (1e5 if unit.lower() == "lakh" else 1e3 if unit.lower() == "k" else 1)
        (skipped if round(v) in own or round(v, 2) in own else kept).append(v)
    return kept, skipped


def monthly_total(text: str, own: set[float] = frozenset()) -> float:
    """Rupees per month a free-text plan asks the person to put away (baselines only)."""
    return sum(monthly_amounts(text, own)[0])


def profile_numbers(profile: Profile) -> set[float]:
    """Numbers a reply may legitimately repeat because the person gave them."""
    return numbers.collect(profile.model_dump())


def own_figures(profile: Profile, surplus: bool = True) -> set[float]:
    """The person's own monthly figures (pay, spending, EMIs and, for free text, the surplus), which a plan quotes but
    does not put away. The ALLOCATION block keeps an item equal to the surplus (investing all of it is a plan)."""
    vals = [profile.take_home_monthly, profile.expenses_monthly, *([profile.monthly_surplus] if surplus else []),
            *(d.emi_monthly for d in profile.debts), sum(d.emi_monthly for d in profile.debts)]
    return {round(v) for v in vals if v} | {round(v, 2) for v in vals if v}


# Baselines end with a fixed block so they can be judged on a structured plan, as the pipeline is:
#   ALLOCATION
#   Nifty 50 index fund: ₹5,000 per month
ALLOCATION = re.compile(r"^\s*\**\s*allocation\s*\**\s*:?\s*$", re.I | re.M)
ALLOC_LINE = re.compile(r"^\s*[-*•\d.)]*\s*(.+?)\s*[:\-–—]\s*\**\s*(?:₹|rs\.?\s?|inr\s?)\s*([\d,]+(?:\.\d+)?)\s*"
                        r"(lakh|k)?([^\n]*)", re.I | re.M)
PER_MONTH = re.compile(r"^\W*(?:per month|a month|/\s?month|/\s?mo\b|monthly|every month|pm\b|p\.m\.)", re.I)
# Lines that restate what the person already pays rather than put money away. An EMI line counts only for the part
# above their current EMIs (a prepayment); spending lines never count.
EMI_LINE = re.compile(r"\bemis?\b|loan (?:re)?payments?|\brepay", re.I)
SPEND_LINE = re.compile(r"\brent\b|living expenses|household|groceries|\bbills\b|expenses", re.I)
# ...unless the line puts money away: "Emergency fund (6 months of expenses)", "Household buffer savings".
SAVE_WORDS = re.compile(r"\b(emergency|funds?|save|saving|savings|buffer|sips?|invest\w*|deposits?)\b", re.I)


def allocation(text: str) -> list[tuple[str, float, bool]] | None:
    """[(item, rupees, per month?)] from the ALLOCATION block, or None when the text has no such block. An amount
    without a monthly unit ("Emergency Savings: ₹10,80,000 (no monthly deposit needed)", "Wedding: ₹14,40,000 in 2
    years") is kept but marked, and never counted as money put away each month."""
    m = None
    for m in ALLOCATION.finditer(text or ""):
        pass
    if m is None:
        return None
    out = []
    for name, amount, unit, rest in ALLOC_LINE.findall(text[m.end():]):
        v = float(amount.replace(",", "")) * (1e5 if unit.lower() == "lakh" else 1e3 if unit.lower() == "k" else 1)
        out.append((name.strip(" *"), v, bool(PER_MONTH.match(rest))))
    return out


def allocation_total(items: list[tuple[str, float, bool]], profile: Profile) -> tuple[float, list[str]]:
    """(rupees a month the block puts away, lines left out and why)."""
    emis = sum(d.emi_monthly for d in profile.debts)
    own = own_figures(profile, surplus=False)   # an item equal to the surplus is kept: investing all of it is a plan
    total, skipped = 0.0, []
    for name, v, monthly in items:
        if not monthly:
            skipped.append(f"{name}: not monthly")
        elif EMI_LINE.search(name):
            total += max(0.0, v - emis)
            if v <= emis:
                skipped.append(f"{name}: existing EMIs")
        elif (SPEND_LINE.search(name) and not SAVE_WORDS.search(name)) or round(v) in own:
            skipped.append(f"{name}: the person's own figure")
        else:
            total += v
    return total, skipped


def allocation_products(items: list[tuple[str, float, bool]]) -> set[str]:
    out = set()
    for name, amount, monthly in items:
        if amount <= 0 or not monthly:
            continue
        out |= {pid for pid, rx in PRODUCT_RE.items() if rx.search(name)}
        if STOCKS.search(name) or COMPANIES.search(name):
            out.add("direct_equity")
    return out
