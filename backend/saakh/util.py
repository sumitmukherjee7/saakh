from __future__ import annotations

import hashlib
import json
from typing import Any


def inr(x: float | int | None, short: bool = False) -> str:
    """Indian-style rupee formatting: ₹1,50,000 or (short) ₹1.5 lakh."""
    if x is None:
        return "-"
    neg = x < 0
    x = abs(float(x))
    if short:
        if x >= 1e7:
            s = f"₹{x / 1e7:.2f} crore".replace(".00 ", " ")
        elif x >= 1e5:
            s = f"₹{x / 1e5:.2f}".rstrip("0").rstrip(".") + " lakh"
        else:
            s = inr(x)
        return ("-" if neg else "") + s
    n = int(round(x))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-₹" if neg else "₹") + s


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def sha256(obj: Any) -> str:
    data = obj if isinstance(obj, (bytes, bytearray)) else canonical_json(obj).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def annuity_emi(principal: float, annual_rate: float, months: int) -> float:
    r = annual_rate / 12
    if r == 0:
        return principal / months
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def annuity_pv(emi: float, annual_rate: float, months: int) -> float:
    r = annual_rate / 12
    if r == 0:
        return emi * months
    return emi * (1 - (1 + r) ** -months) / r
