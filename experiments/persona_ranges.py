"""Where the benchmark personas sit against published Indian household figures (paper plan §3, item 8).

    python -m experiments.persona_ranges experiments/data/personas_v1.jsonl

Prints a markdown table of the personas' distribution (quantiles and shares) next to the published reference for each
quantity, with the source. The personas are young urban salaried earners by design, so they sit above the all-India
and all-urban averages; the table makes that visible rather than claiming survey matching.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from finadvisor.advisor.profile import Profile

# Published figures (as cited; see docs/EXPERIMENTS.md §4 for the full references).
REFERENCE = {
    "take_home": ("Urban regular-wage/salaried earnings ≈ ₹24,434 a month (PLFS, Apr–Jun 2024 quarter; all-India "
                  "regular salaried ≈ ₹20,702 in 2023-24, Economic Survey 2024-25)"),
    "expenses": ("Urban average monthly per-capita consumption ₹6,459 (HCES 2022-23; ₹6,996 in 2023-24); a household of "
                 "3–4 spends ₹20,000–28,000"),
    "indebted": "22.4 % of urban households carried any debt (AIDIS 2019, reference date 30 Jun 2018)",
    "debt": "Average debt of an indebted urban household ₹5.37 lakh; ₹1.20 lakh over all urban households (AIDIS 2019)",
    "insurance": ("Household Finance Committee (RBI, 2017): the average household holds 77 % of wealth in real estate, "
                  "11 % in gold and 5 % in financial assets; pension wealth is nearly absent; 51 % of households without "
                  "insurance said they could not afford it (2015)"),
}


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * (len(xs) - 1)))]


def fmt_inr(v):
    return f"₹{v:,.0f}"


def main(path: str) -> None:
    rows = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    ps = [Profile(**r["profile"]) for r in rows]
    n = len(ps)
    take = [p.take_home_monthly for p in ps]
    exp = [p.expenses_monthly for p in ps]
    ratio = [p.expenses_monthly / p.take_home_monthly for p in ps]
    months = [p.liquid_savings / p.expenses_monthly for p in ps]
    emi = [p.total_emi / p.take_home_monthly for p in ps]
    indebted = [p for p in ps if p.debts]
    debt = [sum(d.outstanding for d in p.debts) for p in indebted]
    deps = [p.dependants for p in ps]
    life = [p for p in ps if p.dependants]
    life_mult = [p.life_cover / (12 * p.take_home_monthly) for p in life]

    def quant(xs, f=lambda v: f"{v:,.0f}"):
        return f"{f(q(xs, 0.1))} / {f(q(xs, 0.5))} / {f(q(xs, 0.9))}"

    lines = [
        "| Quantity | Personas (p10 / median / p90, or share) | Published reference |", "|---|---|---|",
        f"| Take-home pay a month | {quant(take, fmt_inr)} | {REFERENCE['take_home']} |",
        f"| Expenses a month | {quant(exp, fmt_inr)} (expense ratio {quant(ratio, lambda v: f'{v:.0%}')}) | {REFERENCE['expenses']} |",
        f"| Emergency savings, months of expenses | {quant(months, lambda v: f'{v:.1f}')}; {sum(m < 6 for m in months) / n:.0%} below 6 months | — (no national figure; the Health Check's own target is 6 months) |",
        f"| Any loan | {len(indebted) / n:.0%} of personas | {REFERENCE['indebted']} |",
        f"| Debt of indebted personas | {quant(debt, fmt_inr)} | {REFERENCE['debt']} |",
        f"| EMIs as a share of take-home (all personas) | {quant(emi, lambda v: f'{v:.0%}')}; {sum(e > 0.4 for e in emi) / n:.0%} above 40 % | — |",
        f"| Dependants | mean {statistics.mean(deps):.1f}; {sum(d == 0 for d in deps) / n:.0%} with none | — |",
        f"| Life cover of personas with dependants, × annual take-home | {quant(life_mult, lambda v: f'{v:.0f}')}; {sum(m < 15 for m in life_mult) / max(1, len(life)):.0%} below 15× | {REFERENCE['insurance']} |",
        f"| Health cover | {sum(p.health_cover == 0 for p in ps) / n:.0%} none; {sum(p.health_cover >= 5e5 for p in ps) / n:.0%} ≥ ₹5 lakh | {REFERENCE['insurance']} |",
        f"| Card bill unpaid / costly loan | {sum(not p.card_dues_paid_in_full for p in ps) / n:.0%} / {sum(any(d.kind in ('personal', 'bnpl') for d in p.debts) for p in ps) / n:.0%} | — |",
        f"| Age | {quant([p.age for p in ps])} | target users: earners in their 20s–40s |",
    ]
    print(f"{n} personas ({Path(path).name})\n")
    print("\n".join(lines))
    print("\nReading: the personas are stratified so every rule fires often, and they are urban salaried earners with "
          "take-home from ₹22,000 to ₹3.5 lakh; the median sits above the urban salaried average and the debt and "
          "cover gaps are deliberately more common than in the population. They are a test bed for the rules, not a "
          "sample of India.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "experiments/data/personas_v1.jsonl")
