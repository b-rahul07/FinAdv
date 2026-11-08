"""Direct answers for questions the general plan reply doesn't answer by itself (part of compose-v1).

Each topic returns the opening answer, which plan steps to list, and an optional "how to choose" guide with official
links. Numbers come from the profile, the plan, the capacity engine, the configs and the calculators; nothing here is
written by a model. Topics that need data FinAdvisor doesn't have (income-tax slabs) say so and point to the
official tool instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from statistics import median

from finadvisor.advisor import pressure
from finadvisor.advisor.fundfinder import ter_of
from finadvisor.advisor.gate import RISK_LABEL
from finadvisor.advisor.numbers import NUM, _value
from finadvisor.calc import goals as G
from finadvisor.calc.money import inr

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("switch_direct", re.compile(r"regular plans?|direct plans?|switch\w* (to |into )?direct|distributor|commission", re.I)),
    ("tax", re.compile(r"\btax\b|\btaxes\b|regime|\b80c\b|\b80d\b|deduction|\bitr\b", re.I)),
    ("market_fall", re.compile(r"markets? (is |are )?(fall|crash|down|drop|tank)|\b(stop|pause|cancel|break) (my |the |all )?sips?"
                               r"|\bcrash|\bcorrection\b|\bbear market", re.I)),
    ("lumpsum", re.compile(r"lump ?sum|lying (idle |around )?in|idle (money|cash)|\bbonus\b|windfall|one[- ]time"
                           r"|(sitting|kept|parked) in (my )?(savings|bank)", re.I)),
    ("portfolio", re.compile(r"portfolio|my (investments|holdings)|diversif|how (are|is) my (funds?|investments?|money|shares?)"
                             r" (doing|performing)", re.I)),
    ("returns", re.compile(r"what returns?|expected returns?|how much (will|would|can) (i|it|my money|this) (get|grow|make|earn|be)"
                           r"|returns? (can|will|should) i (expect|get)", re.I)),
    ("raise", re.compile(r"\b(salary )?(hike|raise|increment|appraisal|pay rise)\b", re.I)),
]
GOAL_WORDS: list[tuple[str, re.Pattern]] = [
    ("education", re.compile(r"educat|college|school|child|\bkids?\b|\bson\b|daughter", re.I)),
    ("home", re.compile(r"\bhouse\b|\bhome\b|\bflat\b|apartment|property|\brent", re.I)),
    ("vehicle", re.compile(r"\bcar\b|\bbike\b|vehicle|scooter", re.I)),
    ("marriage", re.compile(r"wedding|marriage", re.I)),
    ("travel", re.compile(r"travel|\btrip\b|vacation|holiday", re.I)),
]
WHEN_RETIRE = re.compile(r"when (can|could|will|would) i retire|retire (early|by|at|before)|\bfire\b", re.I)
PREPAY = re.compile(r"prepay|pre-pay|pay (it |them )?off|close (my |the )?loan|foreclos|part[- ]?pay|repay early", re.I)
CARD = re.compile(r"credit card|card (dues|bill|debt)", re.I)
CHOOSE = re.compile(r"\bwhich\b|what (kind|type|sort)|\bchoose\b|\bbest\b|\bbuy\b|\bpolicy\b|\bplans?\b|\bgood\b", re.I)
PCT = re.compile(r"(\d+(?:\.\d+)?)\s*(%|percent|per cent)", re.I)
COMPARE = re.compile(r"\bor\b|\bvs\.?\b|versus|better|compare|difference|between", re.I)
# Stable facts for side-by-side comparisons ("{ltcg}" is filled from the tax config).
FACTS = {
    "ppf": "money locked for 15 years (partial withdrawals from year 7); interest is tax-free",
    "elss": "each instalment locked for 3 years; long-term gains above {ltcg} a year are taxed at {rate}",
    "fixed_deposit": "fixed rate for the term; interest is taxed at your income-tax slab rate",
    "nps": "mostly locked until age 60; part must buy a pension then",
    "large_cap_index_fund": "no lock-in; long-term gains above {ltcg} a year are taxed at {rate}",
    "flexi_cap_fund": "no lock-in; long-term gains above {ltcg} a year are taxed at {rate}",
    "mid_small_cap_fund": "no lock-in, but meant for goals at least 7 years away; long-term gains above {ltcg} a year are "
                          "taxed at {rate}",
    "gold_etf_fund": "no lock-in; follows the gold price, which can stay flat for years",
}

EQUITY = {"direct_equity", "large_cap_index_fund", "flexi_cap_fund", "elss", "mid_small_cap_fund"}
DEBT = {"fixed_deposit", "recurring_deposit", "ppf", "epf_vpf", "liquid_fund", "short_duration_debt_fund", "savings_account"}
HYBRID = {"hybrid_baf", "nps"}
GOLD = {"gold_etf_fund"}
LOAN_NAME = {"home": "home loan", "car": "car loan", "personal": "personal loan", "education": "education loan",
             "two_wheeler": "two-wheeler loan", "gold": "gold loan", "bnpl": "BNPL dues", "other": "loan"}

LINK_TAX = ("Income Tax Department's official tax calculator", "https://www.incometax.gov.in/iec/foportal/income-tax-calculator")
LINK_MFC = ("MF Central (official, run by the registrars)", "https://www.mfcentral.com/")
LINK_POLICYHOLDER = ("IRDAI's policyholder guide (official)", "https://policyholder.gov.in/")
LINK_IRDAI = ("IRDAI annual reports: insurers' claim settlement records", "https://irdai.gov.in/")


@dataclass
class Ctx:
    question: str
    final: object
    profile: object
    cap: object
    bundle: object
    held: list[dict]
    snap: dict | None
    steps: list[str]                       # the plan's steps as numbered-list sentences

    @property
    def plan(self):
        return self.final.plan

    @property
    def c(self) -> dict:
        return self.bundle.rules["capacity"]

    def steps_for(self, *actions) -> list[str]:
        return [t for s, t in zip(self.plan.steps, self.steps) if s.action in actions]

    def step(self, action: str):
        return next((s for s in self.plan.steps if s.action == action), None)

    def invest_return(self) -> float | None:
        """The plan's expected return a year (percent), weighted by what goes into each bucket."""
        bs = [b for b in self.plan.buckets if b.monthly > 0 and b.assumed_return_pa is not None]
        if bs:
            return sum(b.monthly * b.assumed_return_pa for b in bs) / sum(b.monthly for b in bs)
        general = next((b for b in self.plan.buckets if b.id == "general" and b.assumed_return_pa is not None), None)
        return general.assumed_return_pa if general else None


@dataclass
class Topic:
    short: str
    pick: list[str] | None = None          # None: the caller's default (all steps)
    guide: list[tuple[str, list[str]]] = field(default_factory=list)   # (title, bullet lines)
    why: bool = True                       # add the "why this suits you" lines
    held: bool = False                     # add "what you already have"


def intent_of(question: str) -> str | None:
    if COMPARE.search(question) and len([p for p in pressure.products_in(question) if p in FACTS]) >= 2:
        return "compare"
    for name, pat in PATTERNS:
        if pat.search(question):
            return name
    if WHEN_RETIRE.search(question):
        return "retire_when"
    if any(p.search(question) for _, p in GOAL_WORDS):
        return "goal"
    return None


def _join(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def _link(label_url: tuple[str, str]) -> str:
    return f"[{label_url[0]}]({label_url[1]})"


def _pct(x: float, d: int = 0) -> str:
    return f"{x:.{d}%}"


def _years(months: int) -> str:
    y, m = divmod(months, 12)
    if not y:
        return f"{m} month{'s' if m != 1 else ''}"
    return f"{y} year{'s' if y != 1 else ''}" + (f" {m} month{'s' if m != 1 else ''}" if m else "")


def amounts_in(text: str) -> list[float]:
    """Rupee amounts written in a question ("2 lakh", "50k", "₹1,20,000"); percentages and small counts skipped."""
    out = []
    for m in NUM.finditer(text):
        if text[m.end():m.end() + 1] == "%" or re.match(r"\s*(%|percent|years?|months?|yrs?)\b", text[m.end():], re.I):
            continue
        v = _value(m)
        if v >= 1000:
            out.append(v)
    return out


# ---------------------------------------------------------------- topics

def compare(x: Ctx) -> Topic:
    decisions = {d.id: d for d in x.final.decisions}
    pids = [p for p in pressure.products_in(x.question) if p in FACTS and p in decisions]
    names = {p["id"]: p["name"] for p in x.bundle.shelf["products"]}
    fit = [p for p in pids if decisions[p].allowed]
    no = [p for p in pids if not decisions[p].allowed]

    def nm(ps):
        return _join([names[p] for p in ps])

    def reason(p):
        return decisions[p].reasons[0] if decisions[p].reasons else "it doesn't suit your profile yet"

    if fit and no:
        short = (f"{nm(fit)} suit{'s' if len(fit) == 1 else ''} you now. {nm(no)} "
                 f"{'doesn' if len(no) == 1 else 'don'}'t yet: {reason(no[0])}.")
    elif fit:
        short = (f"{'Both' if len(fit) == 2 else 'All of them'} suit your risk level, so the better one is the one that "
                 "matches when you'll need the money; see the comparison below.")
    else:
        short = f"Neither suits you yet: {reason(no[0])}. The steps below come first."
    later = [p for p in fit if decisions[p].after_priority]
    if later:
        short += f" {nm(later)} can start once the priority steps below are done."
    eq = x.bundle.tax["equity"]
    rets = x.bundle.assumptions["returns_pa"]
    lines = []
    for p in pids:
        d = decisions[p]
        risk = RISK_LABEL.get(d.product.get("riskometer"), "")
        r = rets.get(p, {}).get("value")
        fact = FACTS[p].format(ltcg=inr(eq["ltcg_annual_exemption_inr"]), rate=f"{eq['ltcg_rate']:.1%}".replace(".0%", "%"))
        lines.append(f"{names[p]}: {risk} risk; {fact}"
                     + (f"; FinAdvisor assumes about {r:g}% a year." if r is not None else "."))
    return Topic(short, pick=x.steps[:3], guide=[("Side by side", lines)])


def switch_direct(x: Ctx) -> Topic:
    regular = [f for h in x.held for f in h.get("regular", [])]
    eq = x.bundle.tax["equity"]
    guide = [("Before you switch", [
        "Start new SIPs in the Direct plan of the same fund now: it costs nothing and every new rupee pays the lower fee.",
        f"Moving money you already hold counts as selling, so gains are taxed. Equity fund units held more than "
        f"{eq['long_term_after_months']} months are long-term, and the first {inr(eq['ltcg_annual_exemption_inr'])} of "
        "long-term gains each year is tax-free, so switching in parts over a few years can avoid tax.",
        "Check the exit load (usually on units held under a year), and remember ELSS units are locked for 3 years.",
        f"Direct plans are bought on the fund house's own website or app, or on {_link(LINK_MFC)}.",
    ])]
    if regular:
        total = sum(f["value"] for f in regular)
        saving, priced = 0.0, 0
        for f in regular:
            t = ter_of(x.snap, f["name"])
            if t and t.get("regular") is not None and t.get("direct") is not None:
                saving += f["value"] * max(0.0, t["regular"] - t["direct"]) / 100
                priced += 1
        names = _join([f["name"] for f in regular[:3]] + ([f"{len(regular) - 3} more"] if len(regular) > 3 else []))
        short = (f"Yes, for new money at least. {len(regular)} of your funds are Regular plans ({inr(total)}): {names}. "
                 "A Direct plan is the same fund without the distributor's commission, so it charges less every year.")
        if priced:
            short += (f" On what you hold today, the Direct plans would cost about {inr(saving)} a year less "
                      f"(expense ratios from AMFI{'' if priced == len(regular) else f', {priced} of {len(regular)} funds priced'}).")
        return Topic(short, pick=[], guide=guide, why=False)
    diffs = [t["regular"] - t["direct"] for t in ((x.snap or {}).get("ter") or {}).values()
             if t.get("regular") is not None and t.get("direct") is not None]
    gap = f" Across the funds AMFI lists, the Direct plan costs a median {median(diffs):.2f} percentage points a year less." \
        if diffs else ""
    if sum(h.get("funds", 0) for h in x.held):
        short = "All the mutual funds in your Holdings are already Direct plans, so there's nothing to switch." + gap
        return Topic(short, pick=[], guide=[], why=False)
    short = ("A Direct plan is the same fund without the distributor's commission, so it charges less every year." + gap
             + " Add your funds under Holdings (or import your CAS statement) and I'll work out what switching saves you.")
    return Topic(short, pick=[], guide=guide, why=False)


def tax(x: Ctx) -> Topic:
    p = x.profile
    short = ("FinAdvisor doesn't calculate income tax yet, so I can't tell you which regime costs you less. The "
             f"{_link(LINK_TAX)} does, using your salary and deductions; it takes a few minutes.")
    lines = ["The new regime (the default) has lower rates but allows almost no deductions. The old regime has higher "
             "rates but lets you deduct things like EPF, PPF, ELSS, life and health insurance premiums and home-loan interest."]
    have = []
    if any(d.kind == "home" for d in p.debts):
        have.append("your home loan's interest and principal repayment")
    if p.health_cover > 0:
        have.append("your health insurance premium")
    if p.life_cover > 0:
        have.append("your life insurance premium")
    if have:
        lines.append(f"In your case, {_join(have)} would count only under the old regime. Add up what you'd deduct and "
                     "compare both regimes in the calculator.")
    lines.append("Don't buy a product just to save tax: under the new regime, ELSS, PPF and insurance premiums save no tax "
                 "at all, so pick them for what they do, not for the deduction.")
    in_plan = {m.product_id for b in x.plan.buckets for m in b.mix if m.monthly > 0}
    if in_plan & {"elss", "ppf", "nps", "epf_vpf"}:
        lines.append("Your plan already includes products that can also cut tax under the old regime; the amounts are on "
                     "the plan card.")
    return Topic(short, pick=x.steps_for("buy_health_cover", "buy_term_cover"), guide=[("What decides it", lines)],
                 why=False)


def market_fall(x: Ctx) -> Topic:
    short = ("Keep your SIPs going if the money is for a goal at least 5 years away. In a fall each instalment buys more "
             "units, and stopping turns a temporary drop into a missed recovery. Stop or pause only if you need the money "
             "within a few years or can't afford the instalment.")
    if "R1" in x.cap.rule_ids:
        short += (" In your case the plan already puts new money into your emergency fund first, which is the right thing "
                  "to do whatever the market does.")
    elif x.plan.investing_monthly > 0:
        short += f" Your plan invests {inr(x.plan.investing_monthly)} a month; nothing in it changes because markets fell."
    return Topic(short, pick=x.steps_for("invest") or x.steps[:2],
                 guide=[("If a fall worries you", [
                     "Money you need within 3 years shouldn't be in equity funds at all; your plan keeps it in steadier products.",
                     "Look at your goals, not daily prices: a SIP for a goal 10 years away has many recoveries ahead of it.",
                 ])])


def lumpsum(x: Ctx) -> Topic:
    p, c = x.profile, x.c
    target = c["emergency_months"] * p.expenses_monthly
    said = amounts_in(x.question)
    note = ""
    if said and abs(said[0] - p.liquid_savings) > 0.1 * max(said[0], 1):
        note = (f" (Your profile says your savings are {inr(p.liquid_savings)}. If you now have {inr(said[0])}, update "
                "your profile and I'll redo this with the new amount.)")
    deploy = x.step("deploy_excess_savings")
    if p.liquid_savings > target:
        excess = p.liquid_savings - target
        short = (f"Keep {inr(target)} ({c['emergency_months']} months of expenses) as your emergency fund, in a savings "
                 f"account or liquid fund. Invest the other {inr(excess)}"
                 + (f" in your plan's mix over 6 months, about {inr(deploy.monthly)} a month," if deploy else " in your plan's mix")
                 + " rather than all at once: spreading it out avoids putting everything in just before a fall.")
    elif p.liquid_savings >= target:
        short = (f"Keep your {inr(p.liquid_savings)} where it is: it is exactly your emergency fund of {c['emergency_months']} "
                 "months of expenses, so there's nothing extra to invest from it.")
    else:
        short = (f"Keep your savings as your emergency fund for now. Your {inr(p.liquid_savings)} covers {x.cap.E:.1f} months of "
                 f"expenses, short of the {c['emergency_months']} months ({inr(target)}) you need, so don't invest it "
                 "until that is full.")
    short += " Money you earn every month is best invested monthly, as a SIP." + note
    pick = x.steps_for("buy_health_cover", "clear_card_dues", "deploy_excess_savings", "build_emergency_fund") or x.steps[:3]
    return Topic(short, pick=pick)


def portfolio(x: Ctx) -> Topic:
    held = [h for h in x.held if h.get("value")]
    if not held:
        return Topic("I can't see any holdings yet. Add them under Holdings, or import your CAS statement, and I'll review "
                     "how they're doing, how they're spread and how they fit your risk level.", pick=[], why=False)
    v = sum(h["value"] for h in held)
    inv = sum(h.get("invested") or 0 for h in held)
    parts = [f"Your investments are worth {inr(v)}"]
    if inv > 0:
        g = v - inv
        parts[0] += (f"; you put in {inr(inv)}, so they are {'up' if g >= 0 else 'down'} {inr(abs(g))} "
                     f"({'+' if g >= 0 else '−'}{_pct(abs(g) / inv, 1)}).")
    else:
        parts[0] += "."
    share = {name: sum(h["value"] for h in held if h["product_id"] in ids) / v
             for name, ids in (("equity", EQUITY), ("debt and deposits", DEBT), ("hybrid and NPS", HYBRID), ("gold", GOLD))}
    split = [f"{_pct(s)} {name}" for name, s in share.items() if s >= 0.005]
    only = next((name for name, s in share.items() if s >= 0.995), None)
    if only:
        parts.append(f"All of it is in {only}" + (": a share of steadier products would soften big falls."
                                                    if only == "equity" else "."))
    elif split:
        parts.append(f"They are spread {_join(split)}.")
    shares = sum(h["value"] for h in held if h["product_id"] == "direct_equity") / v
    if shares >= 0.25:
        parts.append(f"{_pct(shares)} is in individual shares, which is a lot: a fall in a few companies would hit the "
                     "whole portfolio. Funds spread the same money over many companies.")
    top = held[0]
    if top["value"] / v >= 0.6 and top["product_id"] != "direct_equity":
        parts.append(f"Most of it ({_pct(top['value'] / v)}) is in one product type, so a problem there affects most of "
                     "your money.")
    if 0.85 <= share["equity"] < 0.995:
        parts.append("Almost everything is in equity; a share of steadier products softens big falls.")
    return Topic(" ".join(parts), pick=x.steps_for("invest") or x.steps[:3], held=True)


def returns(x: Ctx) -> Topic:
    r = x.invest_return()
    monthly = x.plan.investing_monthly
    if r is None or monthly <= 0:
        return Topic("Nothing in your plan is invested yet, so there's no return to estimate: the steps below come "
                     "first. Ask again once they're done, or see the plan card for when investing starts.")
    infl = x.bundle.assumptions["inflation_pa"]["value"]
    fv = G.fv_sip(monthly, r, 120)
    today = fv / G.inflate(1, infl, 10)
    rets = x.bundle.assumptions["returns_pa"]
    mix = {}
    for b in x.plan.buckets:
        for m in b.mix:
            if m.monthly > 0:
                mix[m.product_id] = rets.get(m.product_id, {}).get("value")
    names = {p["id"]: p["name"] for p in x.bundle.shelf["products"]}
    each = _join([f"{names.get(pid, pid).lower()} {v:g}%" for pid, v in mix.items() if v is not None])
    short = (f"About {r:.1f}% a year over the long run for your plan's mix. That is FinAdvisor's planning assumption, "
             f"not a promise: real returns rise and fall, especially in equity funds. At {inr(monthly)} a month, it would "
             f"grow to about {inr(fv)} in 10 years, of which {inr(monthly * 120)} is what you put in; in today's money "
             f"(after {infl:g}% inflation) that's about {inr(today)}.")
    set_on = x.bundle.assumptions.get("set_on")
    set_on = date.fromisoformat(str(set_on)) if set_on else None
    return Topic(short, pick=x.steps_for("invest"),
                 guide=[("Assumptions used", [f"Expected returns a year: {each}.",
                                              (f"Set on {set_on.day} {set_on:%b %Y}; " if set_on else "")
                                              + "deposit, PPF and EPF figures follow published rates; fund figures are "
                                              "long-run planning assumptions."])])


def raise_(x: Ctx) -> Topic:
    p = x.profile
    m = PCT.search(x.question)
    if m and p.take_home_monthly > 0:
        pct = float(m.group(1))
        extra = p.take_home_monthly * pct / 100
        short = (f"Congratulations. If your take-home rises {pct:g}% to about {inr(p.take_home_monthly + extra)} and your "
                 f"expenses stay the same, you'll have {inr(p.monthly_surplus + extra)} a month to plan with instead of "
                 f"{inr(p.monthly_surplus)}.")
    else:
        short = "Congratulations."
    short += (" Update your take-home pay on your profile and I'll redo the plan with it. Putting most of the raise to "
              "work before your spending grows into it is the easiest way to save more.")
    return Topic(short, pick=x.steps[:3])


def retire_when(x: Ctx) -> Topic | None:
    p = x.profile
    g = next((g for g in p.goals if g.kind == "retirement"), None)
    if g is None:
        return None          # compose's retirement answer asks for the goal
    b = next((b for b in x.plan.buckets if b.id == g.id), None)
    infl = x.bundle.assumptions["inflation_pa"]["value"]
    if not b or b.monthly <= 0 or b.assumed_return_pa is None:
        return Topic(f"Nothing goes to retirement yet: the steps below come first. Once they're done, retiring in "
                     f"{g.horizon_years:g} years as planned would take about "
                     f"{inr(b.sip_needed) if b and b.sip_needed else 'more than your current surplus'} a month.")
    n = G.months_to_target(b.monthly, b.assumed_return_pa, g.target_today, infl, g.saved_so_far, x.plan.invest_start_month)
    planned = int(round(g.horizon_years * 12))
    slow = ""
    if b.assumed_return_pa - infl < 1.5 and (n is None or n > planned + 6):
        slow = (f" At your risk level the plan's mix is expected to earn about {b.assumed_return_pa:.1f}% a year, close to "
                f"inflation ({infl:g}%), so savings barely grow in real terms.")
        f = x.final
        order = ["low", "medium", "high"]
        if f.capacity and f.willingness and f.willingness.level and \
                order.index(f.capacity.level) < order.index(f.willingness.level):
            slow += (" What holds it back is your capacity for loss, not your questionnaire: once the protection steps "
                     "below are done, your risk level can rise and the plan can use growth funds.")
    if n is None:
        short = (f"At {inr(b.monthly)} a month you wouldn't reach your retirement target of {inr(g.target_today)} (in "
                 f"today's money) within 60 years. Retiring in {g.horizon_years:g} years would take about "
                 f"{inr(b.sip_needed)} a month.")
    else:
        age = f", at about age {p.age + n // 12}" if p.age else ""
        short = (f"At {inr(b.monthly)} a month you'd reach your retirement target of {inr(g.target_today)} (in today's "
                 f"money, growing with inflation) in about {_years(n)}{age}.")
        if n > planned + 6 and b.sip_needed:
            short += (f" That's later than the {g.horizon_years:g} years you planned; retiring on time would take about "
                      f"{inr(b.sip_needed)} a month.")
        elif n <= planned:
            short += " That's on or before the date you planned."
    short += slow
    pick = x.steps_for("buy_health_cover", "buy_term_cover", "build_emergency_fund", "clear_card_dues") \
        + [t for s, t in zip(x.plan.steps, x.steps) if s.goal_id == g.id]
    return Topic(short, pick=pick or x.steps[:3])


def goal(x: Ctx) -> Topic:
    p, c = x.profile, x.c
    kind = next(k for k, pat in GOAL_WORDS if pat.search(x.question))
    words = next(pat for k, pat in GOAL_WORDS if k == kind)
    g = next((g for g in p.goals if g.kind == kind or words.search(g.name)), None)
    guide = []
    if kind == "home":
        room = max(0.0, c["emi_cap"] * p.take_home_monthly - p.total_emi)
        guide.append(("Buying a home", [
            f"Lenders look at EMIs: yours can rise by at most {inr(room)} a month before all EMIs pass "
            f"{c['emi_cap']:.0%} of take-home pay.",
            "Pay the down payment from savings meant for it, not from your emergency fund.",
            "Buying makes more sense the longer you expect to stay in one city; renting keeps you flexible and your "
            "savings invested. Add the home as a goal and I'll size the down payment.",
        ]))
    if g is None:
        short = ("Add it as a goal on your profile, with the amount in today's money and the years until you need it, and "
                 "I'll work out the monthly amount and a mix that suits that horizon.")
        return Topic(short, pick=x.steps[:3], guide=guide)
    b = next((b for b in x.plan.buckets if b.id == g.id), None)
    if b and b.monthly > 0:
        short = (f"Put about {inr(b.monthly)} a month towards '{g.name}'. Your target of {inr(g.target_today)} in today's "
                 f"money is about {inr(b.target_future)} after inflation in {g.horizon_years:g} years.")
        if b.sip_needed and not b.fundable:
            short += f" Fully funding it would take {inr(b.sip_needed)} a month, so this covers {b.monthly / b.sip_needed:.0%} for now."
    else:
        short = (f"Nothing goes to '{g.name}' yet: the steps below come first"
                 + (f". Funding it fully would take about {inr(b.sip_needed)} a month." if b and b.sip_needed else "."))
    return Topic(short, pick=[t for s, t in zip(x.plan.steps, x.steps) if s.goal_id == g.id] or x.steps[:3], guide=guide)


# --------------------------------------------------------- refinements of existing intents

def insurance_guide(x: Ctx) -> list[tuple[str, list[str]]]:
    if not CHOOSE.search(x.question):
        return []
    q = x.question.lower()
    want_term = bool(re.search(r"term|life", q))
    want_health = bool(re.search(r"health|medical|mediclaim|hospital", q)) or not want_term
    out = []
    if want_health:
        lines = []
        if x.profile.dependants:
            lines.append("A family floater covers you and your family in one policy; parents are usually better on a "
                         "separate policy, since their age raises the premium for everyone.")
        lines += [
            "Have your own policy even if your employer covers you: employer cover ends when you change jobs. A 'super "
            "top-up' adds a lot of cover cheaply above a base amount.",
            "Check before buying: no room-rent limit or disease-wise caps, the waiting period for pre-existing "
            "conditions, a restoration benefit, and whether hospitals near you are in the cashless network.",
            f"Compare insurers' claim settlement records in {_link(LINK_IRDAI)}; {_link(LINK_POLICYHOLDER)} explains "
            "your rights and how to complain.",
        ]
        out.append(("Choosing health insurance", lines))
    if want_term or (x.profile.dependants and not re.search(r"health|medical|mediclaim", q)):
        out.append(("Choosing term insurance", [
            "Buy a pure term plan (no maturity payout): it gives the most cover for the premium. Endowment and ULIP plans "
            "mix insurance with investing and give far less cover.",
            "Choose cover that lasts until your dependants no longer rely on your income, usually until about 60.",
            "Disclose your health and smoking honestly; hidden facts are the most common reason claims are refused.",
        ]))
    return out


def debt(x: Ctx) -> Topic | None:
    p = x.profile
    card = next((d for d in p.debts if d.kind == "credit_card"), None)
    if CARD.search(x.question):
        if card is None and p.card_dues_paid_in_full:
            return Topic("You have no unpaid credit-card balance on your profile. Keep paying the full bill by the due date "
                         "each month: card interest is the costliest debt most people ever pay.", pick=[], why=False)
        if card is not None:
            step = x.step("clear_card_dues")
            interest = card.outstanding * card.rate_pa / 1200 if card.rate_pa else None
            short = ("Clear it first. " + (f"At {card.rate_pa:g}% a year, your {inr(card.outstanding)} balance costs about "
                                           f"{inr(interest)} a month in interest. " if interest else "")
                     + (f"The plan pays it off in {step.months} months, {inr(step.monthly)} a month; after that, pay the full "
                        "bill every month." if step and step.monthly else "After that, pay the full bill every month."))
            return Topic(short, pick=x.steps_for("clear_card_dues") or x.steps[:2])
    if PREPAY.search(x.question):
        loans = [d for d in p.debts if d.kind != "credit_card" and d.outstanding > 0]
        if not loans:
            return Topic("You have no loans on your profile, so there's nothing to prepay.", pick=x.steps[:2], why=False)
        r = x.invest_return()
        d = max(loans, key=lambda d: d.rate_pa or 0)
        name = LOAN_NAME.get(d.kind, "loan")
        if not d.rate_pa or r is None:
            return None
        short = (f"Your {name} costs {d.rate_pa:g}% a year. Your plan's mix is expected to earn about {r:.1f}% (a planning "
                 "assumption, not a promise).")
        if d.rate_pa > r:
            short += (f" So prepaying part of the loan is the better use of spare money: it saves a sure {d.rate_pa:g}%. "
                      "Do it after your emergency fund and insurance are in place, and keep investing for goals with a date.")
        else:
            short += (" So investing is expected to earn more than prepaying saves; keep paying the EMI as usual. Prepay "
                      "only if being debt-free sooner matters more to you than the extra return.")
        guide = [("Good to know", [
            "Banks can't charge a prepayment penalty on floating-rate loans to individuals (RBI rule); fixed-rate loans may "
            "have one, so check your loan agreement.",
            "When you prepay, ask the bank to cut the tenure rather than the EMI: you save more interest.",
        ] + (["If you use the old tax regime, home-loan interest and principal are deductible, which lowers the loan's "
              "real cost a little."] if d.kind == "home" else []))]
        return Topic(short, pick=x.steps_for("clear_card_dues", "repay_costly_loan") or x.steps[:2], guide=guide)
    return None


TOPICS = {"compare": compare, "switch_direct": switch_direct, "tax": tax, "market_fall": market_fall, "lumpsum": lumpsum,
          "portfolio": portfolio, "returns": returns, "raise": raise_, "retire_when": retire_when, "goal": goal}
FOLLOWUPS = {
    "compare": ["Which mutual funds suit me?", "Make me a money plan"],
    "switch_direct": ["How is my portfolio doing?", "Which mutual funds suit me?"],
    "tax": ["Make me a money plan", "How much term insurance do I need?"],
    "market_fall": ["How is my portfolio doing?", "Make me a money plan"],
    "lumpsum": ["Do I have enough emergency savings?", "Which mutual funds suit me?"],
    "portfolio": ["My mutual funds are in regular plans, should I switch?", "Make me a money plan"],
    "returns": ["How much should I invest each month?", "Which mutual funds suit me?"],
    "raise": ["How much should I invest each month?", "Make me a money plan"],
    "retire_when": ["How much do I need to retire?", "Make me a money plan"],
    "goal": ["Make me a money plan", "How much should I invest each month?"],
}
