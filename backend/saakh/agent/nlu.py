"""Offline Hindi / Hinglish / English understanding for the entrepreneur's
words. Deterministic and dependency-free, so the agent works with no network
and every interpretation is reproducible and testable.
"""
from __future__ import annotations

import re
from typing import Any

from ..facts import FACTS, coerce

HI_NUM = {
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5, "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9,
    "दस": 10, "ग्यारह": 11, "बारह": 12, "पंद्रह": 15, "बीस": 20, "पच्चीस": 25, "तीस": 30, "पैंतीस": 35,
    "चालीस": 40, "पचास": 50, "साठ": 60, "सत्तर": 70, "अस्सी": 80, "नब्बे": 90, "सौ": 100,
    "डेढ़": 1.5, "डेढ": 1.5, "ढाई": 2.5, "dedh": 1.5, "dhai": 2.5,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "twenty": 20, "fifty": 50, "ek": 1, "do": 2, "teen": 3, "char": 4, "paanch": 5, "das": 10, "bees": 20, "pachas": 50,
}
MULT = [(r"करोड़|करोड|crore|cr\b", 1e7), (r"लाख|lakh|lac|lakhs|\bl\b", 1e5), (r"हज़ार|हजार|hazaar|hazar|thousand|\bk\b", 1e3)]

ACTIVITY_KW = [
    ("tailoring", r"सिलाई|दर्ज़ी|दर्जी|कढ़ाई|बुटीक|silai|tailor|darzi|boutique|stitch|embroider"),
    ("fabrication", r"वेल्डिंग|फैब्रिक|ग्रिल|लोहे|welding|fabricat|grill|cnc|plasma|lathe"),
    ("dairy", r"गाय|भैंस|डेयरी|दूध|cow|buffalo|dairy|milk"),
    ("leaf_plates", r"पत्तल|दोना|leaf[ -]?plate|pattal|dona"),
    ("street_food", r"ठेला|ठेले|चाय|नाश्ता|cart|thela|chai|stall|street"),
    ("retail", r"किराना|kirana|general store|grocery|दुकान|\bshop\b|\bstore\b"),
    ("food_processing", r"अचार|पापड़|मसाला|pickle|papad|masala|food processing"),
    ("repair_services", r"मरम्मत|repair|mechanic|मैकेनिक"),
]
SECTOR_OF = {"tailoring": "manufacturing", "fabrication": "manufacturing", "dairy": "allied_agri",
             "leaf_plates": "manufacturing", "street_food": "trading", "retail": "trading",
             "food_processing": "manufacturing", "repair_services": "services"}
PURPOSE_KW = [("livestock", r"गाय|भैंस|cow|buffalo|पशु"), ("machinery", r"मशीन|machine|चूल्हा|stove|equipment|उपकरण|cnc|cutter"),
              ("working_capital", r"माल|stock|स्टॉक|कच्चा|raw material|restock|inventory")]
# \b is unreliable after Devanagari vowel signs (e.g. "ं"), so end-of-token is explicit
_END = r"(?=$|[\s,.!?।])"
YES = r"^(जी हाँ|हाँ|हां|हा|जी|haan|haa|ha|han|yes|y|yeah|yep|sure|ok|okay|bilkul|बिल्कुल|ठीक)" + _END
NO = r"^(नहीं|नही|ना|nahi|nahin|nai|no|n|nope|na)" + _END


def parse_amount(text: str) -> float | None:
    t = text.lower().replace(",", "")
    m = re.search(r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(करोड़|करोड|crore|cr\b|लाख|lakh|lac|lakhs|हज़ार|हजार|hazaar|hazar|thousand|k\b|l\b)?", t)
    best = None
    for m in re.finditer(r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(करोड़|करोड|crore|cr\b|लाख|lakh|lac|lakhs|हज़ार|हजार|hazaar|hazar|thousand|k\b|l\b)?", t):
        n = float(m.group(1))
        unit = m.group(2) or ""
        for pat, mul in MULT:
            if unit and re.fullmatch(pat, unit):
                n *= mul
                break
        if best is None or n > best:
            best = n
    if best is not None and best >= 100:
        return best
    # word numbers: "डेढ़ लाख", "पच्चीस हज़ार", "तीन लाख"
    for pat, mul in MULT:
        mm = re.search(r"(\S+)\s*(?:" + pat + ")", t)
        if mm:
            w = mm.group(1)
            if w in HI_NUM:
                return HI_NUM[w] * mul
            try:
                return float(w) * mul
            except ValueError:
                pass
    return best


def parse_int(text: str) -> int | None:
    m = re.search(r"\d+", text)
    if m:
        return int(m.group(0))
    for w, v in HI_NUM.items():
        if re.search(rf"(^|\s){re.escape(w)}(\s|$)", text.lower()) and v == int(v):
            return int(v)
    return None


def parse_yes_no(text: str) -> bool | None:
    t = text.strip().lower()
    if re.search(YES, t):
        return True
    if re.search(NO, t):
        return False
    return None


def intake(text: str) -> dict[str, Any]:
    """Extract what we can from the opening request."""
    out: dict[str, Any] = {}
    low = text.lower()
    amt = parse_amount(text)
    if amt:
        out["loan_amount_sought"] = int(amt)
    for act, pat in ACTIVITY_KW:
        if re.search(pat, low):
            out["activity"] = act
            out["sector"] = SECTOR_OF[act]
            break
    for pur, pat in PURPOSE_KW:
        if re.search(pat, low):
            out["loan_purpose"] = pur
            break
    if re.search(r"समूह|shg|self.help|स्वयं सहायता|\bgroup\b", low):
        out["ownership_type"] = "shg"
    return out


def answer(fact: str, text: str) -> Any:
    """Map free text to a value for `fact`; raise ValueError if unclear."""
    f = FACTS[fact]
    t = text.strip()
    if f.type == "bool":
        v = parse_yes_no(t)
        if v is None:
            raise ValueError("yes/no not understood")
        return v
    if f.type == "money":
        v = parse_amount(t)
        if v is None:
            raise ValueError("amount not understood")
        return int(v)
    if f.type == "int":
        v = parse_int(t)
        if v is None:
            raise ValueError("number not understood")
        return v
    if f.type == "enum":
        low = t.lower()
        for o in f.options:
            if str(o.value).lower() == low or o.label["en"].lower() in low or o.label["hi"] in t:
                return o.value
        for o in f.options:  # partial word match
            words = [w for w in re.split(r"[\s/()]+", o.label["en"].lower()) if len(w) > 3]
            if any(w in low for w in words):
                return o.value
        if fact == "activity":
            got = intake(t).get("activity")
            if got:
                return got
        raise ValueError("option not understood")
    return coerce(fact, t)


def is_question(text: str) -> bool:
    return bool(re.search(r"\?|क्यों|क्या|कैसे|why|how|what|kyon|kyu|explain|समझा", text.lower()))
