"""The pack two people need to work out the hand-check sheet without reading code or JSON.

    python -m experiments.handcheck_pack            # writes docs/handcheck/{rules.md, worksheet.md, answer_sheet.csv}

rules.md      the written rules, rendered from the versioned configs (rules and willingness) so its numbers are the
              configs' numbers; a worked example for a person who is not on the sheet
worksheet.md  the 45 personas of experiments/data/handcheck_v1.csv as readable facts (no derived values)
answer_sheet.csv  the columns experiments/handcheck.py reads; each grader fills a copy

The committed copies are checked by a test, so they cannot drift from the configs or the sheet.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from experiments.run import ROOT
from finadvisor.advisor.profile import Profile
from finadvisor.calc.money import inr
from finadvisor.configs import default_bundle

SHEET = ROOT / "experiments" / "data" / "handcheck_v1.csv"
OUT = ROOT / "docs" / "handcheck"

LOAN = {"home": "home loan", "car": "car loan", "personal": "personal loan", "education": "education loan",
        "bnpl": "pay-later (BNPL) dues", "credit_card": "credit-card balance", "gold": "gold loan",
        "two_wheeler": "two-wheeler loan", "other": "other loan"}

# A person who is not on the sheet, worked by hand below; a test checks the engines give the same answers.
EXAMPLE = Profile(
    age=31, take_home_monthly=80000, expenses_monthly=40000, liquid_savings=160000,
    debts=[{"kind": "car", "outstanding": 400000, "rate_pa": 9.5, "emi_monthly": 12000},
           {"kind": "education", "outstanding": 300000, "rate_pa": 9.0, "emi_monthly": 8000}],
    card_dues_paid_in_full=True, dependants=2, life_cover=10000000, health_cover=500000,
    goals=[{"id": "g1", "name": "Car", "kind": "vehicle", "target_today": 600000, "horizon_years": 2},
           {"id": "g2", "name": "Retirement", "kind": "retirement", "target_today": 30000000, "horizon_years": 25}],
    experience="beginner",
    gl_answers={1: "b", 2: "c", 3: "b", 4: "c", 5: "b", 6: "c", 7: "b", 8: "c", 9: "b", 10: "b", 11: "b", 12: "b", 13: "b"})
EXAMPLE_ANSWER = {"capacity": "medium", "rules": ["R1", "R2", "R7"], "willingness": "high", "suitability": "medium"}


def facts(p: Profile) -> list[str]:
    loans = "; ".join(
        f"{LOAN[d.kind]}, {inr(d.outstanding)} outstanding"
        + (f" at {d.rate_pa:g}% a year" if d.rate_pa is not None else "") + f", EMI {inr(d.emi_monthly)} a month"
        for d in p.debts) or "none"
    goals = "; ".join(f"{g.name} in {g.horizon_years:g} year{'' if g.horizon_years == 1 else 's'}" for g in p.goals) or "none"
    answers = " · ".join(f"{n} {p.gl_answers[n]}" for n in sorted(p.gl_answers))
    return [f"- Take-home {inr(p.take_home_monthly)} a month · expenses {inr(p.expenses_monthly)} a month · "
            f"emergency savings {inr(p.liquid_savings)}",
            f"- Dependants {p.dependants} · life cover {inr(p.life_cover)} · health cover {inr(p.health_cover)}",
            f"- Loans: {loans}",
            f"- Credit-card bill paid in full every month: {'yes' if p.card_dues_paid_in_full else 'no'}",
            f"- Goals: {goals}",
            f"- Investing experience: {p.experience}",
            f"- Questionnaire answers: {answers}"]


def rules_md(bundle) -> str:
    c, w = bundle.rules["capacity"], bundle.willingness
    months, cap, mult = c["emergency_months"], c["emi_cap"], c["life_cover_multiple"]
    floor, share = c["health_cover_min_inr"], c["health_cover_income_share"]
    costly, lv = c["costly_debt"], c["levels"]
    r7 = bundle.rules["rules"]["R7"]["min_goal_years"]
    low_max, med_max = w["bands"]["low_max"], w["bands"]["medium_max"]
    if c.get("s_D_form") != "ratio" or lv["high_at"] != 1.0:
        raise SystemExit("this sheet describes the 'ratio' EMI score and High at exactly 1; rewrite it for this config")
    kinds = " or ".join(LOAN[k] for k in costly["kinds"])
    key = ["| Question | a | b | c | d |", "|---|---|---|---|---|"]
    for item in w["items"]:
        s = {o["key"]: o["score"] for o in item["options"]}
        key.append(f"| {item['n']} | " + " | ".join(str(s.get(k, "–")) for k in "abcd") + " |")
    caps = [f"If investing experience is \"{exp}\", willingness is at most {level.capitalize()}."
            for exp, level in w.get("experience_cap", {}).items()]
    ex = EXAMPLE
    return "\n".join([
        f"# Hand-check rules ({bundle.rules['version']}, {w['version']})",
        "",
        "You are checking our rule engine by working the same rules out by hand. For each person on the worksheet, "
        "write four answers in your copy of the answer sheet: capacity, rules fired, willingness, suitability.",
        "",
        "## Before you start",
        "",
        "- Work alone. Do not compare with the other grader until both sheets are handed in.",
        "- Do not run the project's code and do not open `experiments/data/personas_v1.jsonl`; it holds the engine's answers.",
        "- A calculator or a spreadsheet for the arithmetic is fine.",
        "- If a rule seems unclear for a person, apply it as written here and say so in the notes column. Those notes "
        "are results too.",
        "- Do not round before comparing with a limit. Exactly on a limit: read the wording (\"below\", \"above\", \"at least\").",
        "",
        "## Step 1: five scores, each from 0 to 1",
        "",
        f"1. **Emergency.** Months = emergency savings ÷ monthly expenses. Score = months ÷ {months}, but never above 1.",
        f"2. **EMIs.** Share = all EMIs added together ÷ monthly take-home. Score = 1 if the share is {cap:.0%} or less; "
        f"otherwise {cap:.2f} ÷ share.",
        f"3. **Life cover.** With no dependants the score is 1. Otherwise score = life cover ÷ ({mult} × annual take-home), "
        "never above 1. Annual take-home is 12 × monthly take-home.",
        f"4. **Health cover.** Needed = the larger of {inr(floor)} and {share:.0%} of annual take-home. "
        "Score = health cover ÷ needed, never above 1.",
        f"5. **Costly debt.** Score = 0 if the credit-card bill is not paid in full every month, or the person has a {kinds}, "
        f"or has any other loan without security (education loan, other loan) at {costly['unsecured_min_rate_pa']:g}% a year or more. "
        "Otherwise 1. Home, car, gold and two-wheeler loans are secured and never count here. A credit-card balance in the "
        "loans list does not count by itself; only the \"paid in full\" line does.",
        "",
        "## Step 2: capacity",
        "",
        f"Capacity score = the smallest of the five scores. **Low** if it is below {lv['low_below']}; **High** if it is "
        "exactly 1 (all five scores are 1); otherwise **Medium**.",
        "",
        "## Step 3: rules fired",
        "",
        f"- **R1** months of emergency savings below {months}.",
        "- **R2** life-cover score below 1.",
        "- **R3** health-cover score below 1.",
        "- **R4** costly-debt score is 0.",
        f"- **R5** EMI share above {cap:.0%}.",
        "- **R6** capacity is Low, or investing experience is \"none\".",
        f"- **R7** any goal less than {r7} years away.",
        "",
        "Write them as `R1 R4 R7`. If no rule fires, write `none` (an empty cell counts as not answered).",
        "",
        "## Step 4: willingness",
        "",
        "Look up each questionnaire answer in the table and add the thirteen numbers (questions 9 and 10 are both added).",
        "",
        *key,
        "",
        f"Total {low_max} or less is **Low**; {low_max + 1} to {med_max} is **Medium**; {med_max + 1} or more is **High**. "
        + " ".join(caps),
        "",
        "## Step 5: suitability",
        "",
        "Suitability = the lower of capacity and willingness.",
        "",
        "## Worked example (this person is not on the sheet)",
        "",
        *facts(ex),
        "",
        "1. Emergency: 1,60,000 ÷ 40,000 = 4 months; score 4 ÷ 6 = 0.67.",
        "2. EMIs: 12,000 + 8,000 = 20,000; share 20,000 ÷ 80,000 = 25%; score 1.",
        "3. Life cover: annual take-home 9,60,000; needed 15 × 9,60,000 = 1,44,00,000; score 1,00,00,000 ÷ 1,44,00,000 = 0.69.",
        "4. Health cover: needed = larger of 5,00,000 and 4,80,000 = 5,00,000; score 1.",
        "5. Costly debt: card paid in full, no personal loan, education loan at 9% (under 14%); score 1.",
        "",
        "Capacity score = 0.67, so capacity is **Medium**. Rules: R1 (4 months), R2 (life score below 1), R7 (car in 2 years); "
        "R6 does not fire (capacity is not Low, experience is not \"none\"). Questionnaire: 3+3+2+3+2+3+2+3+3+3+2+2+2 = 33, "
        "so willingness is **High**. Suitability = lower of Medium and High = **Medium**.",
        "",
        "Answer-sheet row: `medium`, `R1 R2 R7`, `high`, `medium`.",
        ""])


def worksheet_md(rows: list[dict]) -> str:
    out = ["# Hand-check worksheet", "",
           f"{len(rows)} people. Work each one out with `rules.md` and write the four answers in your copy of "
           "`answer_sheet.csv`. All amounts are rupees.", ""]
    for row in rows:
        p = Profile(**json.loads(row["facts"]))
        out += [f"## {row['id']}", "", *facts(p), ""]
    return "\n".join(out)


def write(out: Path = OUT) -> None:
    with SHEET.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out.mkdir(parents=True, exist_ok=True)
    (out / "rules.md").write_text(rules_md(default_bundle()), encoding="utf-8", newline="\n")
    (out / "worksheet.md").write_text(worksheet_md(rows), encoding="utf-8", newline="\n")
    cols = [c for c in rows[0] if c != "facts"]
    with (out / "answer_sheet.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for row in rows:
            w.writerow([row["id"], *[""] * (len(cols) - 1)])
    print(f"{len(rows)} people -> {out / 'rules.md'}, {out / 'worksheet.md'}, {out / 'answer_sheet.csv'}")


if __name__ == "__main__":
    write()
