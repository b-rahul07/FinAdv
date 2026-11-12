"""How the capacity rules line up with SEBI's Financial Health Check, the tool their thresholds come from.

    python -m experiments.sebi_check                    # all personas against the saved copy of the tool
    python -m experiments.sebi_check --live             # also re-read the live page and compare it with the saved copy
    python -m experiments.sebi_check --json results/paper/sebi_check.json

What the tool is. https://investor.sebi.gov.in/financial_health_check.html is a 14-question self-assessment. It asks
for no amounts and computes nothing: the visitor picks an option ("Do you have life insurance cover for at least 15 to
20 times your annual income?" Yes / No / Not applicable), each option carries a fixed colour, and the report lists the
advice text of every answer under red, amber or green. experiments/data/sebi_health_check_<date>.json is the page's
own question object (options, colours, advice texts, the two skips), saved with the date and the page's hash.

What can therefore be checked, and what cannot. Entering personas into the tool by hand would test nothing the page
source does not already say, because the person entering them would have to work out each ratio first. The check here
is the one the tool supports: for every persona, `answers` picks the option a truthful person with those facts would
choose, written from the question wording alone (it does not call the capacity engine); the tool's colour for that
option is read from the saved copy; and that is compared with whether the engine's rule fires. Agreement shows the
engine implements the tool's checks as worded. The differences are design choices and are listed with their counts.
The engine's arithmetic is checked separately against the written rules (experiments/rules_rework.py).

Not modelled by the engine: question 4 (knowing the policy's terms) and questions 9 to 14 (budget, retirement corpus,
sharing details, nomination, will). Not from the tool: R6 (complex products) and R7 (goals under three years).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from pathlib import Path

from experiments.run import ROOT
from finadvisor.advisor.capacity import assess
from finadvisor.advisor.profile import Profile
from finadvisor.configs import default_bundle

URL = "https://investor.sebi.gov.in/financial_health_check.html"
SNAPSHOT = ROOT / "experiments" / "data" / "sebi_health_check_2026-11-12.json"
PERSONAS = ROOT / "experiments" / "data" / "personas_v1.jsonl"
COLOURS = {"#EC1212": "red", "#907326": "amber", "#008A27": "green", "": "none"}

# Loans the profile records as taken without security. Card balances are question 6, not question 7.
UNSECURED = ("personal", "bnpl", "education", "other")


def parse_page(raw: bytes) -> list[dict]:
    """The questions as the page holds them: option texts, the colour of each option, its advice text."""
    text = raw.decode("cp1252", errors="replace")
    m = re.search(r"var jsonobj\s*=\s*(\{.*?\})\s*;\s*\$\(document\)", text, re.S)
    if not m:
        raise SystemExit("the page no longer holds its questions in jsonobj; read it by hand and make a new snapshot")
    out = []
    for q in json.loads(m.group(1))["data"]["questions"]:
        colours, advice = q["optionsColor"], q["optionsHint"]
        out.append({
            "id": q["ques_id"], "question": re.sub(r"\s+", " ", q["question"].replace("<br>", " ")).strip(),
            "note": q["hints"],
            "options": [{"text": o, "colour": COLOURS.get(colours[i + 1], "none") if i + 1 < len(colours) else "none",
                         "advice": re.sub(r"<[^>]+>", "", advice[i]) if i < len(advice) else ""}
                        for i, o in enumerate(q["options"][1:])]})          # options[0] is the "Select" placeholder
    return out


def fetch() -> bytes:
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (research check of a public page)"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def snapshot(raw: bytes, date: str) -> dict:
    return {"source": URL, "retrieved": date, "page_sha256": hashlib.sha256(raw).hexdigest(),
            "skips": [{"when": "question 1 answered 'No'", "skips": 2},
                      {"when": "question 3 answered 'I do not have any health insurance'", "skips": 4}],
            "questions": parse_page(raw)}


def answers(p: Profile) -> dict[int, int]:
    """Question -> index of the option a truthful person with these facts picks. From the question wording only."""
    a: dict[int, int] = {1: 0 if p.dependants > 0 else 1}
    if p.dependants > 0:                                   # Q2 is skipped when nobody depends on you
        # "life insurance cover for at least 15 to 20 times your annual income": the lower bound, 15, is the pass mark
        a[2] = 0 if p.life_cover >= 15 * 12 * p.take_home_monthly else 1
    # "Do you have health insurance": the profile's health cover is personal cover, so any amount is "personal"
    a[3] = 2 if p.health_cover > 0 else 0
    # Q5 is a self-rating; its advice says the fund "should at least be six times your monthly expenses"
    months = p.liquid_savings / p.expenses_monthly if p.expenses_monthly > 0 else float("inf")
    a[5] = 2 if months >= 6 else (1 if months >= 1 else 0)
    # Q6: the profile records only whether the bill is paid in full
    a[6] = 1 if p.card_dues_paid_in_full else 3
    # "Do you have any personal loans or any unsecured loans?"
    owes = [d for d in p.debts if d.outstanding > 0 or d.emi_monthly > 0]
    a[7] = 0 if any(d.kind in UNSECURED for d in owes) else 1
    # "Is the total EMI ... greater than 40% of your monthly take-home pay?"
    emi = sum(d.emi_monthly for d in p.debts)
    a[8] = 2 if not owes else (0 if emi > 0.40 * p.take_home_monthly else 1)
    return a


# rule -> what counts as the tool flagging it
RULES = {
    "R1": "question 5 not green (the fund is under six months of expenses)",
    "R2": "question 2 red (dependants, and life cover under 15 times annual income)",
    "R3": "question 3 red (no health insurance)",
    "R4": "question 6 red (card bill not paid in full) or question 7 red (a personal or unsecured loan)",
    "R5": "question 8 red (EMIs above 40% of take-home pay)",
}


def tool_flags(p: Profile, snap: dict) -> dict[str, bool]:
    q = {x["id"]: x for x in snap["questions"]}
    colour = {i: q[i]["options"][o]["colour"] for i, o in answers(p).items()}
    return {"R1": colour[5] != "green", "R2": colour.get(2) == "red", "R3": colour[3] == "red",
            "R4": colour[6] == "red" or colour[7] == "red", "R5": colour[8] == "red"}


def known_difference(rule: str, side: str, p: Profile) -> str | None:
    """A mismatch that follows from a stated design choice; anything else needs looking at."""
    if rule == "R3" and side == "engine_only" and p.health_cover > 0:
        return ("has health cover, but under the larger of ₹5 lakh and half of annual take-home: the tool colours any "
                "cover green and gives that amount only as advice; the engine uses the amount as the pass mark")
    if rule == "R4" and side == "tool_only" and p.card_dues_paid_in_full:
        owed = [d for d in p.debts if d.outstanding > 0 or d.emi_monthly > 0]
        kinds = {d.kind for d in owed}
        rates = [d.rate_pa or 0 for d in owed if d.kind in ("education", "other")]
        if not kinds & {"personal", "bnpl"} and rates and max(rates) < 14:
            return ("the only unsecured loan is an education loan under 14% a year: the tool's question covers any "
                    "unsecured loan; the engine counts personal loans, pay-later dues and other unsecured loans at 14% "
                    "or more")
    return None


def compare(rows: list[dict], snap: dict, rules_cfg: dict) -> dict:
    out = {r: {"tool_flags_when": RULES[r], "both_flag": 0, "both_pass": 0, "engine_only": [], "tool_only": [],
               "explained": {}, "unexplained": []} for r in RULES}
    for row in rows:
        p = Profile(**row["profile"])
        fired, tool = assess(p, rules_cfg).rule_ids, tool_flags(p, snap)
        for r in RULES:
            e, t = r in fired, tool[r]
            if e == t:
                out[r]["both_flag" if e else "both_pass"] += 1
                continue
            side = "engine_only" if e else "tool_only"
            out[r][side].append(row["id"])
            why = known_difference(r, side, p)
            if why:
                out[r]["explained"].setdefault(why, []).append(row["id"])
            else:
                out[r]["unexplained"].append(row["id"])
    n = len(rows)
    for r in out.values():
        r["n"] = n
        r["agreement"] = (r["both_flag"] + r["both_pass"]) / n if n else None
    return out


def markdown(res: dict, snap: dict) -> str:
    lines = [f"Tool: {snap['source']}, read {snap['retrieved']} (page sha256 {snap['page_sha256'][:12]}…).", "",
             "| Rule | The tool flags it when | Both flag | Both pass | Engine only | Tool only | Agreement |",
             "|---|---|---|---|---|---|---|"]
    for rule, r in res.items():
        lines.append(f"| {rule} | {r['tool_flags_when']} | {r['both_flag']} | {r['both_pass']} | "
                     f"{len(r['engine_only'])} | {len(r['tool_only'])} | {r['agreement']:.1%} |")
    lines.append("")
    for rule, r in res.items():
        for why, ids in r["explained"].items():
            lines.append(f"- {rule}, {len(ids)} personas: {why}. ({', '.join(ids[:6])}{'…' if len(ids) > 6 else ''})")
        if r["unexplained"]:
            lines.append(f"- **{rule}: {len(r['unexplained'])} UNEXPLAINED mismatches, look at these: "
                         f"{', '.join(r['unexplained'])}**")
    if not any(r["unexplained"] for r in res.values()):
        lines.append("- No mismatch outside the stated design choices.")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("personas", nargs="?", default=str(PERSONAS))
    ap.add_argument("--snapshot", default=str(SNAPSHOT))
    ap.add_argument("--live", action="store_true", help="re-read the live page and compare it with the snapshot")
    ap.add_argument("--save", help="with --live: write a new snapshot to this path, dated today")
    ap.add_argument("--json")
    args = ap.parse_args()
    snap = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    if args.live:
        raw = fetch()
        same = parse_page(raw) == snap["questions"]
        print(f"Live page {'matches' if same else 'DIFFERS FROM'} the snapshot of {snap['retrieved']}.\n")
        if args.save:
            from datetime import date
            Path(args.save).write_text(
                json.dumps(snapshot(raw, date.today().isoformat()), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    rows = [json.loads(line) for line in Path(args.personas).read_text(encoding="utf-8").splitlines() if line.strip()]
    res = compare(rows, snap, default_bundle().rules)
    print(markdown(res, snap))
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps({"snapshot": {k: snap[k] for k in ("source", "retrieved", "page_sha256")},
                                               "rules": res}, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
