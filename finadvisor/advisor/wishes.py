"""Answer the request first, then advise (deterministic wording, template `wish-v1`).

When someone asks for something specific ("which stocks should I buy?", "I want to try F&O"), the answer opens with
what FinAdvisor can tell them about that request, within its rules, and only then gives its own advice, graded by how
serious the gap is:

  strong     "I strongly advise ..."   a safety gap (R1 emergency fund, R2/R3 cover, R4 costly debt, R5 EMI load)
                                        or Low capacity for loss
  recommend  "I'd recommend ... first" other steps come first (after-priority products, R6 experience)
  suggest    "I'd suggest ..."          nothing blocks; a better-fitting route exists

The check card's `conflict` line (report Algorithm 3) is still produced and stored unchanged; this module only
changes how the answer reads. No individual stock is ever named (brief §2.5)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from finadvisor.advisor.gate import RISK_LABEL
from finadvisor.calc.money import inr

SAFETY_RULES = {"R1", "R2", "R3", "R4", "R5"}

# What FinAdvisor can say about each request, whatever the verdict. {alt} is the index-fund status sentence.
ABOUT = {
    "direct_equity": ("I can't name individual stocks. Choosing specific shares is personalised advice that only a "
                      "SEBI-registered adviser or research analyst may give, and FinAdvisor's checks can't test a single "
                      "company. Here is what I can tell you: the simplest way to own India's largest companies is a "
                      "Nifty 50 index fund, which holds all fifty at once at a low cost; {alt} If you still want to pick "
                      "shares yourself, keep them to a small part of money you won't need for many years, spread across "
                      "several companies and sectors, and add them under Holdings to track their price, gains and "
                      "52-week range."),
    "fno": ("FinAdvisor never plans futures and options. {fact} If what you're after is growth from the stock market, "
            "a Nifty 50 index fund gets you that without leverage; {alt}"),
    "crypto": ("Cryptocurrency is unregulated in India, so FinAdvisor never plans it and can't compare coins. If you "
               "decide to buy some anyway, treat it as money you can afford to lose entirely and keep it small."),
    "new_emi": ("Here is how this EMI fits your budget and your priority steps."),
}

INDEX_ALT = {
    "fits": "it suits your profile now.",
    "after_priorities": "it suits your risk level and can start once the steps below are done.",
    "blocked": "today it is rated {risk} risk, above what your profile allows.",
}


def template_id() -> str:
    """The wording lives in this module, so its id hashes the module text."""
    return f"wish-v1@{hashlib.sha256(Path(__file__).read_text(encoding='utf-8').replace(chr(13), '').encode()).hexdigest()[:8]}"


# How each request reads in a sentence ("You asked about ..."); shelf names are singular labels for cards.
PHRASE = {
    "mid_small_cap_fund": "mid- and small-cap funds", "large_cap_index_fund": "Nifty 50 index funds",
    "flexi_cap_fund": "flexi-cap funds", "elss": "ELSS (tax-saving) funds", "hybrid_baf": "balanced advantage funds",
    "gold_etf_fund": "gold ETFs and gold funds", "fixed_deposit": "fixed deposits", "recurring_deposit": "recurring deposits",
    "liquid_fund": "liquid funds", "short_duration_debt_fund": "short-duration debt funds", "nps": "NPS", "ppf": "PPF",
    "epf_vpf": "EPF / VPF", "new_emi": "a new EMI", "direct_equity": "individual stocks", "fno": "F&O",
    "crypto": "crypto",
}
DOING = {"direct_equity": "buying individual stocks", "fno": "trading F&O", "crypto": "buying crypto",
         "new_emi": "taking on a new EMI"}
# Generic wording for a triggered safety rule when the check card has no concrete change for it.
RULE_STEP = {"R1": "build your emergency fund", "R2": "get enough term life cover", "R3": "get enough health cover",
             "R4": "clear your costly debt", "R5": "bring your EMIs down"}
CHASING = {"peer_success", "rally_fomo", "finfluencer"}
GROWTH = ("large_cap_index_fund", "flexi_cap_fund", "elss", "hybrid_baf")


def _status(decision) -> str:
    if decision is None or not decision.allowed:
        return "blocked"
    return "after_priorities" if decision.after_priority else "fits"


def severity(card: dict, rule_ids: set[str]) -> str:
    if card["verdict"] == "fits":
        return "suggest"
    if card.get("capacity_level") == "low" or rule_ids & SAFETY_RULES:
        return "strong"
    return "recommend"


def _clean(text: str) -> str:
    t = text.rstrip(".")
    t = t[:-len(" first")] if t.endswith(" first") else t
    return t[0].lower() + t[1:]


def _first_step(card: dict, rule_ids: set[str], safety_only: bool) -> str | None:
    """The first concrete fact change from the check card, phrased to follow 'you to ...'. A strong warning always
    names a safety step (R1-R5) first."""
    want = SAFETY_RULES if safety_only else {f"R{i}" for i in range(1, 8)}
    for c in card["changes"]:
        if c["rule"] in want:
            return _clean(c["text"])
    for r in sorted(rule_ids & want):
        if r in RULE_STEP:
            return RULE_STEP[r]
    return None


def _emi_answer(card: dict) -> str:
    cap = card["emi_cap"]
    if card.get("new_emi"):
        return (f"An EMI of {inr(card['new_emi'])} would take your EMIs from {card['emi_ratio_now']:.0%} to "
                f"{card['emi_ratio_after']:.0%} of take-home pay; the safe limit is {cap:.0%}.")
    if card["emi_room"] <= 0:
        return (f"Your EMIs already take {card['emi_ratio_now']:.0%} of take-home pay, at or above the safe limit of "
                f"{cap:.0%}, so there's no room for a new EMI.")
    now = ("You have no EMIs now" if card["emi_ratio_now"] <= 0 else
           f"Your EMIs take {card['emi_ratio_now']:.0%} of take-home pay now")
    return (f"{now}, so a new EMI can be at most {inr(card['emi_room'])} a month before all EMIs pass the safe limit of "
            f"{cap:.0%}. Tell me the EMI amount and I'll check it against your plan.")


def frame(card: dict, decisions: dict, rule_ids: set[str], bundle, in_plan: list[str] | None = None,
          pressure_types: list[str] | None = None, goal_years: list[float] | None = None) -> dict:
    """Returns {"answer", "advice", "severity"}: the two paragraphs that open the reply.
    `in_plan` is given on the Plan route (products in the plan just built); the Check route builds no plan.
    `goal_years` are the person's goal horizons, for products that need a long goal."""
    pid, product = card["product_id"], decisions[card["product_id"]].product if card["product_id"] in decisions else {}
    phrase = PHRASE.get(pid, card["product_name"])
    need_years = product.get("min_goal_years")
    long_goal = bool(need_years) and any(y >= need_years for y in goal_years or [])
    missing = in_plan is not None and pid not in in_plan
    idx = decisions.get("large_cap_index_fund")
    alt = INDEX_ALT[_status(idx)].format(risk=RISK_LABEL.get(idx.product.get("riskometer"), "") if idx else "")
    verdict = card["verdict"]
    if pid == "new_emi" and "emi_room" in card:
        answer = _emi_answer(card)
    elif pid in ABOUT:
        fact = bundle.assumptions["facts"]["fno_losses"]["text"] if pid == "fno" else ""
        answer = ABOUT[pid].format(alt=alt, fact=fact)
    else:
        lead = f"You asked about {phrase}."
        if verdict == "fits":
            answer = f"{lead} They suit your profile: their risk level is within what your capacity and questionnaire allow."
            if need_years:
                answer += f" They are meant for goals at least {need_years} years away"
                if missing and not long_goal:
                    answer += ", and your profile has no goal that far off yet, so they are not in your plan today."
                elif missing:
                    answer += "; your plan below uses other diversified funds for those goals today."
                else:
                    answer += "."
        elif verdict == "after_priorities":
            answer = f"{lead} They suit your risk level, so they can be part of your investing once the priority steps are done."
        else:
            why = card["blockers"][0].split(": ", 1)[-1] if card["blockers"] else "they don't suit your profile yet"
            why = "their" + why[3:] if why.startswith("its ") else why
            answer = f"{lead} They don't suit you yet: {why}."

    sev = severity(card, rule_ids)
    first = _first_step(card, rule_ids, safety_only=sev == "strong")
    doing = DOING.get(pid, f"putting money into {phrase}")
    below = "the plan steps below" if in_plan is not None else "the steps below"
    if sev == "strong":
        advice = (f"I strongly advise you to {first or 'close the gaps on your health card'} before {doing}. That gap is "
                  f"what would hurt most if something went wrong, and {below} close it one at a time.")
    elif sev == "recommend":
        ceiling = RISK_LABEL[bundle.rules["suitability"]["max_risk"][card["suitability"]]]
        if first and pid != "crypto":
            advice = f"I'd recommend you {first} first; {below} show the order."
        elif pid == "crypto":
            advice = "I'd recommend keeping your long-term money in the regulated products your profile allows."
        else:
            advice = f"I'd recommend staying with products rated up to {ceiling} risk for now, as your plan does."
            if "R6" in rule_ids and card.get("willingness_level") == "medium":
                advice += " Your questionnaire counts as Medium until you have some investing experience."
    elif pid == "fno":
        advice = "I'd suggest leaving F&O aside and getting stock market growth through diversified equity funds."
    elif pid == "direct_equity":
        growth = in_plan is not None and any(p in in_plan for p in GROWTH)
        advice = ("I'd suggest getting most of your stock market exposure through "
                  + ("the equity funds in your plan" if growth else "diversified equity funds")
                  + " and keeping any shares you pick yourself to a small slice.")
    elif pid == "crypto":
        advice = "I'd recommend keeping your long-term money in the regulated products in your plan."
    elif missing and need_years and not long_goal:
        advice = "I'd suggest adding a long-term goal on your profile; FinAdvisor then checks where they fit in its mix."
    elif missing and need_years:
        advice = (f"I'd suggest keeping most of your stock market money in the plan's diversified funds; if you add "
                  f"{phrase}, keep them a small part of goals at least {need_years} years away.")
    elif pid == "new_emi":
        advice = ("If you go ahead, keep the EMI well below that limit and compare the total you'd pay, including interest "
                  "and any processing fee, with paying from savings you've built for it.")
    elif in_plan is not None:
        advice = "I'd suggest keeping them at the share your plan below gives them, so they fit alongside everything else."
    else:
        advice = "I'd suggest asking me for a plan, so FinAdvisor sizes them alongside everything else."
    if set(pressure_types or []) & CHASING and pid not in ("new_emi",):
        advice += (" Recent gains, whether a friend's or the market's, don't predict the next few years, so let the plan "
                   "set the amount, not the rally.")
    return {"answer": answer, "advice": advice, "severity": sev}
