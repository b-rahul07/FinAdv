"""Rupee rounding and Indian digit grouping (1,23,45,678)."""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal


def round_half_up(x: float, ndigits: int = 0) -> float:
    q = Decimal(1).scaleb(-ndigits)
    return float(Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP))


def round_up_to(x: float, step: float) -> float:
    """Round up to a friendly step, e.g. ₹5,833 -> ₹5,900 with step 100."""
    return math.ceil(x / step) * step if x > 0 else 0.0


def group_indian(n: int) -> str:
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if n < 0 else "") + s


def inr(x: float, decimals: int = 0) -> str:
    """₹ string with Indian grouping. inr(1234567.5, 2) -> '₹12,34,567.50'."""
    x = round_half_up(x, decimals)
    whole = int(abs(x))
    out = "₹" + group_indian(whole)
    if decimals:
        frac = f"{abs(x) - whole:.{decimals}f}"[1:]
        out += frac
    return ("-" if x < 0 else "") + out


def inr_words(x: float) -> str:
    """Lakh/crore shorthand for prose: 1250000 -> '₹12.5 lakh'."""
    a = abs(x)
    if a >= 1e7:
        v, unit = a / 1e7, "crore"
    elif a >= 1e5:
        v, unit = a / 1e5, "lakh"
    else:
        return inr(x)
    txt = f"{round_half_up(v, 2):.2f}".rstrip("0").rstrip(".")
    return ("-" if x < 0 else "") + f"₹{txt} {unit}"
