"""Plan structure and the deterministic plan builder.

The LLM planner only chooses a product mix (integer "parts") for each money bucket. Everything
else here is arithmetic: priority steps and their order, rupee amounts, months, goal SIPs and rho.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from finadvisor.advisor.capacity import CapacityResult, costly_debts, required_health_cover
from finadvisor.advisor.gate import GateDecision, allowed_for_goal, plannable, risk_rank
from finadvisor.advisor.profile import Goal, Profile
from finadvisor.calc import goals as G
from finadvisor.calc.loans import months_to_repay
from finadvisor.calc.money import inr, round_up_to

GENERAL = "general"
DEBT_LABEL = {"home": "home loan", "car": "car loan", "two_wheeler": "two-wheeler loan", "personal": "personal loan",
              "education": "education loan", "bnpl": "BNPL dues", "credit_card": "credit-card dues", "gold": "gold loan",
              "other": "loan"}


def n_months(m: int) -> str:
    return f"{m} month" + ("" if m == 1 else "s")
ROUND_STEP = 100  # monthly amounts are rounded to ₹100


@dataclass
class Step:
    order: int
    action: str                  # see ACTIONS below
    text: str                    # deterministic sentence built from the numbers
    rule: str | None = None      # R1..R7 that requires the step
    monthly: float = 0.0
    months: int = 0
    start_month: int = 1
    target: float = 0.0
    product_id: str | None = None
    goal_id: str | None = None
    frees_emi: float = 0.0       # repay steps: the loan's EMI, free for other use from month start_month + months


ACTIONS = ("buy_health_cover", "buy_term_cover", "clear_card_dues", "repay_costly_loan",
           "build_emergency_fund", "no_new_emi", "invest")


@dataclass
class MixItem:
    product_id: str
    share: float
    monthly: float = 0.0


@dataclass
class Bucket:
    id: str                      # goal id or "general"
    name: str
    horizon_years: float | None
    mix: list[MixItem]
    monthly: float = 0.0
    target_future: float | None = None
    sip_needed: float | None = None
    assumed_return_pa: float | None = None
    fundable: bool | None = None
    shortfall: float = 0.0


@dataclass
class Plan:
    steps: list[Step]
    buckets: list[Bucket]
    monthly_surplus: float
    investing_monthly: float
    invest_start_month: int
    rho: float
    rho_by_goal: dict[str, float]
    source: str = "planner"      # planner | repair | safe_fallback | illustrative | model_amounts
    notes: list[str] = field(default_factory=list)
    # Ablation A5 (calculators off): monthly amounts per bucket as the model wrote them and as the calculators
    # would have computed them for the same mix, so the paper can measure the model's arithmetic.
    amounts: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    def mix_signature(self) -> dict[str, dict[str, float]]:
        """What MR6 compares: product shares per bucket, rounded."""
        return {b.id: {m.product_id: round(m.share, 3) for m in b.mix if m.share > 0} for b in self.buckets}


# --------------------------------------------------------------------------- buckets

@dataclass
class BucketSpec:
    id: str
    name: str
    goal: Goal | None
    allowed: list[dict]          # products the planner may use for this bucket


def bucket_specs(profile: Profile, decisions: list[GateDecision], rules: dict) -> list[BucketSpec]:
    candidates = plannable(decisions)
    specs = []
    for g in sorted(profile.goals, key=lambda g: g.horizon_years):
        allowed = [p for p in candidates if allowed_for_goal(p, g, rules)[0]]
        specs.append(BucketSpec(g.id, g.name, g, allowed))
    general = [p for p in candidates if allowed_for_goal(p, None, rules)[0]]
    specs.append(BucketSpec(GENERAL, "Long-term investing (no set goal)", None, general))
    return specs


def cash_available(plan: "Plan", month: int) -> float:
    """Money a plan can direct in `month`: the monthly surplus plus the EMIs of loans already cleared (a loan
    repaid in months s .. s+n-1 frees its EMI from month s+n). Loans that are not cleared keep their EMI."""
    return plan.monthly_surplus + sum(s.frees_emi for s in plan.steps
                                      if s.frees_emi and s.months and s.start_month + s.months <= month)


SAVINGS_FUNDED = ("deploy_excess_savings",)   # paid from money already saved, not from the monthly surplus


def outflow(plan: "Plan", month: int) -> float:
    """Money the plan directs in `month`: the priority steps running that month (a repay step's payment less the
    loan's own EMI, which is not part of the surplus) plus investing from invest_start_month."""
    out = sum(s.monthly - s.frees_emi for s in plan.steps
              if s.action != "invest" and s.action not in SAVINGS_FUNDED and s.months
              and s.start_month <= month < s.start_month + s.months)
    return out + (plan.investing_monthly if month >= plan.invest_start_month else 0.0)


def overspend(plan: "Plan") -> tuple[int, float, float] | None:
    """rule-check-v3: (month, outflow, available) for the first month the plan directs more money than it has, else
    None. Outflow and available cash only change where a step starts or ends, so those months are checked. Priority
    payments are rounded up to the next ₹100, which is allowed for; investing amounts get no such allowance."""
    edges = {1, plan.invest_start_month} | {s.start_month for s in plan.steps if s.months} | \
            {s.start_month + s.months for s in plan.steps if s.months}
    for m in sorted(edges):
        have, out = cash_available(plan, m), outflow(plan, m)
        priority = out - (plan.investing_monthly if m >= plan.invest_start_month else 0.0)
        if out > have + 1 + (ROUND_STEP if priority > 0 else 0):
            return m, out, have
    return None


def is_risky(product: dict, rules: dict) -> bool:
    return risk_rank(product.get("riskometer"), rules) >= risk_rank(rules["risky_from"], rules)


# --------------------------------------------------------------------------- priority steps

def priority_steps(profile: Profile, cap: CapacityResult, rules: dict) -> tuple[list[Step], int, float, list[str]]:
    """Ordered protection/debt steps. Returns (steps, invest_start_month, surplus_after, notes).

    Order: health cover, term cover, card dues, costly loans (highest rate first), emergency fund.
    Card dues and loans are cleared with the whole monthly surplus plus the loan's own EMI; a cleared
    loan's EMI is added back to the surplus for later steps.
    """
    steps: list[Step] = []
    notes: list[str] = []
    surplus = profile.monthly_surplus
    month = 1
    ids = cap.rule_ids

    def add(**kw):
        steps.append(Step(order=len(steps) + 1, **kw))

    if "R3" in ids:
        need = required_health_cover(cap.Y, rules)
        add(action="buy_health_cover", rule="R3", target=need - profile.health_cover,
            text=f"Get health cover of at least {inr(need)} (you have {inr(profile.health_cover)}). "
                 "Pay the premium from your monthly surplus.")
        notes.append("Insurance premiums are not known yet, so later monthly amounts do not deduct them.")
    if "R2" in ids:
        need = rules["capacity"]["life_cover_multiple"] * cap.Y
        who = "1 person depends" if profile.dependants == 1 else f"{profile.dependants} people depend"
        add(action="buy_term_cover", rule="R2", target=need - profile.life_cover,
            text=f"Get term life cover of about {inr(need)} ({rules['capacity']['life_cover_multiple']}× annual income) "
                 f"because {who} on you; you have {inr(profile.life_cover)}.")

    if "R4" in ids:
        card = sum(d.outstanding for d in profile.debts if d.kind == "credit_card")
        if not profile.card_dues_paid_in_full:
            if card > 0 and surplus > 0:
                m = G.months_to_save(card, surplus)
                add(action="clear_card_dues", rule="R4", monthly=round_up_to(card / m, ROUND_STEP), months=m,
                    start_month=month, target=card,
                    text=f"Clear credit-card dues of {inr(card)}: {inr(round_up_to(card / m, ROUND_STEP))}/month "
                         f"for {n_months(m)}, then pay the full bill every month.")
                month += m
            else:
                add(action="clear_card_dues", rule="R4",
                    text="Pay the full credit-card bill every month; card interest is usually above 36% a year.")
        for d in sorted(costly_debts(profile, rules), key=lambda d: -(d.rate_pa or 0)):
            payment = surplus + d.emi_monthly
            m = months_to_repay(d.outstanding, d.rate_pa or 0, payment) if payment > 0 else None
            label = d.label or DEBT_LABEL.get(d.kind, "loan")
            if m is None:
                add(action="repay_costly_loan", rule="R4", target=d.outstanding,
                    text=f"Your {label} costs more than you can repay from the surplus; keep paying the EMI and "
                         "avoid new debt.")
                continue
            add(action="repay_costly_loan", rule="R4", monthly=round_up_to(payment, ROUND_STEP), months=m,
                start_month=month, target=d.outstanding, frees_emi=d.emi_monthly,
                text=f"Prepay your {label} ({inr(d.outstanding)} outstanding"
                     + (f" at {d.rate_pa:g}%" if d.rate_pa else "")
                     + f"): put {inr(round_up_to(payment, ROUND_STEP))}/month towards it for about {n_months(m)}.")
            month += m
            surplus += d.emi_monthly   # the EMI is freed once the loan is closed

    if "R1" in ids:
        gap = rules["capacity"]["emergency_months"] * profile.expenses_monthly - profile.liquid_savings
        if surplus > 0:
            m = G.months_to_save(gap, surplus)
            monthly = round_up_to(gap / m, ROUND_STEP)
            add(action="build_emergency_fund", rule="R1", monthly=monthly, months=m, start_month=month,
                target=gap, product_id="liquid_fund",
                text=f"{inr(monthly)}/month for {n_months(m)} builds the {inr(gap)} still needed for an emergency "
                     f"fund of {rules['capacity']['emergency_months']} months' expenses. Keep it in a savings "
                     "account or liquid fund.")
            month += m
        else:
            add(action="build_emergency_fund", rule="R1", target=gap,
                text=f"Your expenses and EMIs use all of your take-home pay, so the {inr(gap)} emergency-fund gap "
                     "can't be closed yet. Look for expenses to cut first.")
    if "R5" in ids:
        excess = (cap.D - rules["capacity"]["emi_cap"]) * profile.take_home_monthly
        add(action="no_new_emi", rule="R5",
            text=f"Take no new EMI or BNPL. EMIs need to fall by about {inr(round_up_to(excess, ROUND_STEP))}/month "
                 f"to get under {rules['capacity']['emi_cap'] * 100:.0f}% of take-home pay.")
    return steps, month, surplus, notes


# --------------------------------------------------------------------------- full plan

def normalise_mix(raw: list[tuple[str, float]], spec: BucketSpec) -> tuple[list[MixItem], list[str]]:
    """Turn planner parts into shares, applying max_share caps. Unknown/disallowed ids are kept with
    share so the rule checker can flag them; caps are enforced here because they are hard limits."""
    notes = []
    total = sum(max(0.0, p) for _, p in raw)
    if total <= 0:
        return [], notes
    items = {}
    for pid, parts in raw:
        if parts > 0:
            items[pid] = items.get(pid, 0) + parts / total
    caps = {p["id"]: p["max_share"] for p in spec.allowed if p.get("max_share")}
    for pid, cap in caps.items():
        if items.get(pid, 0) > cap + 1e-9:
            excess = items[pid] - cap
            items[pid] = cap
            others = {k: v for k, v in items.items() if k != pid}
            s = sum(others.values())
            if s > 0:
                for k in others:
                    items[k] += excess * others[k] / s
            else:
                items[pid] = 1.0  # nothing to move the excess to; cap cannot apply
            notes.append(f"{pid} capped at {cap:.0%} of '{spec.name}'.")
    return [MixItem(pid, share) for pid, share in items.items()], notes


def build_plan(profile: Profile, cap: CapacityResult, decisions: list[GateDecision], mixes: dict[str, list[tuple[str, float]]],
               bundle, source: str = "planner") -> Plan:
    rules, shelf, assumptions = bundle.rules, bundle.shelf, bundle.assumptions
    steps, start, surplus_after, notes = priority_steps(profile, cap, rules)
    specs = bucket_specs(profile, decisions, rules)
    products = {p["id"]: p for p in shelf["products"]}
    returns = assumptions["returns_pa"]
    infl = assumptions["inflation_pa"]["value"]

    buckets: list[Bucket] = []
    for spec in specs:
        mix, n = normalise_mix(mixes.get(spec.id, []), spec)
        notes += n
        b = Bucket(spec.id, spec.name, spec.goal.horizon_years if spec.goal else None, mix)
        if mix:
            b.assumed_return_pa = sum(m.share * returns.get(m.product_id, {"value": 0})["value"] for m in mix)
        buckets.append(b)

    # Allocate the post-priority surplus: nearest goals first, each up to its SIP need; rest to general.
    remaining = surplus_after
    for b, spec in zip(buckets, specs):
        if spec.goal is None:
            continue
        g = spec.goal
        months_left = int(round(g.horizon_years * 12)) - (start - 1)
        b.target_future = G.inflate(g.target_today, infl, g.horizon_years)
        if months_left <= 0 or not b.mix:
            b.fundable = False if months_left <= 0 else None
            if months_left <= 0:
                b.shortfall = b.target_future - g.saved_so_far
                notes.append(f"'{g.name}' falls inside the priority period; consider moving its date.")
            continue
        b.sip_needed = round_up_to(G.sip_needed(b.target_future, b.assumed_return_pa, months_left, g.saved_so_far), ROUND_STEP)
        b.monthly = min(b.sip_needed, max(remaining, 0.0))
        remaining -= b.monthly
        b.fundable = b.monthly >= b.sip_needed - 1e-6
        if not b.fundable:
            b.shortfall = b.sip_needed - b.monthly
    general = buckets[-1]
    general.monthly = max(0.0, remaining) if general.mix else 0.0

    investing = 0.0
    risky = 0.0
    rho_by_goal: dict[str, float] = {}
    for b in buckets:
        for m in b.mix:
            m.monthly = b.monthly * m.share
        investing += b.monthly
        r = sum(m.share for m in b.mix if m.product_id in products and is_risky(products[m.product_id], rules))
        risky += b.monthly * r
        if b.id != GENERAL:
            rho_by_goal[b.id] = r

    for b in buckets:
        if b.monthly <= 0:
            continue
        parts = ", ".join(f"{inr(m.monthly)} in {products.get(m.product_id, {'name': m.product_id})['name']}"
                          for m in b.mix if m.monthly > 0)
        if b.id == GENERAL:
            text = f"From month {start}, invest the remaining {inr(b.monthly)}/month for the long term: {parts}."
        else:
            fund = "" if b.fundable else f" This covers {b.monthly / b.sip_needed:.0%} of the {inr(b.sip_needed)} needed."
            text = (f"From month {start}, put {inr(b.monthly)}/month towards '{b.name}' "
                    f"(about {inr(b.target_future)} in {b.horizon_years:g} years after inflation): {parts}.{fund}")
        steps.append(Step(order=len(steps) + 1, action="invest", text=text, monthly=b.monthly, start_month=start,
                          goal_id=None if b.id == GENERAL else b.id,
                          target=b.target_future or 0.0))

    # Savings far above the emergency-fund target sit idle; suggest moving the extra in parts (only when no
    # priority step needs the money first).
    ef_target = rules["capacity"]["emergency_months"] * profile.expenses_monthly
    excess = profile.liquid_savings - ef_target
    general = next((b for b in buckets if b.id == GENERAL and b.mix), None)
    if general and not ({"R1", "R2", "R3", "R4"} & cap.rule_ids) and excess >= max(50_000, profile.expenses_monthly):
        part = round_up_to(excess / 6, ROUND_STEP)
        steps.append(Step(order=len(steps) + 1, action="deploy_excess_savings", monthly=part, months=6, target=excess,
                          text=f"You hold {inr(excess)} more than your {rules['capacity']['emergency_months']}-month emergency "
                               f"fund ({inr(ef_target)}). If it isn't set aside for a planned expense, it can join the same "
                               f"long-term mix in 6 parts of about {inr(part)} a month rather than all on one day."))

    rho = risky / investing if investing > 0 else 0.0
    return Plan(steps, buckets, profile.monthly_surplus, investing, start, rho, rho_by_goal, source, notes)


def safe_mixes(profile: Profile, suit: str, decisions: list[GateDecision], bundle) -> dict[str, list[tuple[str, float]]]:
    """Deterministic mixes from config (fallback plan and what-if). Monotone in suitability by construction."""
    rules, shelf = bundle.rules, bundle.shelf
    out = {}
    for spec in bucket_specs(profile, decisions, rules):
        short = spec.goal is not None and spec.goal.horizon_years < rules["rules"]["R7"]["min_goal_years"]
        template = shelf["safe_mix"]["short_goal" if short else suit]
        allowed_ids = {p["id"] for p in spec.allowed}
        mix = [(i["product"], i["share"]) for i in template if i["product"] in allowed_ids]
        if not mix:
            fallback = [p["id"] for p in spec.allowed if not is_risky(p, rules) and not p.get("lock_in_years")]
            mix = [(fallback[0], 1.0)] if fallback else []
        out[spec.id] = mix
    return out


def no_risky_options(specs: list[BucketSpec], rules: dict) -> bool:
    return all(not any(is_risky(p, rules) for p in s.allowed) for s in specs)


