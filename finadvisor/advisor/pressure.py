"""Pressure fencing (report Algorithm 3). Wishes are recorded and acknowledged; they never change capacity,
and under the default config they do not change the measured willingness level either."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Six pressure types, report §4.5.
PATTERNS: dict[str, re.Pattern] = {
    "finfluencer": re.compile(r"youtube|youtuber|instagram|insta\b|telegram|influencer|finfluencer|tips? (group|channel)|reel", re.I),
    "peer_success": re.compile(r"\b(friend|friends|colleague|cousin|brother|sister|neighbou?r|everyone|people)\b.*\b(made|earned|got|doubled|tripled|\d+x)\b"
                               r"|\b(made|earned|got)\b.*\b\d+\s?x\b", re.I),
    "rally_fomo": re.compile(r"all[- ]time high|rally|missing out|fomo|market is (up|booming|flying)|before it'?s too late|everyone is buying|nifty is up", re.I),
    "self_expertise": re.compile(r"i know what i'?m doing|i'?m (an )?(expert|experienced|pro)|trust me|i understand (the )?risk|i can handle (the )?risk|i'?ve been trading", re.I),
    "authority": re.compile(r"\bmy (ca|advisor|adviser|banker|father|dad|uncle|boss|manager)\b.*\b(said|says|told|suggested|recommends?)\b"
                            r"|\b(expert|analyst)s? (said|say|recommend)", re.I),
    "insistence": re.compile(r"just tell me|stop (lecturing|warning)|i don'?t care|i still want|i insist|give me the (name|stock|option)", re.I),
}

# Shelf products a wish can point at (used for the conflict line and Check routing).
PRODUCT_WORDS: list[tuple[str, re.Pattern]] = [
    ("fno", re.compile(r"\bf\s?&\s?o\b|\bfno\b|futures|\boptions? (trad|to trad)|\btrad\w* options\b|\b(call|put) options?\b"
                       r"|intraday|which options", re.I)),
    ("crypto", re.compile(r"crypto|bitcoin|\bbtc\b|ethereum|\beth\b|dogecoin", re.I)),
    ("mid_small_cap_fund", re.compile(r"small[- ]?cap|mid[- ]?cap|smallcase", re.I)),
    ("direct_equity", re.compile(r"\b(stocks?|shares?|equities)\b(?! (mutual )?funds?)|\bipo\b|penny", re.I)),
    ("new_emi", re.compile(r"\bemi\b|\bbnpl\b|buy now pay later|no[- ]cost emi|loan (for|to buy)|personal loan", re.I)),
    ("large_cap_index_fund", re.compile(r"index fund|nifty ?50 fund|nifty fund|sensex fund", re.I)),
    ("elss", re.compile(r"\belss\b|tax[- ]saving fund", re.I)),
    ("flexi_cap_fund", re.compile(r"flexi[- ]?cap|equity (mutual )?fund", re.I)),
    ("gold_etf_fund", re.compile(r"gold", re.I)),
    ("nps", re.compile(r"\bnps\b|national pension", re.I)),
    ("ppf", re.compile(r"\bppf\b", re.I)),
    ("fixed_deposit", re.compile(r"\bfd\b|fixed deposit", re.I)),
]


@dataclass
class PressureReading:
    types: list[str] = field(default_factory=list)
    products: list[str] = field(default_factory=list)
    persistent: bool = False

    @property
    def is_pressure(self) -> bool:
        return bool(self.types) or self.persistent


def products_in(text: str) -> list[str]:
    seen = []
    for pid, pat in PRODUCT_WORDS:
        if pat.search(text) and pid not in seen:
            seen.append(pid)
    return seen


def read(text: str, earlier_user_turns: list[str]) -> PressureReading:
    types = [name for name, pat in PATTERNS.items() if pat.search(text)]
    prods = products_in(text)
    # persistence: the same product wish appears in two or more earlier turns
    persistent = False
    if prods:
        repeats = sum(1 for t in earlier_user_turns[-6:] if set(products_in(t)) & set(prods))
        persistent = repeats >= 2
    if persistent and "persistence" not in types:
        types.append("persistence")
    return PressureReading(types, prods, persistent)


def conflict_line(wish_name: str, first: str, because: str) -> str:
    """The deterministic acknowledgement: 'You want X; your current situation means Y first, because Z.'"""
    return f"You want {wish_name}; your current situation means {first} first, because {because}."
