"""Willingness scorer: Grable & Lytton 13-item scale plus investing experience."""

from __future__ import annotations

from dataclasses import dataclass

from finadvisor.advisor.capacity import min_level
from finadvisor.advisor.profile import Profile


@dataclass
class WillingnessResult:
    score: int | None        # 13–47 when complete
    answered: int
    band_level: str | None   # level from the score alone
    level: str               # after the experience cap
    capped_by_experience: bool

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def score_answers(answers: dict[int, str], cfg: dict) -> tuple[int, int]:
    """Return (total, answered). Unknown option keys raise ValueError."""
    total = 0
    answered = 0
    for item in cfg["items"]:
        key = answers.get(item["n"]) or answers.get(str(item["n"]))  # JSON round-trips turn keys into str
        if key is None:
            continue
        scores = {o["key"]: o["score"] for o in item["options"]}
        if key not in scores:
            raise ValueError(f"item {item['n']}: unknown option {key!r}")
        total += scores[key]
        answered += 1
    return total, answered


def band(score: int, cfg: dict) -> str:
    b = cfg["bands"]
    if score <= b["low_max"]:
        return "low"
    if score <= b["medium_max"]:
        return "medium"
    return "high"


def assess(p: Profile, cfg: dict) -> WillingnessResult:
    total, answered = score_answers(p.gl_answers, cfg)
    n_items = len(cfg["items"])
    if answered < n_items:
        # An incomplete questionnaire is never read generously: treat willingness as Low.
        return WillingnessResult(None, answered, None, "low", False)
    band_level = band(total, cfg)
    level = band_level
    cap = cfg.get("experience_cap", {}).get(p.experience)
    if cap:
        level = min_level(level, cap)
    return WillingnessResult(total, answered, band_level, level, level != band_level)
