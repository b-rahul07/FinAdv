"""Routes a message to Learn, Plan or Check. Deterministic and deliberately biased towards the pipeline:
sending a general question through Plan costs time; letting a personal one skip the pipeline breaks §2.4."""

from __future__ import annotations

import re
from dataclasses import dataclass

PERSONAL = re.compile(
    r"\b(i|i'm|im|i've|ive|i'd|my|me|mine|myself|we|our|us)\b|\bfor me\b|\bshould i\b|\bcan i\b", re.I)
MONEY = re.compile(
    r"₹|\brs\.?\s?\d|\b\d[\d,.]*\s?(k|l|lakh|lakhs|lac|cr|crore|crores)\b|\bsalary|\bincome|\bemi\b|\bloan|\bsav(e|ing|ings)\b"
    r"|\binvest|\bsip\b|\bportfolio|\bexpenses?\b|\bdebt|\bcredit card|\bbnpl\b|\binsurance|\bcover\b|\bretire|\bgoal",
    re.I)
CHECK = re.compile(
    r"\bshould i (buy|take|get|start|trade|go for|try)\b|\bshould i invest in\b|\bcan i afford\b"
    r"|\bis it (ok|okay|wise|safe|good) (to|for me)\b|\b(on|via|with) (an? )?(emi|bnpl|no[- ]cost emi)\b"
    r"|\b(right|good|suitable|a good (idea|fit|choice)|ok|okay|wise|safe) for me\b|\bsuits? me\b|\bsuitable\b"
    r"|\bworth (it|buying)\b.*\b(emi|loan)\b|\boptions? (to )?trad|\btrad\w* options\b"
    r"|f&o|\bfno\b|\bfutures\b|\bcrypto|\bbitcoin|\bsmall[- ]?caps?\b|\bmid[- ]?caps?\b", re.I)
LEARN = re.compile(r"^\s*(what|what's|whats|how does|how do|explain|define|difference|meaning|tell me about|why do|why is|is there)\b", re.I)
GREETING = re.compile(r"^\s*(hi|hello|hey|thanks|thank you|ok|okay|good (morning|evening))\b[\s!.]*$", re.I)


@dataclass
class Route:
    kind: str        # learn | plan | check | chat
    reason: str


def route(text: str) -> Route:
    t = text.strip()
    if GREETING.match(t):
        return Route("chat", "greeting")
    personal = bool(PERSONAL.search(t))
    money = bool(MONEY.search(t))
    if CHECK.search(t) and (personal or not LEARN.match(t)):
        return Route("check", "asks whether a product or purchase suits them")
    if personal and money:
        return Route("plan", "about the user's own money")
    if LEARN.match(t) and not personal:
        return Route("learn", "general question")
    if money and personal:
        return Route("plan", "about the user's own money")
    if personal:
        return Route("plan", "personal and unclear; routed to the pipeline to be safe")
    return Route("learn", "general question")
