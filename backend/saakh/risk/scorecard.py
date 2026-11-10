"""Monotone Weight-of-Evidence scorecard: fitting and inference.

Chosen over a black-box model because a branch manager, an auditor and the
entrepreneur all need the *same* explanation: each factor contributes points
from a published table, bins are monotone in the economically sensible
direction, and reason codes fall out exactly (no post-hoc approximation).
The training script benchmarks it against a monotone gradient-boosting
challenger to quantify what interpretability costs (it costs little).
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from ..cashflow.features import FEATURE_META

ARTIFACTS = Path(__file__).parent / "artifacts"
PDO, BASE_SCORE, BASE_ODDS = 40.0, 600.0, 30.0  # 600 points ↔ 30:1 good:bad, +40 points doubles the odds
FACTOR = PDO / math.log(2)
OFFSET = BASE_SCORE - FACTOR * math.log(BASE_ODDS)

BANDS = [("A", 0.03), ("B", 0.06), ("C", 0.10), ("D", 0.18), ("E", 1.01)]
BAND_TEXT = {
    "A": {"en": "Low risk", "hi": "कम जोखिम"}, "B": {"en": "Low–moderate risk", "hi": "कम–मध्यम जोखिम"},
    "C": {"en": "Moderate risk", "hi": "मध्यम जोखिम"}, "D": {"en": "Elevated risk", "hi": "बढ़ा हुआ जोखिम"},
    "E": {"en": "High risk", "hi": "उच्च जोखिम"},
}
POLICY_PD = 0.10  # Saakh recommends (never decides) approval for bands A–C


def band_of(pd: float) -> str:
    return next(b for b, ub in BANDS if pd < ub)


# --------------------------------------------------------------------------- #
# Fitting helpers (used by train.py)
# --------------------------------------------------------------------------- #
def _bin_stats(x, y, edges):
    idx = np.searchsorted(edges, x, side="right")
    k = len(edges) + 1
    bad = np.bincount(idx, weights=y, minlength=k)
    tot = np.bincount(idx, minlength=k).astype(float)
    return bad, tot


def monotone_bins(x: np.ndarray, y: np.ndarray, direction: int, max_bins: int = 7, min_frac: float = 0.04) -> list[float]:
    """Quantile bins merged until bad-rate is monotone in `direction`
    (+1: higher x ⇒ lower bad rate) and every bin has ≥ min_frac of data."""
    qs = np.unique(np.quantile(x, np.linspace(0, 1, max_bins + 1)[1:-1]))
    edges = list(qs)
    while True:
        bad, tot = _bin_stats(x, y, np.array(edges))
        rate = bad / np.maximum(tot, 1)
        # merge smallest bins first
        small = [i for i in range(len(tot)) if tot[i] < min_frac * len(x)]
        viol = []
        for i in range(len(rate) - 1):
            if direction > 0 and rate[i + 1] > rate[i] + 1e-12:
                viol.append(i)
            if direction < 0 and rate[i + 1] < rate[i] - 1e-12:
                viol.append(i)
        if not edges or (not small and not viol):
            return edges
        i = (small or viol)[0]
        j = min(i, len(edges) - 1)  # remove the edge between bin i and i+1 (or the last edge)
        edges.pop(j)


def woe_table(x, y, edges, smooth: float = 0.5):
    bad, tot = _bin_stats(x, y, np.array(edges))
    good = tot - bad
    B, G = y.sum(), len(y) - y.sum()
    woe = np.log(((good + smooth) / (G + smooth)) / ((bad + smooth) / (B + smooth)))
    iv = float((((good + smooth) / (G + smooth)) - ((bad + smooth) / (B + smooth))) @ woe)
    return woe, tot, bad, iv


def woe_transform(x, edges, woe):
    return np.asarray(woe)[np.searchsorted(np.asarray(edges), x, side="right")]


# --------------------------------------------------------------------------- #
# Inference
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def load() -> dict:
    with open(ARTIFACTS / "scorecard.json", encoding="utf-8") as fh:
        return json.load(fh)


def _fmt(feature: str, v: float) -> str:
    f = FEATURE_META.get(feature, {}).get("fmt")
    if f == "pct":
        return f"{v * 100:.0f}%"
    if f == "days":
        return f"{v:.0f} days"
    if f == "months":
        return f"{v:.0f} months"
    if f == "log":
        return f"~{math.expm1(v):.0f}"
    if f == "int":
        return f"{v:.0f}"
    return f"{v:.2f}"


def _bin_label(feature: str, edges: list[float], i: int) -> str:
    lo = None if i == 0 else edges[i - 1]
    hi = None if i == len(edges) else edges[i]
    if lo is None:
        return f"< {_fmt(feature, hi)}"
    if hi is None:
        return f"≥ {_fmt(feature, lo)}"
    return f"{_fmt(feature, lo)} – {_fmt(feature, hi)}"


def score(features: dict[str, float], lang: str = "en") -> dict[str, Any]:
    sc = load()
    contrib = []
    raw_logit = sc["intercept"]
    total_points = 0.0
    for f in sc["features"]:
        name = f["name"]
        x = float(features[name])
        i = int(np.searchsorted(np.asarray(f["edges"]), x, side="right"))
        w = f["woe"][i]
        raw_logit += f["coef"] * w
        pts = f["points"][i]
        total_points += pts
        best = max(f["points"])
        # next better bin in the improving direction (counterfactual advice)
        better = None
        cands = [(j, p) for j, p in enumerate(f["points"]) if p > pts]
        if cands:
            j = min(cands, key=lambda jp: abs(jp[0] - i))[0]
            target = f["edges"][j - 1] if j > i else f["edges"][j]
            better = {"to_bin": _bin_label(name, f["edges"], j), "points_gain": round(f["points"][j] - pts, 1),
                      "threshold": target}
        meta = FEATURE_META[name]
        contrib.append({
            "feature": name, "label": meta["label"], "value": x, "display": _fmt(name, x),
            "bin": _bin_label(name, f["edges"], i), "points": round(pts, 1), "max_points": round(best, 1),
            "gap": round(best - pts, 1), "advice": meta["advice"], "better": better, "loan_feature": bool(meta.get("loan")),
        })
    cal = sc["calibration"]
    pd = float(1 / (1 + math.exp(-(cal["a"] + cal["b"] * raw_logit))))
    # bootstrap ensemble → model-uncertainty interval
    ens = []
    for bmod in sc["bootstrap"]:
        lg = bmod["intercept"] + sum(c * f["woe"][int(np.searchsorted(np.asarray(f["edges"]), float(features[f["name"]]), side="right"))]
                                     for c, f in zip(bmod["coefs"], sc["features"]))
        ens.append(1 / (1 + math.exp(-(cal["a"] + cal["b"] * lg))))
    lo, hi = (float(np.quantile(ens, 0.05)), float(np.quantile(ens, 0.95))) if ens else (pd, pd)
    thin = features.get("months_active", 12) < 9
    if thin:  # thin file: widen interval to reflect feature-measurement noise
        lo, hi = max(0.0, lo * 0.7), min(1.0, hi * 1.4)
    b = band_of(pd)
    reasons = sorted([c for c in contrib if c["gap"] > 0.5], key=lambda c: -c["gap"])[:4]
    strengths = sorted([c for c in contrib if c["gap"] <= 0.5], key=lambda c: -c["points"])[:3]
    return {
        "pd": round(pd, 4), "pd_low": round(min(lo, pd), 4), "pd_high": round(max(hi, pd), 4),
        "band": b, "band_text": BAND_TEXT[b], "score": int(round(total_points)),
        "recommend": pd < POLICY_PD, "policy_pd": POLICY_PD, "thin_file": thin,
        "output_kind": "simulated_risk_estimate",
        "output_note": {"en": "Simulated risk estimate from a model trained on synthetic data, not a validated probability of default.",
                        "hi": "कृत्रिम डेटा पर प्रशिक्षित मॉडल का सिम्युलेटेड जोखिम अनुमान, प्रमाणित डिफ़ॉल्ट संभावना नहीं।"},
        "interval_method": "bootstrap of 25 coefficient refits" + (" + heuristic x0.7/x1.4 widening for thin files" if thin else ""),
        "contributions": contrib,
        "reason_codes": [{"feature": r["feature"], "label": r["label"], "display": r["display"], "points_lost": r["gap"],
                          "advice": r["advice"], "better": r["better"]} for r in reasons],
        "strengths": [{"feature": s["feature"], "label": s["label"], "display": s["display"]} for s in strengths],
        "model_version": sc["version"],
    }


def release_status() -> dict[str, Any]:
    """Release gate read from the training report: fairness gates must pass for production use."""
    try:
        rep = json.loads((ARTIFACTS / "model_report.json").read_text(encoding="utf-8"))
        fair = rep["fairness"]
    except (OSError, KeyError, ValueError):
        return {"status": "blocked", "reason": "model report missing or unreadable, fails closed"}
    if fair.get("passed"):
        return {"status": "released", "reason": fair.get("release_decision")}
    return {"status": "blocked", "reason": fair.get("release_decision"), "messages": fair.get("messages", [])}
