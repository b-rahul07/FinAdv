"""Routes a message to Learn, Plan or Check. Deterministic and deliberately biased towards the pipeline:
sending a general question through Plan costs time; letting a personal one skip the pipeline breaks §2.4."""

from __future__ import annotations

import re
from dataclasses import dataclass

from finadvisor.advisor import pressure

PERSONAL = re.compile(
    r"\b(i|i'm|im|i've|ive|i'd|my|me|mine|myself|we|our|us)\b|\bfor me\b|\bshould i\b|\bcan i\b"
    # misspellings and Hinglish (2026-11-11, adversarial set): first-person words, first-person verb endings
    # ("kya karu", "kisme rakhu") and requests addressed to the advisor ("plan bana do", "batao")
    r"|\b(shud|shoud|shd|cud|shall) i\b|\benou?gh\b|\benuf\b"
    r"|\b(mujhe|mujhko|mera|meri|mere|main|mai|hum|hamara|hamare|hamari|apna|apne|apni|karu|karun|karoon|chahiye|"
    r"daalu|dalu|rakhu|kharidu|kharidoon|lagau|lagaun|banao|bana do|banado|batao|bata do|batado|karo|kar do|kardo)\b",
    re.I)
MONEY = re.compile(
    r"₹|\brs\.?\s?\d|\b\d[\d,.]*\s?(k|l|lakh|lakhs|lac|cr|crore|crores)\b|\bsalary|\bincome|\bemi\b|\bloan|\bsav(e|ing|ings)\b"
    r"|\binvest|\bsip\b|\bportfolio|\bexpenses?\b|\bdebt|\bcredit card|\bbnpl\b|\binsurance|\bcover\b|\bretire|\bgoal"
    r"|\bpaisa|\bpaise|\brupay|\brupaye|\btankha|\bkama\w*|\bbachat|\bbacha\w*|\bnivesh|\bkarz|\budhaar|\bsona\b|\bbazaa?r"
    r"|\bmony\b|\bmoney\b|\bfunds?\b|\bfnds?\b|\bstoc?ks?\b|\bstoks?\b|\bshares?\b",
    re.I)
CHECK = re.compile(
    r"\bshould i (buy|take|get|start|trade|go for|try)\b|\bshould i invest in\b|\bcan i afford\b"
    r"|\bis it (ok|okay|wise|safe|good) (to|for me)\b|\b(on|via|with) (an? )?(emi|bnpl|no[- ]cost emi)\b"
    r"|\b(right|good|best|suitable|a good (idea|fit|choice)|ok|okay|wise|safe) for me\b|\bsuits? me\b|\bsuitable\b"
    r"|\bworth (it|buying)\b.*\b(emi|loan)\b|\boptions? (to )?trad|\btrad\w* options\b"
    r"|f&o|\bfno\b|\bfutures\b|\bcrypto|\bbitcoin|\bsmall[- ]?caps?\b|\bmid[- ]?caps?\b"
    r"|\bgood (idea|buy|time to (buy|invest))\b", re.I)
# A request to pick, buy or sell something ("recommend 3 stocks", "which bank share will go up", "good buy right
# now"): with a product the shelf never plans, it is a Check, whose fixed answer explains why no stock is named.
ASK = re.compile(r"\b(buy|by|sell|hold|recommend\w*|suggest|best|which|wich|konsa|kaunsa|kaunsi|konsi|good|right|safe|wise|"
                 r"worth|tomorrow|this week|next week|apply|pick|tip|tips|multibagger\w*|10x|double|tomorow)\b", re.I)
NEVER_PLANNED = {"direct_equity", "fno", "crypto", "new_emi", "mid_small_cap_fund"}
LEARN = re.compile(r"^\s*((can|could|please|pls|plz) (you )?(please )?)?(what|what's|whats|wat|how does|how do|how is|how are|"
                   r"explain|define|difference|meaning|tell me about|why do|why is|is there)\b", re.I)
# The object pronoun of a general question ("tell me about PPF", "explain ELSS to me") is not a personal fact;
# "for me" stays personal ("what is the best fund for me" is a Check).
LEARN_ME = re.compile(r"\b(tell|explain|describe|teach|show)\s+(to\s+)?(me|us)\b|\bto (me|us)\s*[?.!]*\s*$", re.I)
GREETING = re.compile(r"^\s*(hi|hello|hey|thanks|thank you|ok|okay|good (morning|evening))\b[\s!.]*$", re.I)


@dataclass
class Route:
    kind: str        # learn | plan | check | chat
    reason: str


def route(text: str) -> Route:
    t = text.strip()
    if GREETING.match(t):
        return Route("chat", "greeting")
    learn = bool(LEARN.match(t))
    personal = bool(PERSONAL.search(LEARN_ME.sub(" ", t) if learn else t))
    money = bool(MONEY.search(t))
    asks_never = bool(set(pressure.products_in(t)) & NEVER_PLANNED) and (personal or bool(ASK.search(t)))
    if (CHECK.search(t) or asks_never) and (personal or not learn or asks_never and bool(ASK.search(t))):
        return Route("check", "asks whether a product or purchase suits them")
    if personal and money:
        return Route("plan", "about the user's own money")
    if learn and not personal:
        return Route("learn", "general question")
    if personal:
        return Route("plan", "personal and unclear; routed to the pipeline to be safe")
    return Route("learn", "general question")
