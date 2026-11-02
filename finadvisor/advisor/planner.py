"""LLM planner: chooses product mixes per bucket from the gated shelf. Numbers come from plan.build_plan.

Prompts are kept compact because the website runs on a CPU-only box: the static instructions come first
(so the server can reuse its prompt cache across the auditor's twin calls) and the output is a small object
{bucket_id: "code:weight,code:weight"}.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from finadvisor.advisor.plan import BucketSpec
from finadvisor.advisor.profile import Profile
from finadvisor.advisor.prompts import PLANNER, render_facts
from finadvisor.llm.base import LLM, Generation

ITEM = re.compile(r"([A-Za-z_]+)\s*[:=]\s*(\d+(?:\.\d+)?)")
RISK_CODE = {"low": "L", "low_to_moderate": "LM", "moderate": "M", "moderately_high": "MH", "high": "H",
             "very_high": "VH", "unregulated": "U"}


@dataclass
class PlannerOutput:
    mixes: dict[str, list[tuple[str, float]]]
    generation: Generation | None
    problems: list[str] = field(default_factory=list)   # output the planner was not allowed to give


def code(p: dict) -> str:
    return p.get("code", p["id"])


def schema_for(specs: list[BucketSpec]) -> dict:
    """{bucket_id: "code:weight,code:weight"}: a terse string per bucket keeps output to a few tokens,
    which dominates latency on CPU. Codes are validated after parsing."""
    return {
        "type": "object",
        "properties": {s.id: {"type": "string"} for s in specs},
        "required": [s.id for s in specs],
    }


def build_prompt(profile: Profile, suit: str, specs: list[BucketSpec], style: str,
                 repair_hint: list[str] | None, wish: str | None,
                 anchors: dict[str, str] | None = None) -> str:
    lines = ["FACTS", render_facts(profile, style), f"SUITABILITY: {suit}", "BUCKETS"]
    for s in specs:
        horizon = f"{s.goal.horizon_years:g}y" if s.goal else "no date"
        allowed = ", ".join(f"{code(p)} ({RISK_CODE.get(p.get('riskometer'), '?')}, {p.get('role', '')})" for p in s.allowed)
        lines.append(f"- {s.id} ({s.name}; {horizon}): {allowed}")
        if anchors and anchors.get(s.id):
            lines.append(f"  starting point: {anchors[s.id]}")
    if wish:
        lines.append(f"THE PERSON SAYS: {wish}")
    if repair_hint:
        lines.append("YOUR PREVIOUS CHOICES BROKE THESE CHECKS; FIX THEM:")
        lines += [f"- {h}" for h in repair_hint]
    return "\n".join(lines)


def choose_mixes(llm: LLM, profile: Profile, suit: str, specs: list[BucketSpec], *, style: str = "plain",
                 repair_hint: list[str] | None = None, wish: str | None = None,
                 codes: dict[str, str] | None = None, anchors: dict[str, str] | None = None) -> PlannerOutput:
    usable = [s for s in specs if s.allowed]
    if not usable:
        return PlannerOutput({}, None)
    prompt = build_prompt(profile, suit, usable, style, repair_hint, wish, anchors)
    raw, gen = llm.json(PLANNER.system, prompt, schema_for(usable), purpose=f"planner:{style}", template=PLANNER.id)
    mixes: dict[str, list[tuple[str, float]]] = {}
    problems: list[str] = []
    allowed = {s.id: {p["id"] for p in s.allowed} for s in usable}
    by_code = codes or {code(p): p["id"] for s in usable for p in s.allowed}
    if not isinstance(raw, dict) or "_unparseable" in raw:
        return PlannerOutput({}, gen, ["planner output was not valid JSON"])
    for bid, mix in raw.items():
        if bid not in allowed:
            problems.append(f"unknown bucket {bid!r}")
            continue
        for c, w in ITEM.findall(str(mix)) if isinstance(mix, str) else []:
            pid = by_code.get(c.lower(), c)
            parts = max(0.0, min(10.0, float(w)))
            if parts <= 0:
                continue
            if pid not in allowed[bid]:
                problems.append(f"{pid} is not allowed in bucket {bid}")
            mixes.setdefault(bid, []).append((pid, parts))
    for s in usable:
        if s.id not in mixes:
            problems.append(f"no mix for bucket {s.id}")
    return PlannerOutput(mixes, gen, problems)
