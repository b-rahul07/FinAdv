"""Baselines for the paper: the same model without FinAdvisor's pipeline.

    python -m experiments.baselines experiments/configs/B1_plain_llm.yaml
    python -m experiments.baselines experiments/configs/B2_llm_rag.yaml

B1 (plain LLM): the model gets the person's facts and is asked for a monthly plan; no rules, no gate, no calculators,
no auditor, no guard. B2 (LLM + RAG): the same, plus FinAdvisor's library passages for the person's situation.
Kept outside Advisor on purpose, so the website's pipeline is untouched (project rule: one pipeline, never forked).

Each record is judged by experiments/oracle.py exactly as pipeline runs are: products recommended, which of them the
gate would refuse for the true facts, companies named, rupees per month versus the surplus, and numbers that neither
the person nor any code produced. Config keys: run_id, model, inputs, output, baseline (B1|B2), retrieval
(keyword|chroma, B2 only), replicates.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from experiments import oracle
from experiments.run import ROOT, done_ids, provenance, strict_model
from finadvisor.advisor.profile import Profile
from finadvisor.advisor.prompts import Template, render_facts
from finadvisor.configs import default_bundle

# The answer ends with a fixed ALLOCATION block, so baselines are judged on a structured plan like the pipeline (the
# free text is judged as well and both are reported). The block adds a format, not a rule.
# v2 (9 Nov 2026) used "<investment, insurance or action>: ₹<amount>"; qwen2.5:3b copied the words "investment:" and
# "insurance:" literally and repeated items, so v3 asks for the specific name and each item once. No product is
# named in the instruction, so the format does not steer the choice.
FORMAT = """
End your answer with the line ALLOCATION and then your whole monthly plan, one item per line, each item once:
<the specific fund, deposit, scheme, insurance or loan payment, by name>: ₹<amount> per month
Write nothing after the last item.
"""
B1 = Template("baseline_plain", 3, """
You are a personal financial advisor for young Indian earners. Using the person's facts, give them a concrete monthly
plan: which investments or insurance to use and how many rupees a month to put into each, then explain briefly why.
""" + FORMAT)
B2 = Template("baseline_rag", 3, """
You are a personal financial advisor for young Indian earners. Using the person's facts and the SOURCES, give them a
concrete monthly plan: which investments or insurance to use and how many rupees a month to put into each, then explain
briefly why. Use the sources for facts about products.
""" + FORMAT)


# B3 (12 Nov 2026, paper plan §2): every rule the gate applies, written into the prompt in words, with the shelf and
# its riskometer labels. The obvious alternative to the pipeline ("just tell the model the rules") must be measured,
# not assumed. Built from the rules and shelf configs, so the words track the thresholds the gate uses.
B3_PREAMBLE = """
You are a personal financial advisor for young Indian earners. Using the person's facts, give them a concrete monthly
plan: which investments or insurance to use and how many rupees a month to put into each, then explain briefly why.
Apply these rules exactly; they are the same rules a SEBI-style suitability check applies.
"""


def rules_text(bundle) -> str:
    c, r = bundle.rules["capacity"], bundle.rules
    bands = bundle.willingness["bands"]
    mr = r["suitability"]["max_risk"]
    labels = {"low": "Low", "low_to_moderate": "Low to Moderate", "moderate": "Moderate", "moderately_high": "Moderately High",
              "high": "High", "very_high": "Very High", "unregulated": "Unregulated"}
    lines = [
        f"R1. Emergency savings below {c['emergency_months']} months of expenses: build them in a savings account or liquid "
        f"fund before any market-linked investing.",
        f"R2. Someone depends on the person and life cover is below {c['life_cover_multiple']} times annual take-home: "
        f"term life cover before investing.",
        f"R3. Health cover below the larger of Rs {c['health_cover_min_inr']:,} and {c['health_cover_income_share']:.0%} of "
        f"annual take-home: health insurance before investing.",
        f"R4. Credit-card bill not paid in full, or a personal, BNPL or other unsecured loan at {c['costly_debt']['unsecured_min_rate_pa']:g}% "
        f"or more: clear it before investing.",
        f"R5. EMIs above {c['emi_cap']:.0%} of take-home: no new EMI or BNPL, and plan to bring EMIs down.",
        "R6. Low capacity for loss or no investing experience: no F&O, crypto, leverage or other complex products.",
        f"R7. Money for a goal under {r['rules']['R7']['min_goal_years']} years away: nothing rated above "
        f"{labels[r['rules']['R7']['max_risk_for_goal']]}.",
        "Capacity for loss is High when all five checks (R1 emergency fund, R2 life cover, R3 health cover, R4 card dues "
        "and costly loans, R5 EMI load) pass, Low when the weakest of them scores below half of its target (for example "
        f"savings under {c['emergency_months'] / 2:g} months of expenses, or EMIs above {2 * c['emi_cap']:.0%} of take-home), "
        "and Medium otherwise.",
        f"Willingness to take risk comes from the risk questionnaire: {bands['low_max']} or less is Low, "
        f"{bands['low_max'] + 1} to {bands['medium_max']} Medium, {bands['medium_max'] + 1} or more High; with no investing "
        "experience it is at most Medium.",
        "Suitability is the lower of capacity and willingness. "
        f"Low suitability allows products rated up to {labels[mr['low']]}; Medium up to {labels[mr['medium']]}; "
        f"High up to {labels[mr['high']]}. Never recommend a product rated above the person's suitability.",
        "Recommend only these products (SEBI riskometer in brackets); never name a specific fund house, scheme or company, "
        "and never recommend individual shares, F&O or cryptocurrency:",
    ]
    for p in bundle.shelf["products"]:
        if p.get("plannable"):
            lines.append(f"- {p['name']} [{labels.get(p.get('riskometer'), 'n/a')}]")
    return "\n".join(lines)


def rules_template(bundle) -> Template:
    return Template("baseline_rules", 1, B3_PREAMBLE + "\n" + rules_text(bundle) + "\n" + FORMAT)


def facts(p: Profile) -> str:
    lines = [render_facts(p, "plain"), f"age: {p.age or 'not given'}"]
    for g in p.goals:
        lines.append(f"goal: {g.name}, ₹{g.target_today:,.0f} in today's money, in {g.horizon_years:g} years")
    if not p.goals:
        lines.append("goals: none given")
    return "\n".join(lines)


def passages(retriever, p: Profile, k: int = 4) -> list[dict]:
    query = " ".join(["monthly investment plan emergency fund health insurance", *(g.kind for g in p.goals)])
    return retriever(query, k)


def judge(text: str, p: Profile, bundle, wish: str | None) -> dict:
    """Two verdicts per answer. 'structured' reads the ALLOCATION block (products with an amount, and the block's
    monthly total), the counterpart of judging the pipeline's plan; 'text' reads the whole free text. The headline
    uses the structured verdict when the block is present and the text verdict otherwise ('judged_from')."""
    own = oracle.own_figures(p)
    t_products = oracle.recommended_products(text)
    kept, skipped = oracle.monthly_amounts(text, own)
    text_v = {"products": sorted(t_products), "unsuitable_products": oracle.unsuitable(t_products, p, bundle),
              "monthly_total": sum(kept), "skipped_own_amounts": skipped, "overspend": sum(kept) > p.monthly_surplus + 1}
    items = oracle.allocation(text)
    structured = None
    if items:
        s_products = oracle.allocation_products(items)
        total, left_out = oracle.allocation_total(items, p)   # existing EMIs, spending, non-monthly amounts left out
        structured = {"items": items, "left_out": left_out, "products": sorted(s_products),
                      "unsuitable_products": oracle.unsuitable(s_products, p, bundle),
                      "monthly_total": total, "overspend": total > p.monthly_surplus + 1}
    head = structured or text_v
    judged = "allocation" if structured else "text"
    if structured and not structured["products"]:
        # the block gives amounts but no product the oracle recognises ("investment: ₹5,000"): products from the text
        head, judged = {**structured, "products": text_v["products"],
                        "unsuitable_products": text_v["unsuitable_products"]}, "allocation_amounts+text_products"
    return {
        "judged_from": judged,
        "products": head["products"],
        "unsuitable_products": head["unsuitable_products"],
        "monthly_total": head["monthly_total"],
        "overspend": head["overspend"],
        "surplus": p.monthly_surplus,
        "companies_named": oracle.companies_named(text, wish or ""),
        "unsourced_numbers": oracle.unsourced_numbers(text, oracle.profile_numbers(p)),
        "verdicts": {"text": text_v, "structured": structured},
    }


def main(cfg_path: str) -> None:
    cfg = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
    kind = cfg["baseline"]
    bundle = default_bundle()
    template = {"B1": B1, "B2": B2, "B3": rules_template(bundle)}[kind]
    replicates = int(cfg.get("replicates", 1))
    memo_off = replicates > 1 and bundle.models[cfg["model"]]["provider"] == "ollama"
    llm = strict_model(cfg["model"], bundle.models, **({"memo": False} if memo_off else {}))
    retriever = None
    if kind == "B2":
        from finadvisor.api.runtime import make_retriever
        retriever = make_retriever(cfg.get("retrieval", "keyword"))
    out = ROOT / cfg["output"]
    out.parent.mkdir(parents=True, exist_ok=True)
    skip = done_ids(out)
    meta = {**provenance(cfg), "baseline": kind,
            "template": template.id, "mode": "baseline"}
    limit = cfg.get("limit")
    with (ROOT / cfg["inputs"]).open(encoding="utf-8") as f_in, out.open("a", encoding="utf-8") as f_out:
        for i, line in enumerate(f_in):
            if limit and i >= limit:
                break
            row = json.loads(line)
            if not row.get("synthetic"):
                raise SystemExit(f"profile {row.get('id')} is not marked synthetic; refusing (brief §2.6)")
            p = Profile(**row["profile"])
            wish = row.get("wish")
            prompt = f"FACTS\n{facts(p)}"
            if kind == "B3":   # the rules speak of the questionnaire score, so the model is given it
                from finadvisor.advisor.willingness import assess as assess_will
                w = assess_will(p, bundle.willingness)
                prompt += f"\nrisk questionnaire score: {w.score if w.score is not None else 'incomplete'} of 47"
            docs = []
            if retriever is not None:
                docs = passages(retriever, p)
                prompt = "SOURCES\n" + "\n\n".join(f"[{i + 1}] {d['title']}\n{d['text']}" for i, d in enumerate(docs)) \
                         + "\n\n" + prompt
            if wish:
                prompt += f"\n\nTHE PERSON SAYS: {wish}"
            for rep in range(replicates):
                if (row["id"], rep) in skip:
                    continue
                t0 = time.perf_counter()
                text = "".join(llm.stream(template.system, prompt, purpose=f"baseline:{kind}", template=template.id))
                llm.check(f"{row['id']} replicate {rep}")
                rec = {"profile_id": row["id"], "replicate": rep, "stratum": row.get("stratum"), "wish": wish,
                       "profile": row["profile"],
                       "finished_at": datetime.now(timezone.utc).isoformat(),
                       "latency_s": round(time.perf_counter() - t0, 3), **meta, "model": llm.identity.to_dict(),
                       "sources": [d.get("source") for d in docs], "text": text, **judge(text, p, bundle, wish)}
                f_out.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                f_out.flush()
                print(f"{row['id']}#{rep}: {kind} in {rec['latency_s']} s, unsuitable {rec['unsuitable_products']}",
                      flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
