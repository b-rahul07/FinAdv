"""The website's conversation stage: answers that need no plan run.

    follow-up what-ifs   "and if I add a car loan EMI of 12k?"  -> the what-if engine on the confirmed facts
    one missing fact     a single-question card; the answer becomes a new profile version (apply_answers)
    tax                  both regimes from the person's salary, the cheaper one, ELSS/PPF/NPS, FD vs debt fund
    "am I on track?"     plan progress, goals and the health check, from the home-page overview

Runs before the routes when `stages.conversation` is set (configs/pipeline/pipeline-v5-website.yaml). Experiments
use pipeline files without the flag, so nothing here runs for them.

No model call: every sentence is built from engine and calculator results. `reply` returns None for anything it does
not recognise with confidence, for any turn that names a product the plan never holds, and for any pressure turn;
those go to the pipeline (router rule: when unsure, the pipeline).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

from finadvisor.advisor import cards, pressure
from finadvisor.advisor.capacity import assess as assess_capacity
from finadvisor.advisor.profile import Goal, Profile, TaxFacts, missing_fields
from finadvisor.advisor.router import LEARN, NEVER_PLANNED
from finadvisor.calc import goals as goal_calc
from finadvisor.calc import income_tax
from finadvisor.calc.money import inr

log = logging.getLogger(__name__)
CONFIG = Path(__file__).resolve().parent.parent.parent / "configs" / "conversation" / "v1.yaml"
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@lru_cache(maxsize=1)
def config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


@dataclass
class Reply:
    route: str                       # whatif | tax | track | ask
    text: str
    cards: list[dict] = field(default_factory=list)
    record: dict | None = None       # stored in advice_runs.record; None for a question back to the person


# ----------------------------------------------------------------------------- amounts in a message

UNIT = {"k": 1e3, "thousand": 1e3, "l": 1e5, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5,
        "cr": 1e7, "crore": 1e7, "crores": 1e7}
AMT = r"(?:₹|rs\.?\s*|inr\s*)?(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|lakhs?|lacs?|l|crores?|cr)?\b"
MONTHLY = re.compile(r"\bemi\b|\b(a|per|each|every)\s+month\b|\bmonthly\b|/\s*(month|mo)\b|\bp\.?m\.?\b", re.I)
COUNT = {"no": 0, "zero": 0, "one": 1, "a": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def _amount(m: re.Match, g: int = 1) -> float:
    return float(m.group(g).replace(",", "")) * UNIT.get((m.group(g + 1) or "").lower(), 1)


def _month(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{MONTHS[d.month - 1]} {d.year}"


def _day(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


# ----------------------------------------------------------------------------- follow-up what-ifs

HYPOTHETICAL = re.compile(r"\b(what if|and if|if i\b|if my\b|if we\b|suppose|supposing|how about|what about|what happens if"
                          r"|what would happen if)|^\s*(and |but |or )?with\b", re.I)
P_EMI = re.compile(r"\b(loan|emi)\b", re.I)
P_DEPENDANTS = re.compile(r"\b(\d+|no|zero|one|two|three|four|five)\s+(more\s+)?(dependants?|dependents?|kids?|children|child)\b", re.I)
P_BABY = re.compile(r"\b(have|having|had|expecting|expect)\s+(a|another)\s+(baby|child|kid)\b", re.I)
P_SAVE_MORE = re.compile(r"\b(save|saved|put away|set aside)\s+" + AMT + r"\s+(more|extra)\b", re.I)
P_SPEND_LESS = re.compile(r"\b(cut|reduce|lower|trim)\s+(my\s+)?(expenses|spending|spends?)\s+by\s+" + AMT
                          + r"|\bspend\s+" + AMT + r"\s+less\b", re.I)
P_SPEND_MORE = re.compile(r"\b(expenses|spending|rent)\s+(go(es)?\s+up|rises?|increases?|went up)\s+by\s+" + AMT
                          + r"|\bspend\s+" + AMT + r"\s+more\b", re.I)
P_INCOME_UP = re.compile(r"\b(raise|hike|increment)\s+of\s+" + AMT
                         + r"|\b(salary|take[- ]?home|income|pay)\s+(go(es)?\s+up|rises?|increases?)\s+by\s+" + AMT
                         + r"|\bearn\s+" + AMT + r"\s+more\b", re.I)
P_INCOME_SET = re.compile(r"\b(salary|take[- ]?home|income|pay)\s+(becomes?|is|were|was|of|goes to|rises to|increases to)\s+" + AMT, re.I)


def _last_amount(m: re.Match) -> float:
    """The amount in whichever alternative of the pattern matched (its number group is followed by its unit group)."""
    groups = m.groups()
    for i in range(len(groups) - 1):
        g = groups[i]
        if g and re.fullmatch(r"\d[\d,]*(?:\.\d+)?", g):
            return float(g.replace(",", "")) * UNIT.get((groups[i + 1] or "").lower(), 1)
    raise ValueError("no amount")


def parse_change(text: str, p: Profile) -> tuple[dict, str] | None:
    """(changes for cards.what_if, the change in words) or None when the message is not one clear change."""
    cfg = config()["what_if"]
    m = P_DEPENDANTS.search(text)
    if m:
        n = COUNT.get(m.group(1).lower(), None)
        n = int(m.group(1)) if n is None else n
        total = p.dependants + n if m.group(2) else n
        if 0 <= total <= 10 and total != p.dependants:
            return {"dependants": total}, f"you had {total} dependant{'' if total == 1 else 's'} instead of {p.dependants}"
        return None
    if P_BABY.search(text):
        return {"dependants": p.dependants + 1}, f"you had {p.dependants + 1} dependant{'' if p.dependants == 0 else 's'} instead of {p.dependants}"
    for pat, sign, what in ((P_SAVE_MORE, -1, "expenses"), (P_SPEND_LESS, -1, "expenses"), (P_SPEND_MORE, +1, "expenses")):
        m = pat.search(text)
        if m:
            a = _last_amount(m)
            new = p.expenses_monthly + sign * a
            if a <= 0 or new < 0:
                return None
            verb = "fell" if sign < 0 else "rose"
            return {"expenses_monthly": new}, f"your expenses {verb} by {inr(a)} a month, to {inr(new)}"
    m = P_INCOME_UP.search(text)
    if m:
        a = _last_amount(m)
        new = p.take_home_monthly + a
        if 0 < a and new < cfg["take_home_monthly_max"]:
            return {"take_home_monthly": new}, f"your take-home rose by {inr(a)} a month, to {inr(new)}"
        return None
    m = P_INCOME_SET.search(text)
    if m:
        new = _last_amount(m)
        if 0 < new < cfg["take_home_monthly_max"] and new != p.take_home_monthly:
            return {"take_home_monthly": new}, f"your take-home were {inr(new)} a month instead of {inr(p.take_home_monthly)}"
        return None
    if P_EMI.search(text):
        m = re.search(AMT, text, re.I)
        if m:
            a = _amount(m)
            if a > 0 and (a < cfg["emi_max_without_monthly_word"] or MONTHLY.search(text)) and a < p.take_home_monthly * 2:
                return {"new_emi": a}, f"you took on a new EMI of {inr(a)} a month"
    return None


def _what_if(text: str, p: Profile, bundle, ctx: dict) -> Reply | None:
    if not HYPOTHETICAL.search(text) or not (ctx.get("home") or {}).get("plan"):
        return None                                   # a follow-up needs a plan to follow
    parsed = parse_change(text, p)
    if parsed is None:
        return None
    changes, words = parsed
    w = cards.what_if(p, changes, bundle)
    b, a = w["before"], w["after"]
    parts = [f"If {words}: you would have {inr(a['monthly_surplus'])} left each month instead of {inr(b['monthly_surplus'])}."]
    parts += [e for e in w["explanations"] if not e.startswith("Nothing in the plan")]
    if a["investing_monthly"] != b["investing_monthly"] or a["invest_start_month"] != b["invest_start_month"]:
        parts.append(f"Investing would be {inr(a['investing_monthly'])} a month from month {a['invest_start_month']}; "
                     f"today it is {inr(b['investing_monthly'])} from month {b['invest_start_month']}.")
    else:
        parts.append("The steps and the investing amount stay as they are.")
    parts.append("This is an illustration with the standard mix for your level. Your saved plan has not changed.")
    # "Make this my profile" only where the change is an exact fact; a new loan needs its real details.
    apply = None if "new_emi" in changes else p.model_copy(update=changes).model_dump(mode="json")
    card = {"type": "what_if_answer", "label": words[0].upper() + words[1:], "changes": changes, "before": b, "after": a,
            "explanations": w["explanations"], "apply": apply, "show": "main",
            "apply_note": ("To make it real, add the loan with its actual size and rate under My money, Loans."
                           if apply is None else None)}
    follow = {"type": "followups", "items": ["Make me a money plan", "Am I on track?"]}
    cap = assess_capacity(p, bundle.rules)
    record = {"profile": p.model_dump(), "capacity": cap.to_dict(), "suitability": b["suitability"],
              "rules": sorted(cap.rule_ids), "what_if": {"changes": changes, "before": b, "after": a,
                                                         "explanations": w["explanations"]}}
    return Reply("whatif", " ".join(parts), [card, follow], record)


# ----------------------------------------------------------------------------- one missing fact

ASKABLE = {
    "age": {"question": "How old are you?", "unit": "years", "min": 16, "max": 100,
            "hint": "Used to set how many years your retirement goal has."},
    "gross_salary_annual": {"question": "What is your yearly salary before tax?", "unit": "₹ a year", "min": 0, "max": 1e9,
                            "hint": "The gross figure on your payslip or Form 16, for the whole year."},
    "retirement_spend_monthly": {"question": "How much would you want to spend each month in retirement, in today's money?",
                                 "unit": "₹ a month", "min": 1, "max": 1e8, "hint": ""},
    "deductions_80c": {"question": "80C investments this year (EPF, PPF, ELSS, life-insurance premium)", "unit": "₹ a year", "min": 0, "max": 1e8, "hint": ""},
    "deductions_80d": {"question": "Health-insurance premium you pay (80D)", "unit": "₹ a year", "min": 0, "max": 1e8, "hint": ""},
    "nps_80ccd1b": {"question": "Your own NPS contribution (80CCD(1B))", "unit": "₹ a year", "min": 0, "max": 1e8, "hint": ""},
    "hra_exemption_annual": {"question": "HRA exemption on your payslip or Form 16", "unit": "₹ a year", "min": 0, "max": 1e8, "hint": ""},
}
TAX_FIELDS = tuple(TaxFacts.model_fields)


def ask_card(fld: str, then: str, hint: str | None = None) -> dict:
    a = ASKABLE[fld]
    return {"type": "ask", "field": fld, "question": a["question"], "unit": a["unit"], "min": a["min"], "max": a["max"],
            "hint": hint if hint is not None else a["hint"], "then": then, "show": "main"}


def retirement_goal(p: Profile, spend_monthly: float, bundle) -> Goal:
    """The retirement goal that follows from a monthly spend in today's money: the corpus (today's rupees) that pays
    that amount for the configured number of years, due at the planning retirement age."""
    r = config()["retirement"]
    if p.age is None:
        raise ValueError("Age is needed to date a retirement goal.")
    years_left = r["age"] - p.age
    if years_left < 1:
        raise ValueError(f"The planning retirement age is {r['age']}; add your retirement goal on the Facts tab instead.")
    inflation = bundle.assumptions["inflation_pa"]["value"]
    corpus = goal_calc.retirement_corpus_today(spend_monthly, r["years"], r["return_after_pa"], inflation)
    used = {g.id for g in p.goals}
    gid = next(f"g{n}" for n in range(1, len(used) + 2) if f"g{n}" not in used)
    return Goal(id=gid, name="Retirement", kind="retirement", target_today=round(corpus), horizon_years=years_left)


def apply_answers(p: Profile, answers: dict, bundle) -> Profile:
    """A new profile with the answers of a single-question card (or the deductions form) applied. Raises ValueError
    with a sentence for the person when an answer cannot be used."""
    upd: dict = {}
    tax = (p.tax or TaxFacts()).model_dump()
    goals = list(p.goals)
    for fld, raw in answers.items():
        if fld not in ASKABLE:
            raise ValueError(f"Unknown field {fld!r}.")
        try:
            v = float(raw)
        except (TypeError, ValueError):
            raise ValueError("Please enter a number.") from None
        a = ASKABLE[fld]
        if not a["min"] <= v <= a["max"]:
            raise ValueError(f"{a['question']}: enter a value between {a['min']:g} and {a['max']:g}.")
        if fld == "age":
            upd["age"] = int(v)
        elif fld in TAX_FIELDS:
            tax[fld] = v
        elif fld == "retirement_spend_monthly":
            goals.append(retirement_goal(p.model_copy(update=upd), v, bundle))
    d = {**p.model_dump(), **upd, "goals": [g.model_dump() for g in goals]}
    if any(x is not None for x in tax.values()):
        d["tax"] = tax
    return Profile(**d)


RETIRE = re.compile(r"\bretire(ment|d|s)?\b|\bpension\b", re.I)
RETIRE_ASK = re.compile(r"\b(how much|enough|corpus|need|save|plan|when can i|can i|ready)\b", re.I)


def _retirement(text: str, p: Profile, bundle) -> Reply | None:
    if not (RETIRE.search(text) and RETIRE_ASK.search(text)) or LEARN.match(text) and not PERSONAL.search(text):
        return None
    if any(g.kind == "retirement" or RETIRE.search(g.name) for g in p.goals):
        return None                                   # the goal exists: the plan answers
    r = config()["retirement"]
    if p.age is None:
        return Reply("ask", "To plan for retirement I need one thing first.", [ask_card("age", text)])
    if p.age >= r["age"]:
        return None
    hint = (f"Your expenses today are {inr(p.expenses_monthly)} a month. I will size a goal that pays this for "
            f"{r['years']} years from age {r['age']}.")
    return Reply("ask", "You have no retirement goal yet, so I need one number to size it.",
                 [ask_card("retirement_spend_monthly", text, hint)])


# ----------------------------------------------------------------------------- tax

PERSONAL = re.compile(r"\b(i|my|me|mine|i'm|i'd|we|our)\b", re.I)
TAX = re.compile(r"\bincome[- ]?tax\b|\bhow much tax\b|\btax (do|will|would|should|can) i\b|\bmy tax(es)?\b"
                 r"|\btax on my (salary|income|pay)\b|\b(which|what) (tax )?regime\b|\b(old|new) (tax )?regime\b"
                 r"|\bold (or|vs\.?|versus) new\b|\bnew (or|vs\.?|versus) old\b|\b(save|saving|cut|reduce|lower) (my |on |more )?tax\b"
                 r"|\btax[- ]saving\b|\b80c\b|\b80d\b|\bafter[- ]tax\b|\btax (bill|liability|outgo)\b", re.I)
SAVE_TAX = re.compile(r"\b80c\b|\belss\b|\bppf\b|\bnps\b|\b(save|saving|cut|reduce|lower) (my |on |more )?tax\b|tax[- ]saving|deductions?", re.I)
FD = re.compile(r"\bfds?\b|fixed deposits?", re.I)
DEBT_FUND = re.compile(r"\bdebt (mutual )?funds?\b", re.I)
DEDUCTION_LABEL = {"deductions_80c": "80C", "deductions_80d": "80D", "nps_80ccd1b": "NPS 80CCD(1B)",
                   "hra_exemption_annual": "HRA exemption"}


def _tax(text: str, p: Profile, bundle) -> Reply | None:
    if not TAX.search(text) or (LEARN.match(text) and not PERSONAL.search(text)):
        return None
    facts = p.tax or TaxFacts()
    gross = facts.gross_salary_annual
    if not gross:
        return Reply("ask", "To work out your tax I need one number.", [ask_card("gross_salary_annual", text)])
    cfg = income_tax.rules()
    ded = {k: getattr(facts, k) for k in income_tax.DEDUCTION_FIELDS}
    known = {k: v for k, v in ded.items() if v}
    c = income_tax.compare(gross, ded, cfg)
    new, old = c["new"], c["old"]
    with_ded = ("with the deductions you gave me (" + ", ".join(f"{DEDUCTION_LABEL[k]} {inr(v)}" for k, v in old["deductions"].items() if v)
                + ")") if old["deductions_total"] else "with no deductions"
    parts = [f"For FY {c['financial_year']}, on a salary of {inr(gross)} a year: tax is {inr(new['total'])} under the new "
             f"regime and {inr(old['total'])} under the old regime {with_ded}."]
    if c["better"] == "same":
        parts.append("The two regimes cost the same.")
    else:
        parts.append(f"The {c[c['better']]['label'].lower()} is cheaper by {inr(c['saving'])} a year.")
    if not known:
        parts.append("I assumed you claim nothing under the old regime; add your 80C, 80D, NPS and HRA amounts on the "
                     "card for an exact comparison.")
    extra = None
    if SAVE_TAX.search(text):
        extra = income_tax.with_full_deductions(gross, ded, cfg)
        caps = cfg["old"]["deductions"]
        if extra["extra_invested"] > 0:
            parts.append(
                f"ELSS, PPF and NPS cut tax only under the old regime. Using all of 80C ({inr(caps['deductions_80c'])}) and "
                f"the extra NPS deduction ({inr(caps['nps_80ccd1b'])}) means putting in {inr(extra['extra_invested'])} more "
                f"a year; that lowers the old regime's tax by {inr(extra['old_saving'])}, to {inr(extra['old_tax_full'])}. "
                + ("The two regimes would then cost the same." if extra["better_after"] == "same" else
                   f"Even then the {cfg[extra['better_after']]['label'].lower()} is cheaper by {inr(extra['saving_after'])}."))
        else:
            parts.append("You already use all of 80C and the extra NPS deduction, so more ELSS, PPF or NPS would not "
                         "lower your tax further.")
        parts.append("Under the new regime none of them reduces tax, so there they are a choice about saving, not tax.")
    fd = None
    if FD.search(text) and DEBT_FUND.search(text):
        rate = c[c["better"] if c["better"] != "same" else "new"]["marginal_rate"]
        conv = config()["tax"]
        ret = bundle.assumptions["returns_pa"]
        fd = income_tax.fd_vs_debt_fund(conv["fd_vs_fund_amount"], conv["fd_vs_fund_years"], ret["fixed_deposit"]["value"],
                                        ret["short_duration_debt_fund"]["value"], rate)
        if rate == 0:
            parts.append("At your income neither a bank FD's interest nor a debt fund's gain is taxed in practice, so tax "
                         "does not separate them.")
        else:
            parts.append(
                f"FD against debt fund: both are taxed at your slab rate, {rate * 100:.1f}% with cess. An FD's interest is "
                f"taxed every year; a debt fund's gain only when you sell. On {inr(fd['amount'])} for {fd['years']} years "
                f"that leaves {inr(fd['fd_after_tax'])} from the FD and {inr(fd['debt_fund_after_tax'])} from the fund, at "
                f"assumed returns of {fd['fd_rate_pct']:g}% and {fd['fund_rate_pct']:g}% a year, which are not guaranteed.")
    parts.append(f"Estimated, not tax advice. Not counted: {c['not_modelled']}.")
    card = {"type": "tax", "financial_year": c["financial_year"], "as_of": c["as_of"], "gross": gross, "new": new, "old": old,
            "better": c["better"], "saving": c["saving"], "deductions": {k: (v or 0) for k, v in ded.items()},
            "deductions_known": bool(known), "then": text, "show": "main",
            "source": f"Slabs and limits for FY {c['financial_year']}, as of {_day(c['as_of'])}"}
    items = [q for q in ("Would ELSS, PPF or NPS cut my tax?", "Is an FD or a debt fund better for me after tax?")
             if not (q.startswith("Would") and extra) and not (q.startswith("Is an FD") and fd)]
    record = {"profile": p.model_dump(), "tax": {**c, "full_deductions": extra, "fd_vs_debt_fund": fd}}
    return Reply("tax", " ".join(parts), [card, {"type": "followups", "items": items + ["Make me a money plan"]}], record)


# ----------------------------------------------------------------------------- "am I on track?"

TRACK = re.compile(r"\bon track\b|\bhow am i doing\b|\bam i doing (ok|okay|well|fine|alright|enough)\b"
                   r"|\b(my|check my|show my) progress\b|\bhow far (am i|have i)\b", re.I)


def _track(text: str, p: Profile, ctx: dict) -> Reply | None:
    home = ctx.get("home") or {}
    plan = home.get("plan")
    if not TRACK.search(text) or not plan:
        return None                                   # no plan yet: the pipeline makes one
    today: date = ctx.get("today") or date.today()
    this_month = date(today.year, today.month, 1).isoformat()
    open_steps = [s for s in plan["steps"] if s["status"] in ("suggested", "pending")]
    overdue = [s for s in open_steps if (s["ends_on"] or s["starts_on"]) < this_month]
    goals = home.get("goals") or []
    short = [g for g in goals if g.get("fundable") is False and g.get("sip_needed")]
    if plan["stale"]:
        lead = "Your facts changed after this plan was made, so its amounts may be out of date. Ask me to re-plan first."
    elif overdue:
        s = overdue[0]
        lead = (f"Not quite: step {s['order']} was due by {_month(s['ends_on'] or s['starts_on'])} and is still open"
                + (f", along with {len(overdue) - 1} more." if len(overdue) > 1 else "."))
    elif not open_steps:
        lead = "Yes: every step of your plan is done or skipped."
    else:
        lead = "Yes, so far: nothing in your plan is overdue."
    parts = [lead, f"You have done {plan['done']} of {plan['total']} steps of the plan made on {_day(plan['made_at'])}."]
    nxt = next((s for s in plan["steps"] if s["order"] == plan["next_order"]), None)
    if nxt:
        when = (f"from {_month(nxt['starts_on'])}" if nxt["kind"] == "ongoing" else
                f"in {_month(nxt['starts_on'])}" if nxt["kind"] == "one_off" or nxt["ends_on"] == nxt["starts_on"] else
                f"{_month(nxt['starts_on'])} to {_month(nxt['ends_on'])}")
        parts.append(f"Next is step {nxt['order']} ({when}): {nxt['text']}")
    for g in goals[:3]:
        line = f"{g['name']}: {g['funded']:.0%} saved ({inr(g['saved_so_far'])} of {inr(g['target_today'])} in today's rupees)"
        if g.get("sip_needed") is not None and g.get("monthly_assigned") is not None:
            line += f"; it needs {inr(g['sip_needed'])} a month and your plan gives {inr(g['monthly_assigned'])}"
        parts.append(line + ".")
    if short and not plan["stale"]:
        parts.append("The plan cannot fully fund " + " and ".join(g["name"] for g in short[:2])
                     + " at today's surplus; a later date, a smaller target or more income closes the gap.")
    health, hist = home.get("health"), home.get("health_history") or []
    if health:
        line = f"Your health check passes {health['score']} of {health['out_of']}"
        if len(hist) > 1 and hist[0]["score"] != health["score"]:
            line += f", {'up' if health['score'] > hist[0]['score'] else 'down'} from {hist[0]['score']} on {_day(hist[0]['at'])}"
        parts.append(line + ".")
    follow = {"type": "followups", "items": (["Update my money plan for my latest facts"] if plan["stale"] else [])
              + ["Do I have enough emergency savings?", "Make me a money plan"]}
    cap = assess_capacity(p, ctx["rules"])
    record = {"profile": p.model_dump(), "capacity": cap.to_dict(), "rules": sorted(cap.rule_ids),
              "track": {"done": plan["done"], "total": plan["total"], "next_order": plan["next_order"], "stale": plan["stale"],
                        "overdue": [s["order"] for s in overdue], "goals": goals, "health_history": hist}}
    return Reply("track", " ".join(parts), [follow], record)


# ----------------------------------------------------------------------------- entry

def reply(inp, bundle) -> Reply | None:
    """An answer from this stage, or None to let the routes handle the turn. `inp` is the pipeline's TurnInput."""
    p: Profile | None = inp.confirmed
    text = inp.text.strip()
    if p is None or missing_fields(p) or not text:
        return None                                   # no confirmed, complete profile: the pipeline asks for it
    try:
        if set(pressure.products_in(text)) & (NEVER_PLANNED - {"new_emi"}):
            return None                               # shares, F&O, crypto, small caps: always the pipeline
        if pressure.read(text, inp.earlier_user_turns).is_pressure:
            return None
        ctx = dict(inp.context()) if inp.context is not None else {}
        ctx["rules"] = bundle.rules
        return (_track(text, p, ctx) or _what_if(text, p, bundle, ctx) or _tax(text, p, bundle)
                or _retirement(text, p, bundle))
    except Exception:  # noqa: BLE001 - this stage is a shortcut; when it fails the pipeline answers
        log.exception("conversation stage failed; falling through to the routes")
        return None
