"""Profile extraction (LLM). Output is only ever a proposal shown on the profile card for confirmation."""

from __future__ import annotations

import re

from pydantic import ValidationError

from finadvisor.advisor.profile import Debt, Goal, Profile
from finadvisor.advisor.prompts import EXTRACT
from finadvisor.llm.base import LLM, Generation

# The model is called only when the message can state a fact that grounding would accept: an amount (numeric fields
# must quote their value), or a non-numeric fact (dependants, investing experience, card dues). Questions such as
# "Do I have enough emergency savings?" used to trigger a 5-20 s model call for nothing.
FACT_HINT = re.compile(
    r"\d|\b(lakhs?|lacs?|crores?|thousand|hundred|hazaa?r|hajar|lpa|dedh|dhaa?i)\b|\b(one|two|three|four|five)\b.*\b(kids?|children|depend\w*)\b"
    r"|\b(married|wife|husband|spouse|my (kids?|children|son|daughter|parents|mother|father)|depend\w* on me)\b"
    r"|\b(never invested|first[- ]time investor|new to investing|no (investing )?experience|i'?ve been investing"
    r"|i invest(ed)? (in|for)|years of investing)\b|\b(card (bill|dues)|credit[- ]card)\b", re.I)

SCHEMA = {
    "type": "object",
    "properties": {
        "age": {"type": "integer"},
        "take_home_monthly": {"type": "number"},
        "expenses_monthly": {"type": "number"},
        "liquid_savings": {"type": "number"},
        "dependants": {"type": "integer"},
        "life_cover": {"type": "number"},
        "health_cover": {"type": "number"},
        "card_dues_paid_in_full": {"type": "boolean"},
        "experience": {"type": "string", "enum": ["none", "beginner", "intermediate", "advanced"]},
        "debts": {"type": "array", "items": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["home", "car", "personal", "education", "bnpl", "credit_card", "gold",
                                                "two_wheeler", "other"]},
            "outstanding": {"type": "number"}, "rate_pa": {"type": "number"}, "emi_monthly": {"type": "number"}},
            "required": ["kind"]}},
        "goals": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"},
            "kind": {"type": "string", "enum": ["retirement", "home", "education", "marriage", "vehicle", "travel",
                                                "wealth", "other"]},
            "target_today": {"type": "number"}, "horizon_years": {"type": "number"}},
            "required": ["name"]}},
    },
}

SCALARS = ("age", "take_home_monthly", "expenses_monthly", "liquid_savings", "dependants", "life_cover",
           "health_cover", "card_dues_paid_in_full", "experience")

# Grounding: a field is accepted only when the message talks about it (and, for numbers, contains the value).
# The 3B model otherwise invents facts, e.g. "age 25, expenses 6000" from "should I buy a phone on EMI of 6000".
FIELD_HINT = {
    "age": re.compile(r"\b(age|aged|years? old|yo|i'?m \d+|i am \d+)\b", re.I),
    "take_home_monthly": re.compile(r"earn|salary|income|take[- ]home|in[- ]hand|paid|make \d|ctc|kamata|kamati|"
                                    r"milta|milti|tankhwa?h", re.I),
    "expenses_monthly": re.compile(r"spend|expense|expenditure|outgo|cost of living|household|rent|kharch", re.I),
    "liquid_savings": re.compile(r"sav(ed|ings?)|emergency|in the bank|bank balance|liquid|fd\b|fixed deposit", re.I),
    "dependants": re.compile(r"depend|kids?|child|children|son|daughter|parents|mother|father|wife|husband|spouse", re.I),
    "life_cover": re.compile(r"term (plan|cover|insurance)|life (cover|insurance)|lic\b", re.I),
    "health_cover": re.compile(r"health|medical|mediclaim|hospital", re.I),
    "card_dues_paid_in_full": re.compile(r"credit[- ]card|card (bill|dues|balance)", re.I),
    "experience": re.compile(r"invest(ed|ing|or)|experience|trad(e|ed|ing)|never|first time|beginner|new to|stocks?|"
                             r"mutual funds?|sip", re.I),
}
DEBT_HINT = re.compile(r"\b(loan|emi|bnpl|owe|borrow|credit[- ]card|mortgage|debt)", re.I)
NUMERIC = {"age", "take_home_monthly", "expenses_monthly", "liquid_savings", "dependants", "life_cover", "health_cover"}
COUNT_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "a": 1, "an": 1}


# Indian money phrases (14 Nov 2026): "12 LPA" (lakh per annum), "40 hazaar", "do lakh", "dedh lakh", "saade teen
# lakh". A value found here can ground a field the model proposes; nothing is filled from it directly. "12 LPA" is a
# yearly salary before tax, so it is 12,00,000 and never a monthly take-home: a model that turns it into 1,00,000 a
# month is not grounded, and the card asks for take-home instead.
_HI_NUM = {"ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "chhah": 6,
           "saat": 7, "aath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12, "pandrah": 15, "bees": 20,
           "pachees": 25, "tees": 30, "chalis": 40, "chaalis": 40, "pachas": 50, "pachaas": 50, "sau": 100}
_HI_FRACTION = {"dedh": 1.5, "derh": 1.5, "dhai": 2.5, "dhaai": 2.5, "adhai": 2.5}
_HI_PREFIX = {"saade": 0.5, "sade": 0.5, "sawa": 0.25, "paune": -0.25}
_SCALE = {"lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7,
          "hazaar": 1e3, "hazar": 1e3, "hajar": 1e3, "thousand": 1e3}
_SCALE_RE = "|".join(sorted(_SCALE, key=len, reverse=True))
LPA = re.compile(r"(\d+(?:\.\d+)?)\s*(?:lpa|l\.p\.a\.?|lakhs?\s+(?:per\s+annum|p\.?a\.?|a\s+year|per\s+year|yearly))\b",
                 re.I)
DIGIT_SCALE = re.compile(rf"(\d+(?:\.\d+)?)\s*({_SCALE_RE})\b", re.I)
HI_WORDS = re.compile(rf"\b(?:({'|'.join(_HI_PREFIX)})\s+)?({'|'.join([*_HI_FRACTION, *_HI_NUM])})\s+({_SCALE_RE})\b",
                      re.I)


def money_phrases(text: str) -> set[float]:
    """Rupee values written the Indian way, which the number guard's reader does not cover."""
    out: set[float] = set()
    for m in LPA.finditer(text):
        out.add(round(float(m.group(1)) * 1e5, 2))
    for m in DIGIT_SCALE.finditer(text):
        out.add(round(float(m.group(1)) * _SCALE[m.group(2).lower()], 2))
    for m in HI_WORDS.finditer(text):
        word = m.group(2).lower()
        base = _HI_FRACTION.get(word, _HI_NUM.get(word))
        if m.group(1):
            if word in _HI_FRACTION:
                continue   # "saade dedh" is not a number
            base += _HI_PREFIX[m.group(1).lower()]
        out.add(round(base * _SCALE[m.group(3).lower()], 2))
    return out


def _numbers(text: str) -> set[float]:
    from finadvisor.advisor.numbers import collect
    out = collect(text)
    out |= {float(v) for w, v in COUNT_WORDS.items() if re.search(rf"\b{w}\b", text, re.I)}
    out |= money_phrases(text)
    return out


# Experience is a fact only when the message states it. "What stocks should I invest in?" mentions investing but
# says nothing about experience; the 3B model still proposed "intermediate" for it, and the reply became a profile
# card instead of an answer (advice evaluation, 14 Nov 2026).
EXPERIENCE_STATED = re.compile(
    r"\b(i'?ve been (investing|trading)|i have been (investing|trading)|i (invest|trade)(ed)? (in|for|since|regularly)"
    r"|years? of (investing|trading)|been investing|beginner|experienced (investor|trader)|new to (investing|stocks|"
    r"mutual funds|the (stock )?market)|never (invested|traded|bought)|first[- ]time investor|no (investing )?experience"
    r"|i'?m (an? )?(expert|pro|advanced|intermediate|novice)|i am (an? )?(expert|pro|advanced|intermediate|novice)"
    r"|haven'?t (ever )?invested)\b", re.I)
ASKING_TO_INVEST = re.compile(r"\b(should|can|could|do|shall|where|what|which|how)\b[^.?!]{0,30}\bi (invest|trade)\b",
                              re.I)


def experience_stated(text: str) -> bool:
    return bool(EXPERIENCE_STATED.search(text)) and not (ASKING_TO_INVEST.search(text)
                                                          and not NO_EXPERIENCE.search(text))


NO_EXPERIENCE = re.compile(r"never (invested|traded|bought)|first[- ]time investor|new to investing|no (investing )?experience"
                           r"|haven'?t (ever )?invested", re.I)
NOT_A_GOAL = re.compile(r"insurance|cover|term plan|mediclaim|policy|loan|emi|independence", re.I)


def grounded(field: str, value, text: str, nums: set[float]) -> bool:
    if not FIELD_HINT[field].search(text):
        return False
    if field == "experience":
        return experience_stated(text)
    if field == "dependants":   # "my wife and two kids" -> 3 is a count the message implies, not states
        return isinstance(value, (int, float)) and 0 <= value <= 10
    if field in NUMERIC:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return False
        return round(v, 2) in nums or round(v) in nums or (field == "dependants" and v == 0)
    return True


def worth_extracting(text: str) -> bool:
    return bool(FACT_HINT.search(text))


def extract(llm: LLM, text: str, current: Profile | None, *, exclude_purchase: bool = False) -> tuple[dict, list[str], Generation | None]:
    """Return (proposed profile dict, changed field names, generation). Nothing is applied here."""
    base = (current or Profile()).model_dump()
    if not worth_extracting(text):
        return base, [], None
    prompt = f"MESSAGE: {text}"
    if exclude_purchase:
        prompt += "\nDo not include any new purchase, loan or EMI the user is ASKING about; only facts they already have."
    raw, gen = llm.json(EXTRACT.system, prompt, SCHEMA, purpose="extract", template=EXTRACT.id)
    if not isinstance(raw, dict):
        return base, [], gen
    proposed = dict(base)
    changed: list[str] = []
    nums = _numbers(text)
    asked_emi = None
    if exclude_purchase:
        from finadvisor.advisor.check import parse_new_emi
        asked_emi = parse_new_emi(text)
    if NO_EXPERIENCE.search(text):
        raw["experience"] = "none"     # the model sometimes answers "intermediate" to "I've never invested"
    for k in SCALARS:
        if k in raw and raw[k] is not None and raw[k] != base.get(k) and grounded(k, raw[k], text, nums):
            proposed[k] = raw[k]
            changed.append(k)
    existing_goals = {g["name"].strip().lower() for g in base["goals"]}
    used_ids = {g["id"] for g in base["goals"]}
    for g in raw.get("goals") or []:
        if not g.get("name") or g["name"].strip().lower() in existing_goals or NOT_A_GOAL.search(g["name"]):
            continue
        if not g.get("target_today") or not g.get("horizon_years"):
            continue  # incomplete goals are asked for on the card instead of guessed
        if not (round(float(g["target_today"])) in nums or round(float(g["target_today"]), 2) in nums):
            continue  # the target must be stated in the message
        # the first free gN: a profile whose g2 was removed on the card still has g3, so counting goals could collide
        gid = next(f"g{n}" for n in range(1, len(used_ids) + 2) if f"g{n}" not in used_ids)
        try:
            goal = Goal(id=gid, name=g["name"], kind=g.get("kind", "other"),
                        target_today=g["target_today"], horizon_years=g["horizon_years"])
        except ValidationError:
            continue
        used_ids.add(gid)
        existing_goals.add(g["name"].strip().lower())
        proposed["goals"] = [*proposed["goals"], goal.model_dump()]
        changed.append("goals")
    for d in raw.get("debts") or []:
        try:
            debt = Debt(**{k: v for k, v in d.items() if v is not None})
        except ValidationError:
            continue
        if debt.outstanding == 0 and debt.emi_monthly == 0:
            continue
        if not DEBT_HINT.search(text) or not any(round(x) in nums for x in (debt.outstanding, debt.emi_monthly) if x):
            continue  # a debt needs a debt word and a stated amount
        if asked_emi and abs(debt.emi_monthly - asked_emi) < 1:
            continue  # the EMI being asked about is not an existing debt
        proposed["debts"] = [*proposed["debts"], debt.model_dump()]
        changed.append("debts")
    try:
        Profile(**proposed)
    except ValidationError:
        return base, [], gen
    return proposed, sorted(set(changed)), gen
