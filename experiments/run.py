"""Headless experiment runner: the same advisor pipeline the website uses (report §7.1).

    python -m experiments.run experiments/configs/smoke.yaml

A run config names the pipeline config (stage flags = ablations), the model, the input profiles (JSONL) and
the output file. Results are appended one JSON line per profile as they finish; re-running skips profiles
already in the output, so Colab/Kaggle sessions can be resumed.

Modes:
  plan (default): plan + audit only (Advisor.run_plan), the fastest way to measure suitability and the auditor.
  turn: the full Plan reply the website gives (Advisor.turn: plan, audit, answer, explanation), so explanations and
        the number guard can be measured. Profiles with a "wish" are also run with a neutral question, and both plans
        are kept, to measure pressure resistance.

Config keys besides stage flags: planner, auditor, explainer (merged into the pipeline config), rules (another
rules version, for sensitivity runs), replicates.

Privacy: real users' data never comes here. Third-party models (self_hosted: false) are allowed only because
inputs are synthetic benchmark profiles (brief §2.6); the runner refuses inputs not marked synthetic.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from finadvisor.advisor.core import RULE_CHECK_VERSION
from finadvisor.advisor.pipeline import Advisor, TurnInput
from finadvisor.advisor.profile import Profile
from finadvisor.advisor.prompts import ALL as TEMPLATES
from finadvisor.configs import CONFIG_DIR, fingerprint, load_bundle, load_component
from finadvisor.llm import get_llm

ROOT = Path(__file__).resolve().parent.parent
NEUTRAL = "Make me a money plan"


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10,
                              check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def provenance(cfg: dict) -> dict:
    """What every result row carries so a number in the paper traces back to the exact code and config: the git
    commit, whether the working tree had uncommitted changes (such a run is not traceable and the report says so),
    the run config and its hash, and the version of the rule check."""
    status = _git("status", "--porcelain", "--untracked-files=no")
    return {"run_id": cfg["run_id"], "run_config": cfg, "run_config_hash": fingerprint(cfg),
            "git_commit": _git("rev-parse", "HEAD"), "git_dirty": None if status is None else bool(status),
            "rule_check": RULE_CHECK_VERSION}


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


def bundle_for(cfg: dict):
    bundle = load_bundle(CONFIG_DIR / cfg["pipeline"])
    p = bundle.pipeline
    if "stages" in cfg:  # inline ablation flags override the pipeline file
        p = {**p, "stages": {**p["stages"], **cfg["stages"]}}
    for key in ("planner", "auditor", "explainer"):  # e.g. planner: {mode: model}
        if key in cfg:
            p = {**p, key: {**p.get(key, {}), **cfg[key]}}
    bundle = bundle.with_pipeline(p)
    if "rules" in cfg:  # sensitivity runs: another rules version (a new file; reported versions are never edited)
        from dataclasses import replace
        bundle = replace(bundle, rules=load_component("rules", cfg["rules"]))
    return bundle


def plan_record(advisor: Advisor, profile: Profile, wish: str | None) -> dict:
    core, audit = advisor.run_plan(profile, wish=wish)
    return {
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


def turn_record(advisor: Advisor, profile: Profile, text: str) -> dict:
    out = advisor.turn(TurnInput(text=text, confirmed=profile, profile_version=1, forced_route="plan"),
                       lambda kind, data: None)
    a = out.advice or {}
    attempts = (a.get("audit") or {}).get("attempts") or []
    return {
        "question": text,
        "capacity": a.get("capacity"),
        "willingness": a.get("willingness"),
        "suitability": a.get("suitability"),
        "first_plan": attempts[0]["plan"] if attempts else a.get("plan"),
        "first_violations": attempts[0]["violations"] if attempts else a.get("violations", []),
        "final_plan": a.get("plan"),
        "final_violations": a.get("violations", []),
        "audit": a.get("audit"),
        "intent": (a.get("compose") or {}).get("intent"),
        "text": out.text,
        "generations": [g.to_dict() for g in out.generations],
    }


def main(cfg_path: str) -> None:
    cfg = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
    bundle = bundle_for(cfg)
    mode = cfg.get("mode", "plan")
    if mode == "turn":
        # Benchmark profiles are already confirmed; reading facts from the question could swap the plan for a
        # "please confirm" card, so extraction is off for turn runs (recorded in flags).
        bundle = bundle.with_pipeline({**bundle.pipeline, "stages": {**bundle.pipeline["stages"], "extraction": False}})
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
    prov = provenance(cfg)
    if prov["git_dirty"]:
        print("warning: uncommitted changes; results will be marked git_dirty and are not traceable to a commit",
              file=sys.stderr)
    run_meta = {
        **prov,
        "versions": bundle.versions,
        "rules_version": bundle.rules["version"],
        "flags": bundle.pipeline["stages"],
        "planner_mode": bundle.pipeline.get("planner", {}).get("mode", "model"),
        "auditor": bundle.pipeline["auditor"],
        "templates": {t.name: t.id for t in TEMPLATES},
        "mode": mode,
    }
    n_new = 0
    limit = cfg.get("limit")   # first N personas only, for a quick check before a full run
    with inputs.open(encoding="utf-8") as f_in, out.open("a", encoding="utf-8") as f_out:
        for i, line in enumerate(f_in):
            if limit and i >= limit:
                break
            row = json.loads(line)
            if not row.get("synthetic"):
                raise SystemExit(f"profile {row.get('id')} is not marked synthetic; refusing (brief §2.6)")
            profile = Profile(**row["profile"])
            wish = row.get("wish")
            for rep in range(replicates):
                if (row["id"], rep) in skip:
                    continue
                t0 = time.perf_counter()
                if mode == "turn":
                    body = turn_record(advisor, profile, wish or NEUTRAL)
                    if wish:   # pressure resistance: the same person asking neutrally
                        body["neutral"] = {k: v for k, v in turn_record(advisor, profile, NEUTRAL).items()
                                           if k in ("final_plan", "final_violations", "text")}
                else:
                    body = plan_record(advisor, profile, wish)
                    if wish:
                        neutral = plan_record(advisor, profile, None)
                        body["neutral"] = {k: neutral[k] for k in ("final_plan", "final_violations")}
                rec = {
                    "profile_id": row["id"],
                    "replicate": rep,
                    "stratum": row.get("stratum"),
                    "wish": wish,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "latency_s": round(time.perf_counter() - t0, 3),
                    **run_meta,
                    "model": llm.identity.to_dict(),
                    **body,
                }
                f_out.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                f_out.flush()
                n_new += 1
                status = (rec.get("audit") or {}).get("status")
                print(f"{row['id']}#{rep}: {status} in {rec['latency_s']} s", flush=True)
    print(f"done: {n_new} new, {len(skip)} already present -> {out}")


if __name__ == "__main__":
    main(sys.argv[1])
