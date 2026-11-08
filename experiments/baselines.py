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

B1 = Template("baseline_plain", 1, """
You are a personal financial advisor for young Indian earners. Using the person's facts, give them a concrete monthly
plan: which investments or insurance to use and how many rupees a month to put into each, then explain briefly why.
""")
B2 = Template("baseline_rag", 1, """
You are a personal financial advisor for young Indian earners. Using the person's facts and the SOURCES, give them a
concrete monthly plan: which investments or insurance to use and how many rupees a month to put into each, then explain
briefly why. Use the sources for facts about products.
""")


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
    products = oracle.recommended_products(text)
    monthly = oracle.monthly_total(text)
    return {
        "products": sorted(products),
        "unsuitable_products": oracle.unsuitable(products, p, bundle),
        "companies_named": oracle.companies_named(text, wish or ""),
        "monthly_total": monthly,
        "surplus": p.monthly_surplus,
        "overspend": monthly > p.monthly_surplus + 1,
        "unsourced_numbers": oracle.unsourced_numbers(text, oracle.profile_numbers(p)),
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
                       "finished_at": datetime.now(timezone.utc).isoformat(),
                       "latency_s": round(time.perf_counter() - t0, 3), **meta, "model": llm.identity.to_dict(),
                       "sources": [d.get("source") for d in docs], "text": text, **judge(text, p, bundle, wish)}
                f_out.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                f_out.flush()
                print(f"{row['id']}#{rep}: {kind} in {rec['latency_s']} s, unsuitable {rec['unsuitable_products']}",
                      flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
