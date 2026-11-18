"""Fact extraction accuracy: the model's real job on the website (review of the paper, 17 Nov 2026).

Each persona's true facts are written in four wordings and given to the extraction step as a chat message:
  plain, casual, table  the three wordings MR6 uses (finadvisor.advisor.prompts.render_facts)
  chat                  a first-person message, as a person would type it
For every field the record keeps the truth, the model's raw answer (what the model read) and the value the system
would put on the confirmation card after grounding (finadvisor.advisor.extract: a value is kept only when the
message states it). Run through experiments.run with `mode: extract` (one model call per wording).

Fields: take-home, expenses, emergency savings, total EMIs, dependants, life cover, health cover, card paid in full,
investing experience. Numbers count as correct within 1%.
"""

from __future__ import annotations

from finadvisor.advisor.extract import EXTRACT, SCHEMA, extract
from finadvisor.advisor.profile import Profile
from finadvisor.advisor.prompts import render_facts
from finadvisor.calc.money import inr
from finadvisor.llm.fake import FakeLLM

WORDINGS = ("plain", "casual", "table", "chat")
NUMERIC = ("take_home_monthly", "expenses_monthly", "liquid_savings", "emi_total", "dependants", "life_cover",
           "health_cover")
FIELDS = NUMERIC + ("card_dues_paid_in_full", "experience")


def chat_message(p: Profile) -> str:
    card = "I pay my credit card bill in full every month" if p.card_dues_paid_in_full else \
        "I don't pay my credit card bill in full"
    deps = "nobody depends on me" if p.dependants == 0 else (
        "1 person depends on me" if p.dependants == 1 else f"{p.dependants} people depend on me")
    exp = {"none": "I have never invested", "beginner": "I'm a beginner at investing",
           "intermediate": "I'm an intermediate investor", "advanced": "I'm an advanced investor"}[p.experience]
    return (f"I earn {inr(p.take_home_monthly)} a month take-home and spend about {inr(p.expenses_monthly)}. "
            f"I have {inr(p.liquid_savings)} in savings and pay {inr(p.total_emi)} a month in EMIs. {deps.capitalize()}. "
            f"My life cover is {inr(p.life_cover)} and my health cover is {inr(p.health_cover)}. {card}. {exp}.")


def message(p: Profile, wording: str) -> str:
    return chat_message(p) if wording == "chat" else render_facts(p, wording)


def truth(p: Profile) -> dict:
    return {"take_home_monthly": p.take_home_monthly, "expenses_monthly": p.expenses_monthly,
            "liquid_savings": p.liquid_savings, "emi_total": p.total_emi, "dependants": p.dependants,
            "life_cover": p.life_cover, "health_cover": p.health_cover,
            "card_dues_paid_in_full": p.card_dues_paid_in_full, "experience": p.experience}


def _values(d: dict | None) -> dict:
    d = d if isinstance(d, dict) else {}
    out = {k: d.get(k) for k in FIELDS if k != "emi_total"}
    # Scoring v2 (18 Nov 2026): EMIs exist only as a list of loans in the schema, so "no loans returned" is the
    # schema's way of saying no EMIs and reads as 0 (v1 counted it as unread, which marked a correct reading of
    # "EMIs ₹0/month" wrong). It is still wrong whenever the message states EMIs.
    debts = d.get("debts") if isinstance(d.get("debts"), list) else []
    out["emi_total"] = sum(float(x.get("emi_monthly") or 0) for x in debts if isinstance(x, dict))
    return out


def correct(field: str, got, want) -> bool:
    if got is None:
        return False
    if field in NUMERIC:
        try:
            g, w = float(got), float(want)
        except (TypeError, ValueError):
            return False
        return abs(g - w) <= max(1.0, 0.01 * abs(w))
    if field == "card_dues_paid_in_full":
        return bool(got) is bool(want) and isinstance(got, bool)
    return str(got).strip().lower() == str(want).lower()


SCORING = "extract-score-v2"   # v2: no loans returned reads as 0 EMIs (see _values)


def score(text: str, raw, want: dict) -> dict:
    """Score one raw model answer: what the model read, and what the confirmation card would show after the
    system's grounding (the raw answer replayed through extract(), no model call)."""
    replay = FakeLLM(lambda *a, _raw=raw, **k: _raw)
    accepted, changed, _ = extract(replay, text, Profile())
    raw_v, all_v, empty = _values(raw), _values(accepted), _values(Profile().model_dump())
    acc_v = {}
    for f in FIELDS:
        kept = ("debts" if f == "emi_total" else f) in changed
        if kept:
            acc_v[f] = all_v[f]
        elif raw_v[f] is not None and correct(f, raw_v[f], empty[f]):
            acc_v[f] = empty[f]       # the model said the empty profile's value, so nothing needed to change
        else:
            acc_v[f] = None           # dropped by grounding, or never read
    return {"raw": raw_v, "accepted": acc_v,
            "raw_correct": {f: correct(f, raw_v[f], want[f]) for f in FIELDS},
            "accepted_correct": {f: correct(f, acc_v[f], want[f]) for f in FIELDS}}


def extract_record(llm, profile: Profile) -> dict:
    want = truth(profile)
    out = {"truth": want, "scoring": SCORING, "wordings": {}}
    for w in WORDINGS:
        text = message(profile, w)
        raw, gen = llm.json(EXTRACT.system, f"MESSAGE: {text}", SCHEMA, purpose="extract", template=EXTRACT.id)
        out["wordings"][w] = {"message": text, "raw_json": raw, **score(text, raw, want),
                              "latency_s": getattr(gen, "latency_s", None)}
    return out


def rescore(rec: dict) -> dict:
    """A stored record scored again with the current scoring, from its stored message and raw answer."""
    want = truth(Profile(**rec["profile"]))
    out = dict(rec)
    out["scoring"] = SCORING
    out["wordings"] = {w: {**v, **score(v["message"], v["raw_json"], want)} for w, v in rec["wordings"].items()}
    return out
