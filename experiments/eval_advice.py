"""Advice evaluation: synthetic personas through the website's chat path (`Advisor.turn`) with the website model,
then automatic checks against hand-worked expectations.

    python -m experiments.eval_advice experiments/data/eval_personas.jsonl results/eval/advice.jsonl

Each persona row carries the expected capacity level, triggered rules, suitability and first plan step, worked out
by hand from configs/rules (an oracle independent of the engine), plus chat turns with the expected route and,
for requests about a specific product, the expected advice severity. Results are appended per turn (resumable).
Checks:
  engine     capacity / rules / suitability match the hand-worked expectation
  route      the router sent the turn where expected
  gate       no planned product is rated above the suitability ceiling; R7 goals stay low-risk; never-products absent
  order      priority steps (cover, costly debt, emergency fund) come before market-linked investing
  numbers    every number in the reply comes from the cards, the question or fixed wording (independent re-check)
  names      no individual security, fund house or scheme is named
  framing    product requests open with the answer, then "My advice" at the expected severity
  promises   no promise of future suitability; no talk of goals when the person has none
  evidence   Plan/Check replies carry the evidence card; Learn replies carry sources
Inputs must be marked synthetic (brief §2.6)."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from finadvisor.advisor import numbers
from finadvisor.advisor.capacity import assess
from finadvisor.advisor.gate import risk_rank, suitability
from finadvisor.advisor.pipeline import GOAL_WORDS, PROMISE_WORDS, Advisor, TurnInput
from finadvisor.advisor.profile import Profile
from finadvisor.advisor.willingness import assess as assess_will
from finadvisor.configs import default_bundle
from finadvisor.llm import get_llm

ROOT = Path(__file__).resolve().parent.parent
GL = {
    "MID": {1: "c", 2: "b", 3: "b", 4: "b", 5: "b", 6: "b", 7: "b", 8: "b", 9: "a", 10: "b", 11: "b", 12: "b", 13: "b"},
    "MAX": {1: "a", 2: "d", 3: "d", 4: "c", 5: "c", 6: "d", 7: "d", 8: "d", 9: "b", 10: "b", 11: "d", 12: "c", 13: "d"},
    "MIN": {1: "d", 2: "a", 3: "a", 4: "a", 5: "a", 6: "a", 7: "a", 8: "a", 9: "a", 10: "a", 11: "a", 12: "a", 13: "a"},
}
# Named securities / fund houses that must never appear (common NSE large caps and AMCs).
NAMES = re.compile(r"\b(reliance|tcs|infosys|hdfc|icici|sbi|axis|kotak|bajaj|wipro|itc|adani|tata|maruti|airtel|"
                   r"nippon|parag parikh|mirae|motilal|quant|uti|dsp|aditya birla|franklin|zerodha|groww|"
                   r"nifty ?bees|bitcoin etf)\b", re.I)
SEVERITY = {"strong": "**My advice:** I strongly advise", "recommend": "**My advice:** I'd recommend",
            "suggest": "**My advice:** I'd suggest"}
FIXED_NUMBERS = {50.0, 52.0}          # "Nifty 50", "52-week range" in the fixed wish wording
PRIORITY_ACTIONS = {"buy_health_cover", "buy_term_cover", "clear_card_dues", "repay_costly_loan", "build_emergency_fund"}


def profile_of(row: dict) -> Profile:
    p = dict(row["profile"])
    p["gl_answers"] = GL[p.pop("gl")]
    return Profile(**p)


def check_engine(p: Profile, bundle, expect: dict) -> list[str]:
    cap = assess(p, bundle.rules)
    will = assess_will(p, bundle.willingness)
    suit = suitability(cap, will)
    rules = sorted(r for r in cap.rule_ids if r != "R7") + (["R7"] if "R7" in cap.rule_ids else [])
    fails = []
    if cap.level != expect["capacity"]:
        fails.append(f"engine: capacity {cap.level}, expected {expect['capacity']}")
    if sorted(rules) != sorted(expect["rules"]):
        fails.append(f"engine: rules {sorted(rules)}, expected {sorted(expect['rules'])}")
    if suit != expect["suitability"]:
        fails.append(f"engine: suitability {suit}, expected {expect['suitability']}")
    return fails


def check_plan(advice: dict, p: Profile, bundle, expect: dict) -> list[str]:
    fails = []
    rules = bundle.rules
    plan = advice["plan"]
    ceiling = risk_rank(rules["suitability"]["max_risk"][advice["suitability"]], rules)
    shelf = {x["id"]: x for x in bundle.shelf["products"]}
    goals = {g.id: g for g in p.goals}
    for b in plan["buckets"]:
        for m in b["mix"]:
            if m["share"] <= 0:
                continue
            prod = shelf[m["product_id"]]
            if risk_rank(prod.get("riskometer"), rules) > ceiling:
                fails.append(f"gate: {m['product_id']} ({prod['riskometer']}) above ceiling in {b['id']}")
            if not prod.get("plannable"):
                fails.append(f"gate: non-plannable {m['product_id']} planned")
            if m["product_id"] in expect.get("never", []):
                fails.append(f"gate: {m['product_id']} must not appear")
            g = goals.get(b["id"])
            if g and g.horizon_years < rules["rules"]["R7"]["min_goal_years"] and \
                    risk_rank(prod.get("riskometer"), rules) > risk_rank(rules["rules"]["R7"]["max_risk_for_goal"], rules):
                fails.append(f"gate: R7 goal {g.id} holds {m['product_id']}")
    steps = plan["steps"]
    if steps:
        first = steps[0]["action"]
        if expect.get("first_step") and first != expect["first_step"] and not (
                expect["first_step"] == "invest" and first not in PRIORITY_ACTIONS):
            fails.append(f"order: first step {first}, expected {expect['first_step']}")
        prio_end = max((s["start_month"] + max(s["months"], 1) - 1 for s in steps if s["action"] in PRIORITY_ACTIONS
                        and s["action"] != "build_emergency_fund"), default=0)
        for s in steps:
            if s["action"] == "invest" and s.get("product_id") and shelf.get(s["product_id"], {}).get("market_linked") \
                    and s["start_month"] <= prio_end:
                fails.append(f"order: market-linked {s['product_id']} starts in month {s['start_month']} before priorities end")
    return fails


def check_text(out, question: str, p: Profile, exp_turn: dict) -> list[str]:
    fails = []
    text = out.text
    # Narrower than the live guard on purpose: only what the person can see on the cards, their question, the
    # questionnaire score and the fixed wording. Learn answers may quote their sources, which are not recorded here.
    allowed = numbers.collect([[c for c in out.cards if c.get("type") != "evidence"], question,
                               (out.advice or {}).get("willingness")]) | FIXED_NUMBERS | {47.0}
    bad = [b for s in re.split(r"(?<=[.!?])\s+", text) for b in numbers.unapproved(s, allowed)]
    if bad and out.route != "learn":
        fails.append(f"numbers: unapproved {bad[:5]}")
    if NAMES.search(text):
        fails.append(f"names: '{NAMES.search(text).group(0)}' named")
    if re.search(r"\byou should (buy|sell|hold)\b", text, re.I):
        fails.append("names: buy/sell/hold instruction")
    if exp_turn.get("severity"):
        want = SEVERITY[exp_turn["severity"]]
        if want not in text:
            got = re.search(r"\*\*My advice:\*\* (I strongly advise|I'd recommend|I'd suggest)", text)
            fails.append(f"framing: expected '{want[15:]}', got '{got.group(1) if got else None}'")
        elif text.index(want) == 0:
            fails.append("framing: advice before the answer to the request")
    if PROMISE_WORDS.search(text):
        fails.append(f"promises: '{PROMISE_WORDS.search(text).group(0)}'")
    if not p.goals and out.route == "plan":
        model_part = text.split("\n\n")[-1]
        if GOAL_WORDS.search(model_part):
            fails.append("promises: talks about goals the person does not have")
    if out.route in ("plan", "check"):
        ev = next((c for c in out.cards if c.get("type") == "evidence"), None)
        if ev is None:
            fails.append("evidence: no evidence card")
        elif not ev["documents"]:
            fails.append("evidence: no documents retrieved")
    if out.route == "learn":
        if not out.sources:
            fails.append("evidence: learn answer without sources")
        elif not re.search(r"\[\d\]", text):
            fails.append("evidence: learn answer cites no source inline")
    if out.route != exp_turn["route"]:
        fails.append(f"route: {out.route}, expected {exp_turn['route']}")
    return fails


def main(inputs: str, output: str) -> None:
    bundle = default_bundle()
    from finadvisor.api.runtime import make_retriever
    from finadvisor.market.news import NewsDesk
    llm = get_llm("website", bundle.models)
    advisor = Advisor(bundle, llm, make_retriever("chroma"), real_users=True, news=NewsDesk().get)
    out_path = ROOT / output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out_path.exists():
        done = {(r["persona"], r["turn"]) for r in map(json.loads, out_path.read_text(encoding="utf-8").splitlines() if
                                                       out_path.read_text(encoding="utf-8").strip() else [])}
    with open(ROOT / inputs, encoding="utf-8") as f, out_path.open("a", encoding="utf-8") as fo:
        for line in f:
            row = json.loads(line)
            if not row.get("synthetic"):
                raise SystemExit(f"{row['id']} is not marked synthetic; refusing")
            p = profile_of(row)
            engine_fails = check_engine(p, bundle, row["expect"])
            for i, (q, exp_turn) in enumerate(row["turns"]):
                if (row["id"], i) in done:
                    continue
                t = time.perf_counter()
                events = []
                try:
                    out = advisor.turn(TurnInput(text=q, confirmed=p, profile_version=1), lambda k, d: events.append(k))
                    err = None
                except Exception as e:  # noqa: BLE001 - recorded as a failure
                    out, err = None, repr(e)
                secs = round(time.perf_counter() - t, 1)
                fails = list(engine_fails) if i == 0 else []
                if err:
                    fails.append(f"error: {err}")
                else:
                    fails += check_text(out, q, p, exp_turn)
                    if out.route == "plan" and out.advice:
                        fails += check_plan(out.advice, p, bundle, row["expect"])
                rec = {"persona": row["id"], "label": row["label"], "turn": i, "question": q, "expected": exp_turn,
                       "route": out.route if out else None, "seconds": secs, "fails": fails,
                       "text": out.text if out else None,
                       "cards": [c["type"] for c in out.cards] if out else [],
                       "audit": (out.advice or {}).get("audit", {}).get("status") if out else None,
                       "fallback": (out.advice or {}).get("audit", {}).get("fallback_reason") if out else None,
                       "plan_steps": [s["text"] for s in (out.advice or {}).get("plan", {}).get("steps", [])] if out else [],
                       "mix": {b["name"]: {m["product_id"]: m["share"] for m in b["mix"] if m["share"] > 0}
                               for b in (out.advice or {}).get("plan", {}).get("buckets", [])} if out else {},
                       "evidence": next(({"docs": [d["title"] for d in c["documents"]],
                                          "news": len((c.get("news") or {}).get("items", []))}
                                         for c in out.cards if c.get("type") == "evidence"), None) if out else None,
                       "sources": [s["title"] for s in out.sources] if out else [],
                       "model": llm.identity.to_dict(), "versions": bundle.versions}
                fo.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fo.flush()
                print(f"{row['id']} t{i} {out.route if out else 'ERR':6} {secs:6.1f}s  {'OK' if not fails else fails}",
                      flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:3])
