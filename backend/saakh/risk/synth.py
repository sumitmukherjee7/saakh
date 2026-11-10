"""Synthetic MSME population with a known causal structure.

Why synthetic: no public dataset links Indian micro-enterprise bank-statement
cash flows to repayment outcomes *and* protected attributes. A structural
simulator lets us (1) train the pipeline end-to-end, (2) evaluate fairness on
outcomes for *every* applicant, including those a traditional policy would
reject (no reject-inference problem), and (3) state exactly which mechanisms
create disparities. Swapping in a lender's real data only changes this file.

Causal story (documented in docs/MODEL_CARD.md):
  * latent business quality h ~ N(0,1), identically distributed across gender,
    area and social group, viability does not depend on who you are;
  * repayment depends on h, on total leverage, and on idiosyncratic shocks
    NOT on gender, area, caste or zone;
  * but *measurement* differs by group: rural / women-led businesses are
    smaller, more cash-based (less visible in statements) and rely more on
    moneylenders because of access gaps; they also less often hold ITRs or
    collateral titled in their name.
So a model that uses level/visibility features, or a document-based policy,
can be unfair even though true risk is group-neutral.
"""
from __future__ import annotations

import numpy as np

from ..cashflow.features import Monthly, compute_features
from ..cashflow.seasonality import SEASONAL_INDEX
from ..util import annuity_emi

ACTIVITIES = ["tailoring", "fabrication", "dairy", "leaf_plates", "food_processing", "street_food", "retail", "repair_services"]
ACT_MU = {"tailoring": 10.75, "fabrication": 12.4, "dairy": 10.6, "leaf_plates": 11.0, "food_processing": 11.2,
          "street_food": 10.55, "retail": 11.2, "repair_services": 10.9}
ACT_INPUT = {"tailoring": 0.37, "fabrication": 0.52, "dairy": 0.42, "leaf_plates": 0.39, "food_processing": 0.5,
             "street_food": 0.52, "retail": 0.74, "repair_services": 0.3}
ACT_PAYERS = {"tailoring": 60, "fabrication": 20, "dairy": 12, "leaf_plates": 18, "food_processing": 35,
              "street_food": 110, "retail": 100, "repair_services": 40}
ACT_TOP = {"tailoring": 0.04, "fabrication": 0.22, "dairy": 0.03, "leaf_plates": 0.2, "food_processing": 0.1,
           "street_food": 0.03, "retail": 0.03, "repair_services": 0.06}
ACT_RISK = {"tailoring": 0.0, "fabrication": 0.1, "dairy": -0.1, "leaf_plates": 0.05, "food_processing": 0.05,
            "street_food": 0.2, "retail": 0.15, "repair_services": 0.0}
ZONES = ["north", "south", "east", "west", "central", "northeast"]
MONTHS_ALL = ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07",
              "2026-08", "2026-09", "2026-10"]


def _sig(x):
    return 1 / (1 + np.exp(-x))


def generate(n: int = 30000, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    female = rng.random(n) < 0.42
    rural = rng.random(n) < 0.55
    zone = rng.choice(len(ZONES), n, p=[0.25, 0.2, 0.17, 0.18, 0.13, 0.07])
    social = rng.choice(4, n, p=[0.3, 0.42, 0.18, 0.10])  # general, obc, sc, st
    pf = np.array([0.24, 0.03, 0.18, 0.14, 0.15, 0.06, 0.12, 0.08])
    pm = np.array([0.08, 0.22, 0.12, 0.03, 0.08, 0.17, 0.18, 0.12])
    act = np.where(female, rng.choice(8, n, p=pf / pf.sum()), rng.choice(8, n, p=pm / pm.sum()))
    h = rng.standard_normal(n)

    nm = np.where(rng.random(n) < 0.6, 12, rng.integers(5, 12, n))
    rows, feats = [], []
    meta = {k: np.zeros(n) for k in ("new_dsr", "has_itr", "has_collateral", "vintage", "bureau_ok", "pd_true",
                                      "loan", "avg_in")}
    default = np.zeros(n, dtype=int)
    for i in range(n):
        a = ACTIVITIES[act[i]]
        logR = ACT_MU[a] + 0.22 * h[i] - 0.25 * rural[i] - 0.18 * female[i] + rng.normal(0, 0.45)
        R = np.exp(logR)
        vis = np.clip(rng.beta(8, 2) if not rural[i] else rng.beta(5, 2.5), 0.3, 1.0)  # share of revenue visible in bank
        dig = np.clip(rng.beta(9, 1.5) if not rural[i] else rng.beta(6, 2), 0.2, 1.0)
        months = MONTHS_ALL[-nm[i]:]
        idx = np.array([SEASONAL_INDEX[a][int(m[5:7]) - 1] for m in months])
        amp = rng.uniform(0.6, 1.2)
        season = 1 + amp * (idx - 1)
        g = 0.012 * h[i] + rng.normal(0, 0.008)
        sig_m = 0.07 + 0.16 * _sig(-1.1 * h[i]) + rng.uniform(0, 0.05)
        t = np.arange(nm[i])
        bi = R * vis * season * np.exp(g * t) * np.exp(rng.normal(0, sig_m, nm[i]))
        rho_b = np.clip(ACT_INPUT[a] + rng.normal(0, 0.05) - 0.025 * h[i], 0.1, 0.9)
        bo = bi * rho_b * np.exp(rng.normal(0, 0.08, nm[i]))
        margin = np.clip(0.075 + 0.045 * h[i] + rng.normal(0, 0.06), -0.25, 0.45)
        ho_share = np.clip(1 - rho_b - margin, 0.02, 0.95)
        ho = bi.mean() * ho_share * np.exp(rng.normal(0, 0.22, nm[i]))  # household draw is sticky, not seasonal
        has_emi = rng.random() < (0.22 + 0.15 * (not rural[i]) + 0.08 * (not female[i]))
        emi = np.full(nm[i], bi.mean() * rng.uniform(0.02, 0.14)) if has_emi else np.zeros(nm[i])
        p_inf = _sig(-1.55 - 0.65 * h[i] + 0.55 * rural[i] + 0.45 * female[i])
        inf = np.full(nm[i], bi.mean() * rng.uniform(0.03, 0.13)) if rng.random() < p_inf else np.zeros(nm[i])
        outflow_daily = (bo + ho + emi + inf).mean() / 30
        buffer = np.exp(rng.normal(2.3 + 0.38 * h[i], 0.55))
        ab = np.maximum(outflow_daily * buffer * np.exp(rng.normal(0, 0.25, nm[i])), 100)
        lam = (0.5 if has_emi else 0.06) * np.exp(-1.4 * h[i])
        bounces = int(rng.poisson(lam * nm[i] / 12))
        payers = np.maximum(1, rng.poisson(ACT_PAYERS[a] * vis * dig * np.exp(0.12 * h[i] + rng.normal(0, 0.3)), nm[i]))
        top = float(np.clip(rng.beta(2, 2 / ACT_TOP[a] - 2) if ACT_TOP[a] < 0.5 else 0.5, 0.005, 0.95))
        m = Monthly(months=months, biz_in=bi.tolist(), biz_out=bo.tolist(), hh_out=ho.tolist(), emi_out=emi.tolist(),
                    informal_out=inf.tolist(), avg_bal=ab.tolist(), payers=payers.tolist(), top_payer_share=top,
                    bounces=bounces, digital_share=float(dig))
        f = compute_features(m, SEASONAL_INDEX[a])
        feats.append(f)
        # ---- new loan & outcome ----
        loan = bi.mean() * rng.uniform(1.0, 5.0)
        new_emi = annuity_emi(loan, 0.12, 36)
        new_dsr = new_emi / bi.mean()
        f["proposed_dsr"] = float(new_dsr)
        lev = emi.mean() / bi.mean() + inf.mean() / bi.mean() + new_dsr
        logit = (-2.8 - 1.15 * h[i] + 3.5 * (lev - 0.22) + ACT_RISK[a] + rng.normal(0, 0.3))
        p = _sig(logit)
        default[i] = int(rng.random() < p)
        meta["pd_true"][i] = p
        meta["new_dsr"][i] = new_dsr
        meta["loan"][i] = loan
        meta["avg_in"][i] = bi.mean()
        meta["has_itr"][i] = rng.random() < _sig(-1.25 + 0.85 * (not rural[i]) - 0.65 * female[i] + 0.55 * (logR - 11.2))
        meta["has_collateral"][i] = rng.random() < _sig(-0.35 - 1.35 * female[i] + 0.25 * rural[i])
        meta["vintage"][i] = rng.gamma(2.2, 2.6)
        meta["bureau_ok"][i] = bounces == 0
    names = list(feats[0].keys())
    X = np.array([[f[k] for k in names] for f in feats])
    return {
        "X": X, "feature_names": names, "y": default, "h": h,
        "female": female, "rural": rural, "zone": zone, "social": social, "activity": act,
        "new_dsr": meta["new_dsr"], "pd_true": meta["pd_true"], "loan": meta["loan"], "avg_in": meta["avg_in"],
        "has_itr": meta["has_itr"].astype(bool), "has_collateral": meta["has_collateral"].astype(bool),
        "vintage": meta["vintage"], "bureau_ok": meta["bureau_ok"].astype(bool), "months": nm,
    }
