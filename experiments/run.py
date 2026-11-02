"""Headless experiment runner: the same advisor pipeline the website uses (report §7.1).

    python -m experiments.run experiments/configs/smoke.yaml

A run config names the pipeline config (stage flags = ablations), the model, the input profiles (JSONL) and
the output file. Results are appended one JSON line per profile as they finish; re-running skips profiles
already in the output, so Colab/Kaggle sessions can be resumed.

Privacy: real users' data never comes here. Third-party models (self_hosted: false) are allowed only because
inputs are synthetic benchmark profiles (brief §2.6); the runner refuses inputs not marked synthetic.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from finadvisor.advisor.pipeline import Advisor
from finadvisor.advisor.profile import Profile
from finadvisor.advisor.prompts import ALL as TEMPLATES
from finadvisor.configs import CONFIG_DIR, fingerprint, load_bundle
from finadvisor.llm import get_llm

ROOT = Path(__file__).resolve().parent.parent


def done_ids(out: Path) -> set[tuple[str, int]]:
    if not out.exists():
        return set()
    ids = set()
    with out.open(encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                ids.add((r["profile_id"], r.get("replicate", 0)))
            except (json.JSONDecodeError, KeyError):
                continue  # a torn last line from an interrupted session is re-run
    return ids


def main(cfg_path: str) -> None:
    cfg = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
    bundle = load_bundle(CONFIG_DIR / cfg["pipeline"])
    if "stages" in cfg:  # inline ablation flags override the pipeline file
        bundle = bundle.with_pipeline({**bundle.pipeline, "stages": {**bundle.pipeline["stages"], **cfg["stages"]}})
    if "planner" in cfg:  # e.g. {mode: model}: the language model chooses the mix (the website uses the standard mix)
        bundle = bundle.with_pipeline({**bundle.pipeline, "planner": {**bundle.pipeline.get("planner", {}), **cfg["planner"]}})
    if "auditor" in cfg:
        bundle = bundle.with_pipeline({**bundle.pipeline, "auditor": {**bundle.pipeline["auditor"], **cfg["auditor"]}})
    replicates = int(cfg.get("replicates", 1))
    # With replicates > 1 the in-process memo is off, so every repeat really calls the model and the spread of
    # outputs at temperature 0 (CPU kernels are not bit-reproducible) can be reported.
    memo_off = replicates > 1 and bundle.models[cfg["model"]]["provider"] == "ollama"
    llm = get_llm(cfg["model"], bundle.models, **({"memo": False} if memo_off else {}))
    advisor = Advisor(bundle, llm)  # not real_users: inputs must be synthetic (checked below)

    inputs = ROOT / cfg["inputs"]
    out = ROOT / cfg["output"]
    out.parent.mkdir(parents=True, exist_ok=True)
    skip = done_ids(out)
    run_meta = {
        "run_id": cfg["run_id"],
        "run_config": cfg,
        "run_config_hash": fingerprint(cfg),
        "versions": bundle.versions,
        "flags": bundle.pipeline["stages"],
        "auditor": bundle.pipeline["auditor"],
        "templates": {t.name: t.id for t in TEMPLATES},
    }
    n_new = 0
    with inputs.open(encoding="utf-8") as f_in, out.open("a", encoding="utf-8") as f_out:
        for line in f_in:
            row = json.loads(line)
            if not row.get("synthetic"):
                raise SystemExit(f"profile {row.get('id')} is not marked synthetic; refusing (brief §2.6)")
            profile = Profile(**row["profile"])
            for rep in range(replicates):
                if (row["id"], rep) in skip:
                    continue
                t0 = time.perf_counter()
                core, audit = advisor.run_plan(profile, wish=row.get("wish"))
                rec = {
                    "profile_id": row["id"],
                    "replicate": rep,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "latency_s": round(time.perf_counter() - t0, 3),
                    **run_meta,
                    "model": llm.identity.to_dict(),
                    "capacity": core.capacity.to_dict() if core.capacity else None,
                    "willingness": core.willingness.to_dict() if core.willingness else None,
                    "suitability": core.suitability,
                    "first_plan": core.plan.to_dict(),
                    "first_violations": core.violations,
                    "final_plan": audit.final.plan.to_dict(),
                    "final_violations": audit.final.violations,
                    "audit": audit.to_dict(),
                    "generations": [g.to_dict() for g in audit.generations],
                }
                f_out.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                f_out.flush()
                n_new += 1
                print(f"{row['id']}#{rep}: {audit.status} in {rec['latency_s']} s", flush=True)
    print(f"done: {n_new} new, {len(skip)} already present -> {out}")


if __name__ == "__main__":
    main(sys.argv[1])
