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
from experiments.run import ROOT, done_ids, provenance
from finadvisor.advisor.profile import Profile
from finadvisor.advisor.prompts import Template, render_facts
from finadvisor.configs import default_bundle
from finadvisor.llm import get_llm

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
        own_block = oracle.own_figures(p, surplus=False)   # "Car loan EMI: ₹28,000" is not a new outflow
        total = sum(v for _, v in items if round(v) not in own_block)
        structured = {"items": items, "products": sorted(s_products),
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
    template = {"B1": B1, "B2": B2}[kind]
    bundle = default_bundle()
    replicates = int(cfg.get("replicates", 1))
    memo_off = replicates > 1 and bundle.models[cfg["model"]]["provider"] == "ollama"
    llm = get_llm(cfg["model"], bundle.models, **({"memo": False} if memo_off else {}))
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
