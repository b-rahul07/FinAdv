"""A second working of the written rules, compared with the engines on every persona.

    python -m experiments.rules_rework

`work` follows docs/handcheck/rules.md step by step on the raw persona facts: plain arithmetic, the limits as the
sheet states them, the questionnaire key read from the sheet's own table. It imports nothing from the capacity,
willingness or gate code. Agreement on all personas shows that the written rules (which the paper describes) and the
engines (which produced the results) say the same thing, with no behaviour hidden in the code.

What this is not: the hand-check. It was written by the same author as the sheet, with the engine's code in view, so
it is a specification-against-code check and is reported as that. The independent check is two people working
docs/handcheck/ by hand (experiments/handcheck.py).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from experiments import personas
from experiments.run import ROOT
from finadvisor.advisor.profile import Profile
from finadvisor.configs import default_bundle

RULES_MD = ROOT / "docs" / "handcheck" / "rules.md"
PERSONAS = ROOT / "experiments" / "data" / "personas_v1.jsonl"
ORDER = ("low", "medium", "high")


def score_key(text: str) -> dict[str, dict[str, int]]:
    """The questionnaire table of rules.md: question -> option -> points."""
    key = {}
    for n, cells in re.findall(r"^\| (\d+) \| (.+) \|$", text, re.M):
        vals = [c.strip() for c in cells.split("|")]
        key[n] = {opt: int(v) for opt, v in zip("abcd", vals) if v.isdigit()}
    return key


def work(f: dict, key: dict[str, dict[str, int]]) -> dict:
    """One person's four answers, by the five steps of rules.md. `f` is the persona's facts as stored."""
    take, loans = f["take_home_monthly"], f.get("debts", [])
    # Step 1
    months = f["liquid_savings"] / f["expenses_monthly"]
    emergency = min(months / 6, 1)
    share = sum(d["emi_monthly"] for d in loans) / take
    emis = 1 if share <= 0.40 else 0.40 / share
    life = 1 if f["dependants"] == 0 else min(f["life_cover"] / (15 * 12 * take), 1)
    needed = max(500000, 0.50 * 12 * take)
    health = min(f["health_cover"] / needed, 1)
    costly = (not f["card_dues_paid_in_full"]
              or any(d["kind"] in ("personal", "bnpl") for d in loans)
              or any(d["kind"] in ("education", "other") and (d.get("rate_pa") or 0) >= 14 for d in loans))
    debt = 0 if costly else 1
    # Step 2
    score = min(emergency, emis, life, health, debt)
    capacity = "low" if score < 0.5 else ("high" if score == 1 else "medium")
    # Step 3
    fired = [r for r, on in (("R1", months < 6), ("R2", life < 1), ("R3", health < 1), ("R4", debt == 0),
                             ("R5", share > 0.40), ("R6", capacity == "low" or f["experience"] == "none"),
                             ("R7", any(g["horizon_years"] < 3 for g in f.get("goals", [])))) if on]
    # Step 4
    total = sum(key[str(n)][opt] for n, opt in f["gl_answers"].items())
    willingness = "low" if total <= 22 else ("medium" if total <= 28 else "high")
    if f["experience"] == "none" and willingness == "high":
        willingness = "medium"
    # Step 5
    suitability = min(capacity, willingness, key=ORDER.index)
    return {"capacity": capacity, "rules": fired, "willingness": willingness, "suitability": suitability}


def compare(path: Path = PERSONAS) -> dict:
    key, bundle = score_key(RULES_MD.read_text(encoding="utf-8")), default_bundle()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    out = {f: [] for f in ("capacity", "rules", "willingness", "suitability")}
    for row in rows:
        mine, engine = work(row["profile"], key), personas.label(Profile(**row["profile"]), bundle)
        for field in out:
            if mine[field] != engine[field]:
                out[field].append(row["id"])
    return {"n": len(rows), "differ": out}


if __name__ == "__main__":
    res = compare()
    for field, ids in res["differ"].items():
        print(f"{field}: {res['n'] - len(ids)} of {res['n']} agree" + (f"; differ: {', '.join(ids)}" if ids else ""))
