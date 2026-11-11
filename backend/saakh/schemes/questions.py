"""Value-of-information question planner.

Eligible applicants drop out of long forms. Instead of a 40-field form, the
agent asks *one* question at a time, always the one whose answer is expected to
settle the most rupee-weighted scheme decisions:

    VOI(f) = Σ_v P(f = v) · Σ_{s : status(s) = UNKNOWN} w_s · settled_s(f = v)
             + ½ · Σ_s w_s · (fraction of s's open questions closed by f)

where w_s is the estimated annual benefit of scheme s for this applicant and
P(f = v) is a prior over answers (from the fact registry). Sensitive questions
(caste, disability, minority status) carry a cost factor, so they are asked only
when they actually move a decision, data minimisation by construction.
"""
from __future__ import annotations

from typing import Any

from ..facts import FACTS, derive
from .benefits import estimate_value
from .engine import T, F, U, load_kb, status_and_missing

SENSITIVE_COST = 1.6


def _support(key: str) -> dict[Any, float]:
    f = FACTS[key]
    if f.prior:
        z = sum(f.prior.values())
        return {k: v / z for k, v in f.prior.items()}
    if f.options:
        n = len(f.options)
        return {o.value: 1 / n for o in f.options}
    return {}


def rank_questions(facts: dict, askable: set[str] | None = None, skip: set[str] | None = None) -> list[dict]:
    skip = skip or set()
    base = status_and_missing(facts)
    df = derive(facts)
    weights = {sid: max(estimate_value(sid, df), 1.0) for sid in base}
    open_schemes = {sid for sid, (st, _) in base.items() if st == U}
    candidates: set[str] = set()
    for sid in open_schemes:
        candidates |= set(base[sid][1])
    candidates = {c for c in candidates if c in FACTS and FACTS[c].question and c not in skip
                  and (askable is None or c in askable) and facts.get(c) is None}
    ranked = []
    for key in candidates:
        support = _support(key)
        if not support:
            continue
        settled_value = 0.0
        partial_value = 0.0
        affected: dict[str, float] = {}
        for v, p in support.items():
            alt = dict(facts)
            alt[key] = v
            after = status_and_missing(alt)
            for sid in open_schemes:
                st_after, miss_after = after[sid]
                if st_after in (T, F):
                    settled_value += p * weights[sid]
                    affected[sid] = affected.get(sid, 0) + p
                else:
                    before_n = max(len(base[sid][1]), 1)
                    closed = (before_n - len(miss_after)) / before_n
                    if closed > 0:
                        partial_value += 0.5 * p * weights[sid] * closed
                        affected[sid] = affected.get(sid, 0) + p * closed
        voi = settled_value + partial_value
        if FACTS[key].sensitive:
            voi /= SENSITIVE_COST
        if voi <= 0:
            continue
        kb = load_kb()
        ranked.append({
            "fact": key, "voi": round(voi, 1),
            "affects": [{"id": sid, "short": kb[sid]["short"], "short_hi": kb[sid].get("short_hi", kb[sid]["short"]), "p_settle": round(p, 2)}
                        for sid, p in sorted(affected.items(), key=lambda x: -x[1])],
        })
    ranked.sort(key=lambda r: -r["voi"])
    return ranked


def next_question(facts: dict, askable: set[str] | None = None, skip: set[str] | None = None) -> dict | None:
    r = rank_questions(facts, askable, skip)
    return r[0] if r else None
