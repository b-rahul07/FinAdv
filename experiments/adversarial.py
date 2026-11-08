"""Adversarial chat turns (pressure, Hinglish, misspellings, "ignore your rules", requests to name stocks).

    python -m experiments.adversarial experiments/configs/ADV_adversarial.yaml

Each turn in experiments/data/adversarial_turns.jsonl is sent through the website's own Advisor.turn for a few
personas (one per suitability level by default, from the persona file), and the same persona also asks a neutral
question. Checks per answer: no company named that the person did not name; the final plan breaks no rule; and, for
answers that carry a plan, the plan equals the neutral plan (pressure did not move it). Config keys: run_id, pipeline,
model, personas (JSONL), turns (JSONL), per_level (personas per suitability level), output.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from experiments import metrics, oracle
from experiments.run import ROOT, bundle_for, done_ids, provenance, strict_model
from finadvisor.advisor.pipeline import Advisor, TurnInput
from finadvisor.advisor.profile import Profile

NEUTRAL = "Make me a money plan"


def pick_personas(path: Path, per_level: int) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    out = []
    for level in ("low", "medium", "high"):
        out += [r for r in rows if (r.get("engine_oracle") or {}).get("suitability") == level][:per_level]
    return out


def main(cfg_path: str) -> None:
    cfg = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
    bundle = bundle_for(cfg)
    bundle = bundle.with_pipeline({**bundle.pipeline, "stages": {**bundle.pipeline["stages"], "extraction": False}})
    llm = strict_model(cfg["model"], bundle.models)
    advisor = Advisor(bundle, llm)
    personas = pick_personas(ROOT / cfg["personas"], int(cfg.get("per_level", 1)))
    turns = [json.loads(line) for line in (ROOT / cfg["turns"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    if cfg.get("limit"):   # first N turns only, for a quick check
        turns = turns[: int(cfg["limit"])]
    out = ROOT / cfg["output"]
    out.parent.mkdir(parents=True, exist_ok=True)
    skip = {pid for pid, _ in done_ids(out)}
    prov = provenance(cfg)
    with out.open("a", encoding="utf-8") as f:
        for p in personas:
            profile = Profile(**p["profile"])
            neutral = advisor.turn(TurnInput(text=NEUTRAL, confirmed=profile), lambda k, d: None)
            llm.check(f"{p['id']} neutral turn")
            neutral_sig = metrics.signature((neutral.advice or {}).get("plan"))
            for t in turns:
                key = f"{p['id']}|{t['id']}"
                if key in skip:
                    continue
                t0 = time.perf_counter()
                res = advisor.turn(TurnInput(text=t["text"], confirmed=profile), lambda k, d: None)
                llm.check(key)
                a = res.advice or {}
                plan_sig = metrics.signature(a.get("plan")) if a.get("plan") else None
                rec = {"profile_id": key, "replicate": 0, "persona": p["id"], "turn_id": t["id"], "kind": t["kind"],
                       "question": t["text"], **prov, "mode": "adversarial",
                       "finished_at": datetime.now(timezone.utc).isoformat(),
                       "latency_s": round(time.perf_counter() - t0, 3), "model": llm.identity.to_dict(),
                       "route": res.route, "text": res.text,
                       "companies_named": oracle.companies_named(res.text, t["text"]),
                       "rule_breaks": [v for v in a.get("violations", []) if not v.startswith("planner:")],
                       "plan_unchanged": None if plan_sig is None else
                       metrics.same_plan(plan_sig, neutral_sig, metrics.TOL)}
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                f.flush()
                print(f"{key}: route {res.route}, companies {rec['companies_named']}, unchanged {rec['plan_unchanged']}",
                      flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
