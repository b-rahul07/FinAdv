"""Question-first answer text for Plan replies (template `compose-v1@<hash>`).

Every reply opens with a direct answer to what was asked, using the person's own numbers, then a short numbered
"What to do" list taken from the computed plan, then at most three reasons tied to their situation. All numbers come
from the plan, the capacity engine and the configs; nothing here is written by a model. The full plan card, health
check and what-if sit under "Details" in the app.

Intents are matched on the question: emergency fund, retirement, mutual funds, how much to invest, insurance, debt,
or a general plan.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from finadvisor.advisor import topics
from finadvisor.advisor.gate import RISK_LABEL, risk_rank
from finadvisor.calc.money import inr

INTENTS: list[tuple[str, re.Pattern]] = [
    ("emergency", re.compile(r"emergency|rainy[- ]day|safety net|\bbuffer\b", re.I)),
    ("retirement", re.compile(r"retire|pension|old age", re.I)),
    ("insurance", re.compile(r"insurance|term (plan|cover|insurance)|health cover|life cover|mediclaim", re.I)),
    ("debt", re.compile(r"\bloans?\b|\bemis?\b|prepay|\bdebt|credit card", re.I)),
    ("funds", re.compile(r"\bfunds?\b|mutual|\bsips?\b|schemes?|where (should|can|do) i (invest|put)", re.I)),
    ("how_much", re.compile(r"how much (should|can|do|could) i (invest|save|put)", re.I)),
]

SHORT = {
    "fixed_deposit": "bank FD", "recurring_deposit": "recurring deposit", "ppf": "PPF", "epf_vpf": "EPF/VPF",
    "liquid_fund": "liquid fund", "short_duration_debt_fund": "short-duration debt fund", "nps": "NPS",
    "hybrid_baf": "balanced advantage fund", "gold_etf_fund": "gold ETF or gold fund",
    "large_cap_index_fund": "Nifty 50 index fund", "flexi_cap_fund": "flexi-cap fund", "elss": "ELSS fund",
    "mid_small_cap_fund": "mid/small-cap fund",
}
FUND_KINDS = {"fund"}

FOLLOWUPS = {
    "plan": ["Do I have enough emergency savings?", "Which mutual funds suit me?", "How much should I invest each month?"],
    "emergency": ["Make me a money plan", "Where should I keep my emergency fund?"],
    "retirement": ["Make me a money plan", "Which mutual funds suit me?"],
    "funds": ["Why not small-cap funds?", "Make me a money plan"],
    "how_much": ["Which mutual funds suit me?", "Do I have enough emergency savings?"],
    "insurance": ["Make me a money plan", "Do I have enough emergency savings?"],
    "debt": ["Make me a money plan", "Should I prepay my loan or invest?"],
}


def template_id() -> str:
    """Hash of this file and topics.py, the two halves of the reply template."""
    text = "".join(Path(f).read_text(encoding="utf-8").replace(chr(13), "") for f in (__file__, topics.__file__))
    return f"compose-v1@{hashlib.sha256(text.encode()).hexdigest()[:8]}"


def intent_of(question: str) -> str:
    for name, pat in INTENTS:
        if pat.search(question):
            return name
    return "plan"


def _months(n: int) -> str:
    if n < 12 or n % 12:
        return f"{n} month{'s' if n != 1 else ''}"
    y = n // 12
    return f"{y} year{'s' if y != 1 else ''}"


def _join(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def _parts(bucket) -> str:
    return _join([f"{inr(m.monthly)} in a {SHORT.get(m.product_id, m.product_id)}" for m in bucket.mix if m.monthly > 0])


def cap(when: str, verb: str) -> str:
    """'From month 13, invest' or 'Invest'."""
    return f"{when}{verb.lower()}" if when else verb


def held_line(held: list[dict], ceiling_level: str, bundle) -> str | None:
    """'You already have ₹13,88,279 invested: ...'. Flags how much of it is rated above the person's risk level."""
    total = sum(h["value"] for h in held)
    if total <= 0:
        return None
    rules = bundle.rules
    risk = {p["id"]: p.get("riskometer") for p in bundle.shelf["products"]}
    names = [f"{inr(h['value'])} in {SHORT.get(h['product_id'], 'shares' if h['product_id'] == 'direct_equity' else h['product_id'])}"
             for h in held[:5]]
    more = len(held) - len(names)
    line = (f"You already have {inr(total)} invested: "
            + (", ".join(names) + f" and {more} more." if more else _join(names) + "."))
    above = sum(h["value"] for h in held if risk_rank(risk.get(h["product_id"]), rules) > risk_rank(ceiling_level, rules))
    if above / total >= 0.25:
        line += (f" About {above / total:.0%} of it is in products rated above your risk level, so new money goes to "
                 "steadier products to balance it; you don't have to sell anything.")
    return line


def todo(plan, profile, rules) -> list[str]:
    """The plan steps as short, numbered actions (amounts from the plan)."""
    buckets = {b.id: b for b in plan.buckets}
    out = []
    for s in plan.steps:
        when = f"From month {s.start_month}, " if s.start_month > 1 else ""
        if s.action == "buy_health_cover":
            out.append(f"Get health insurance of at least {inr(s.target + profile.health_cover)} for yourself"
                       + (" and your family" if profile.dependants else "") + ".")
        elif s.action == "buy_term_cover":
            out.append(f"Buy term life cover of about {inr(s.target + profile.life_cover)}, so the people who depend on "
                       "you are protected.")
        elif s.action == "build_emergency_fund":
            out.append(f"{cap(when, "Save")} {inr(s.monthly)} a month for {_months(s.months)} in a savings account or liquid fund "
                       "until your emergency fund is complete." if s.monthly > 0 else
                       "Cut expenses first: right now they use all of your take-home pay, so nothing is left to save.")
        elif s.action == "invest" and s.goal_id:
            b = buckets.get(s.goal_id)
            out.append(f"{cap(when, "Put")} {inr(s.monthly)} a month towards '{b.name}': {_parts(b)}." if b else s.text)
        elif s.action == "invest":
            b = buckets.get("general")
            out.append(f"{cap(when, "Invest")} {inr(s.monthly)} a month for the long term: {_parts(b)}." if b else s.text)
        elif s.action == "deploy_excess_savings":
            out.append(f"Move the extra {inr(s.target)} sitting in savings into the same mix over 6 months, about "
                       f"{inr(s.monthly)} a month, instead of all at once.")
        else:
            out.append(s.text)
    return out


def _fund_lines(plan, bundle) -> list[str]:
    kind = {p["id"]: p["kind"] for p in bundle.shelf["products"]}
    totals: dict[str, float] = {}
    for b in plan.buckets:
        for m in b.mix:
            if m.monthly > 0 and kind.get(m.product_id) in FUND_KINDS:
                totals[m.product_id] = totals.get(m.product_id, 0) + m.monthly
    return [f"{SHORT.get(pid, pid)} ({inr(v)} a month)" for pid, v in sorted(totals.items(), key=lambda x: -x[1])]


def answer(question: str, final, profile, cap, bundle, held: list[dict] | None = None, fund_lists: bool = False,
           snap: dict | None = None) -> dict:
    """Returns {"intent", "short", "held", "todo", "guide", "why", "followups"}. `held`: current holdings by product
    type. `fund_lists`: the reply carries fund finder cards. `snap`: the fund finder snapshot (expense ratios)."""
    steps = todo(final.plan, profile, bundle.rules)
    ctx = topics.Ctx(question, final, profile, cap, bundle, held or [], snap, steps)
    base, special = intent_of(question), topics.intent_of(question)
    # Specific topics answer the question asked; a loan or insurance question keeps its own answer.
    if special and not (special == "goal" and base not in ("plan", "how_much")) and base not in ("debt", "insurance"):
        t = topics.TOPICS[special](ctx)
        if t is not None:
            return _from_topic(special, t, ctx, final, bundle)
    if base == "debt" and (t := topics.debt(ctx)) is not None:
        return _from_topic("debt", t, ctx, final, bundle)
    out = _answer(question, final, profile, cap, bundle, held, fund_lists, steps)
    if base == "insurance":
        out["guide"] = topics.insurance_guide(ctx)
    return out


def _from_topic(intent: str, t, ctx, final, bundle) -> dict:
    ceiling_level = bundle.rules["suitability"]["max_risk"][final.suitability]
    why = _why(intent, final, ctx.profile, ctx.cap, bundle) if t.why else []
    have = held_line(ctx.held, ceiling_level, bundle) if t.held else None
    pick = ctx.steps if t.pick is None else t.pick
    return {"intent": intent, "short": t.short, "held": have, "todo": pick[:5], "guide": t.guide, "why": why[:3],
            "followups": topics.FOLLOWUPS.get(intent, FOLLOWUPS["plan"])}


def _answer(question: str, final, profile, cap, bundle, held, fund_lists, steps) -> dict:
    rules = bundle.rules
    plan = final.plan
    intent = intent_of(question)
    c = rules["capacity"]
    ef_target = c["emergency_months"] * profile.expenses_monthly
    ceiling_level = rules["suitability"]["max_risk"][final.suitability]
    priority = [s for s in plan.steps if s.action not in ("invest", "deploy_excess_savings")]
    invest_from = plan.invest_start_month
    surplus = profile.monthly_surplus

    short = ""
    pick = steps   # which steps to list
    if intent == "emergency":
        if "R1" in cap.rule_ids:
            short = (f"Not yet. You have {inr(profile.liquid_savings)}, which covers {cap.E:.1f} months of expenses; a "
                     f"safe emergency fund is {c['emergency_months']} months, {inr(ef_target)}.")
            pick = [t for s, t in zip(plan.steps, steps) if s.action == "build_emergency_fund"] or steps[:2]
        else:
            short = (f"Yes. Your {inr(profile.liquid_savings)} covers {cap.E:.1f} months of expenses, more than the "
                     f"{c['emergency_months']} months ({inr(ef_target)}) a safety net needs.")
            pick = [t for s, t in zip(plan.steps, steps) if s.action == "deploy_excess_savings"] or \
                   [f"Keep at least {inr(ef_target)} in a savings account or liquid fund, and top it up when your "
                    "expenses rise."]
    elif intent == "retirement":
        ret = next((b for b in plan.buckets if b.id != "general" and any(
            g.id == b.id and g.kind == "retirement" for g in profile.goals)), None)
        if ret and ret.monthly > 0:
            g = next(g for g in profile.goals if g.id == ret.id)
            short = (f"Put about {inr(ret.monthly)} a month towards retirement. Your target of {inr(g.target_today)} in "
                     f"today's money is about {inr(ret.target_future)} after inflation in {g.horizon_years:g} years.")
            if ret.sip_needed and not ret.fundable:
                short += (f" Fully funding it would take {inr(ret.sip_needed)} a month, so this covers "
                          f"{ret.monthly / ret.sip_needed:.0%} for now.")
            pick = [t for s, t in zip(plan.steps, steps) if s.goal_id == ret.id] + \
                   [t for s, t in zip(plan.steps, steps) if s.action in ("buy_health_cover", "buy_term_cover")]
        elif ret is not None or any(g.kind == "retirement" for g in profile.goals):
            g = next(g for g in profile.goals if g.kind == "retirement")
            ret = ret or next((b for b in plan.buckets if b.id == g.id), None)
            first = next((b for b in plan.buckets if b.monthly > 0 and b.id != "general"), None)
            short = (f"Nothing goes to retirement yet: your monthly savings are fully used by "
                     + (f"'{first.name}', which comes sooner." if first else "the steps below, which come first.")
                     + (f" Fully funding retirement ({inr(g.target_today)} in today's money, {g.horizon_years:g} years "
                        f"away) would take about {inr(ret.sip_needed)} a month on top." if ret and ret.sip_needed else ""))
            pick = steps[:3]
        else:
            short = ("I can't size it yet: your profile has no retirement goal. Add one (the amount you'd want in "
                     "today's money and the years left) and I'll work out the monthly amount.")
            pick = steps[:3]
    elif intent == "funds":
        lines = _fund_lines(plan, bundle)
        if lines:
            short = f"For your risk level, these fund types fit: {_join(lines)}."
            if invest_from > 1:
                short += f" Start them from month {invest_from}, after the steps that protect you first."
        else:
            short = "Not yet: your plan has no mutual funds until the steps below are done."
        short += (" Below, each type lists its actual funds with their costs and past returns, cheapest first. "
                  "FinAdvisor doesn't pick a specific scheme for you; compare them yourself."
                  if fund_lists and lines else " FinAdvisor suggests fund types, not specific schemes or fund houses.")
        pick = steps
    elif intent == "how_much":
        if plan.investing_monthly > 0:
            short = (f"You can invest {inr(plan.investing_monthly)} a month"
                     + (f" from month {invest_from}" if invest_from > 1 else "")
                     + f", out of the {inr(surplus)} left each month after expenses and EMIs.")
        else:
            short = (f"Nothing yet: after expenses and EMIs you have {inr(surplus)} left a month, and the steps below come "
                     "first.")
    elif intent == "insurance":
        need_h = max(c["health_cover_min_inr"], c["health_cover_income_share"] * cap.Y)
        parts = []
        parts.append(f"health cover {inr(profile.health_cover)} (you need at least {inr(need_h)})"
                     if "R3" in cap.rule_ids else f"health cover {inr(profile.health_cover)} is enough")
        if profile.dependants:
            need_l = c["life_cover_multiple"] * cap.Y
            parts.append(f"term life cover {inr(profile.life_cover)} (about {inr(need_l)} is needed)"
                         if "R2" in cap.rule_ids else f"term life cover {inr(profile.life_cover)} is enough")
        else:
            parts.append("no one depends on your income, so term cover is optional for now")
        short = "Your cover: " + "; ".join(parts) + "."
        pick = [t for s, t in zip(plan.steps, steps) if s.action in ("buy_health_cover", "buy_term_cover")] or steps[:2]
    elif intent == "debt":
        short = (f"Your EMIs take {cap.D:.0%} of take-home pay (the limit is {c['emi_cap']:.0%})"
                 + ("; a costly loan or unpaid card bill should go first." if "R4" in cap.rule_ids else
                    ", and none of your loans is costly, so investing alongside the EMIs is fine."))
        pick = [t for s, t in zip(plan.steps, steps) if s.action in ("clear_card_dues", "repay_costly_loan", "no_new_emi")] \
            or steps[:2]
    else:
        short = (f"Here is what to do with the {inr(surplus)} you have left each month after expenses and EMIs"
                 + (", starting with what protects you." if priority else ".") if surplus > 0 else
                 "Right now your expenses and EMIs use all of your take-home pay, so the first step is to free up money.")

    why = _why(intent, final, profile, cap, bundle)
    have = held_line(held or [], ceiling_level, bundle) if intent in ("plan", "funds", "how_much", "retirement") else None
    return {"intent": intent, "short": short, "held": have, "todo": pick[:5], "guide": [], "why": why[:3],
            "followups": FOLLOWUPS.get(intent, FOLLOWUPS["plan"])}


def _why(intent: str, final, profile, cap, bundle) -> list[str]:
    c = bundle.rules["capacity"]
    ceiling = RISK_LABEL[bundle.rules["suitability"]["max_risk"][final.suitability]]
    why = []
    if "R1" in cap.rule_ids and intent != "emergency":
        why.append(f"Your emergency fund covers {cap.E:.1f} of the {c['emergency_months']} months a safety net needs.")
    if final.capacity and final.willingness and final.willingness.level:
        held_out = [SHORT.get(d.id, d.product["name"]) for d in final.decisions
                if not d.allowed and d.product.get("plannable") and any(r.startswith("its risk level") for r in d.reasons)]
        line = (f"Your risk level is {final.suitability.capitalize()}: the lower of your capacity for loss "
                f"({final.capacity.level.capitalize()}) and your questionnaire ({final.willingness.level.capitalize()}), "
                f"so products rated up to {ceiling} risk.")
        if held_out and intent in ("funds", "plan", "how_much"):
            line += f" Not used for new money for now: {_join(held_out[:4])}."
        why.append(line)
    if not profile.goals and intent in ("plan", "funds", "how_much"):
        why.append("You haven't added goals yet, so long-term money uses one standard mix. Add a goal such as a home "
                   "or retirement on your profile to get a separate amount for each.")
    return why


def render(a: dict, with_short: bool = True) -> str:
    parts = []
    if with_short and a["short"]:
        parts.append(a["short"])
    for title, lines in a.get("guide") or []:
        parts.append(f"**{title}**\n\n" + "\n".join(f"- {t}" for t in lines))
    if a.get("held"):
        parts.append("**What you already have**\n\n" + a["held"])
    if a["todo"]:
        parts.append("**What to do**\n\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(a["todo"], 1)))
    if a["why"]:
        parts.append("**Why this suits you**\n\n" + "\n".join(f"- {w}" for w in a["why"]))
    return "\n\n".join(parts)
