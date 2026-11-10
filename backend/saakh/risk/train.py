"""Train, calibrate, fairness-audit and gate the Saakh scorecard.

    python -m saakh.risk.train

Outputs (versioned, human-readable JSON, no pickles):
  artifacts/scorecard.json     bins, WoE, coefficients, points, calibration, bootstrap ensemble
  artifacts/model_report.json  metrics, reliability curves, fairness tables, proxy audit,
                               candidate-feature gate decisions, baseline comparison
"""
from __future__ import annotations

import json
import time
from datetime import date

import numpy as np

from ..cashflow.features import FEATURE_META
from . import synth
from .ml import GBM, Isotonic, LogReg, auc as roc_auc_score, average_precision, brier as brier_score_loss, log_loss
from .scorecard import ARTIFACTS, FACTOR, OFFSET, POLICY_PD, BANDS, monotone_bins, woe_table, woe_transform

BASE = ["inflow_cv", "inflow_trend", "min_to_median", "margin_ratio", "debt_service_ratio", "informal_share",
        "buffer_days", "bounces_12m", "payer_diversity", "top_payer_share", "months_active", "neg_months_share",
        "proposed_dsr"]
CANDIDATES = ["log_avg_inflow", "digital_share"]

# Fairness gates (documented in docs/MODEL_CARD.md)
GATE_AIR = 0.80          # four-fifths rule on approval rates (hard floor)
GATE_EOD = 0.05          # |difference| in approval rate among actually-good borrowers
GATE_CAL = 0.02          # |mean PD − observed default rate| within each group
CAND_MIN_AUC_GAIN = 0.005
CAND_MAX_EOD_WORSEN = 0.01
PROXY_AUC = 0.60         # single-feature AUC for predicting gender / rural
PROXY_MIN_IV = 0.05      # ...tolerated only if the feature carries real signal


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def fit_scorecard(names, X, y, cols):
    """Monotone binning → WoE → L2 logistic; drop weak / sign-violating features."""
    keep = list(names)
    while True:
        tables = {}
        for n in keep:
            x = X[:, cols[n]]
            edges = monotone_bins(x, y, FEATURE_META[n]["dir"])
            woe, tot, bad, iv = woe_table(x, y, edges)
            tables[n] = {"edges": edges, "woe": woe, "iv": iv, "tot": tot, "bad": bad}
        weak = [n for n in keep if tables[n]["iv"] < 0.01 or len(tables[n]["edges"]) == 0]
        if weak:
            keep = [n for n in keep if n not in weak]
            continue
        W = np.column_stack([woe_transform(X[:, cols[n]], tables[n]["edges"], tables[n]["woe"]) for n in keep])
        lr = LogReg(C=1.0).fit(W, y)
        coefs = lr.coef_
        bad_sign = [keep[j] for j in range(len(keep)) if coefs[j] >= 0]
        if bad_sign:
            drop = min(bad_sign, key=lambda n: tables[n]["iv"])
            keep = [n for n in keep if n != drop]
            continue
        return {"features": keep, "tables": tables, "coefs": coefs, "intercept": float(lr.intercept_)}


def model_logit(m, X, cols):
    W = np.column_stack([woe_transform(X[:, cols[n]], m["tables"][n]["edges"], m["tables"][n]["woe"]) for n in m["features"]])
    return m["intercept"] + W @ m["coefs"], W


def ece(p, y, bins=10):
    q = np.quantile(p, np.linspace(0, 1, bins + 1))
    idx = np.clip(np.searchsorted(q, p, side="right") - 1, 0, bins - 1)
    e = 0.0
    curve = []
    for b in range(bins):
        msk = idx == b
        if msk.sum() == 0:
            continue
        e += msk.mean() * abs(p[msk].mean() - y[msk].mean())
        curve.append({"pred": round(float(p[msk].mean()), 4), "obs": round(float(y[msk].mean()), 4), "n": int(msk.sum())})
    return float(e), curve


def group_metrics(p, y, approve, groups: dict[str, np.ndarray]):
    out = {}
    for g, msk in groups.items():
        if msk.sum() < 30:
            continue
        good = (y == 0) & msk
        appr = approve & msk
        out[g] = {
            "n": int(msk.sum()),
            "default_rate": round(float(y[msk].mean()), 4),
            "mean_pd": round(float(p[msk].mean()), 4) if p is not None else None,
            "cal_gap": round(float(p[msk].mean() - y[msk].mean()), 4) if p is not None else None,
            "ece": round(ece(p[msk], y[msk], 5)[0], 4) if p is not None else None,
            "auc": round(float(roc_auc_score(y[msk], p[msk])), 4) if p is not None and 0 < y[msk].sum() < msk.sum() else None,
            "approval_rate": round(float(appr.sum() / msk.sum()), 4),
            "good_approval_rate": round(float((appr & good).sum() / max(good.sum(), 1)), 4),
            "default_rate_approved": round(float(y[appr].mean()), 4) if appr.sum() else None,
        }
    return out


def summarise(gm: dict, pairs: list[tuple[str, str]]):
    s = {}
    for a, b in pairs:
        if a in gm and b in gm:
            ra, rb = gm[a]["approval_rate"], gm[b]["approval_rate"]
            s[f"{a}_vs_{b}"] = {
                "air": round(min(ra, rb) / max(ra, rb), 3) if max(ra, rb) > 0 else None,
                "eod": round(gm[a]["good_approval_rate"] - gm[b]["good_approval_rate"], 4),
                "cal_gap_max": max(abs(gm[a]["cal_gap"] or 0), abs(gm[b]["cal_gap"] or 0)) if gm[a]["cal_gap"] is not None else None,
            }
    return s


def passes(summary: dict) -> tuple[bool, list[str]]:
    msgs, ok = [], True
    for k, v in summary.items():
        if v["air"] is not None and v["air"] < GATE_AIR:
            ok = False
            msgs.append(f"{k}: AIR {v['air']} < {GATE_AIR}")
        if abs(v["eod"]) > GATE_EOD:
            ok = False
            msgs.append(f"{k}: |EOD| {abs(v['eod'])} > {GATE_EOD}")
        if v["cal_gap_max"] is not None and v["cal_gap_max"] > GATE_CAL:
            ok = False
            msgs.append(f"{k}: calibration gap {v['cal_gap_max']} > {GATE_CAL}")
    return ok, msgs


def choose_calibration(lg, yy, seed: int = 3):
    """Pick identity vs Platt by 2-fold cross-fitting on the calibration split
    (never on the test split). Returns (a, b, diagnostics)."""
    r = np.random.default_rng(seed)
    idx = r.permutation(len(yy))
    h1, h2 = idx[: len(idx) // 2], idx[len(idx) // 2:]
    scores = {"identity": [], "platt": []}
    for fit_i, ev_i in ((h1, h2), (h2, h1)):
        scores["identity"].append(ece(sigmoid(lg[ev_i]), yy[ev_i])[0])
        pl = LogReg(C=1e6).fit(lg[fit_i].reshape(-1, 1), yy[fit_i])
        scores["platt"].append(ece(sigmoid(pl.intercept_ + pl.coef_[0] * lg[ev_i]), yy[ev_i])[0])
    mean = {k: float(np.mean(v)) for k, v in scores.items()}
    # parsimony: only recalibrate if it clearly helps (> 0.1pp ECE)
    method = "platt" if mean["platt"] < mean["identity"] - 0.001 else "identity"
    if method == "platt":
        pl = LogReg(C=1e6).fit(lg.reshape(-1, 1), yy)
        a, b = float(pl.intercept_), float(pl.coef_[0])
    else:
        a, b = 0.0, 1.0
    return a, b, {"method": method, "cv_ece": {k: round(v, 4) for k, v in mean.items()}}


def main(n: int = 30000, seed: int = 7) -> dict:
    t0 = time.time()
    d = synth.generate(n, seed)
    names = d["feature_names"]
    cols = {k: i for i, k in enumerate(names)}
    X, y = d["X"], d["y"]
    rng = np.random.default_rng(seed + 1)
    perm = rng.permutation(len(y))
    # train 50% · validation 15% (feature & proxy gates) · calibration 15% · test 20% (touched once, at the end)
    i1, i2, i3 = int(0.50 * n), int(0.65 * n), int(0.80 * n)
    tr, va, ca, te = perm[:i1], perm[i1:i2], perm[i2:i3], perm[i3:]
    groups_all = {
        "female": d["female"], "male": ~d["female"], "rural": d["rural"], "urban": ~d["rural"],
        "rural_female": d["rural"] & d["female"], "urban_male": ~d["rural"] & ~d["female"],
        **{f"zone_{z}": d["zone"] == i for i, z in enumerate(synth.ZONES)},
        **{f"social_{s}": d["social"] == i for i, s in enumerate(["general", "obc", "sc", "st"])},
    }
    groups_te = {k: v[te] for k, v in groups_all.items()}
    groups_va = {k: v[va] for k, v in groups_all.items()}
    pairs = [("female", "male"), ("rural", "urban"), ("rural_female", "urban_male"),
             ("social_sc", "social_general"), ("social_st", "social_general"), ("social_obc", "social_general")]
    zone_names = [f"zone_{z}" for z in synth.ZONES]

    def zone_pair(gm):
        """Add the most different pair of zones (by approval rate) to the gated pairs."""
        z = [g for g in zone_names if g in gm]
        lo, hi = min(z, key=lambda g: gm[g]["approval_rate"]), max(z, key=lambda g: gm[g]["approval_rate"])
        return pairs + [(lo, hi)]

    def evaluate(feature_list, split):
        """Fit on train, calibrate on calibration, measure on `split` (validation for gates, test once at the end)."""
        idx, groups = (va, groups_va) if split == "validation" else (te, groups_te)
        m = fit_scorecard(feature_list, X[tr], y[tr], cols)
        lg_ca, _ = model_logit(m, X[ca], cols)
        a, b, _sel = choose_calibration(lg_ca, y[ca])
        lg_s, _ = model_logit(m, X[idx], cols)
        p_s = sigmoid(a + b * lg_s)
        approve = p_s < POLICY_PD
        gm = group_metrics(p_s, y[idx], approve, groups)
        return m, (a, b), lg_ca, lg_s, p_s, approve, gm

    # ---- 1. base model (validation split) -------------------------------------
    m0, cal0, *_rest = evaluate(BASE, "validation")
    base_auc = float(roc_auc_score(y[va], _rest[2]))
    base_summary = summarise(_rest[4], zone_pair(_rest[4]))

    # ---- 2. candidate-feature gate ---------------------------------------------
    gate_log = []
    accepted = []
    for c in CANDIDATES:
        mc, calc, _, _, p_c, appr_c, gm_c = evaluate(BASE + accepted + [c], "validation")
        auc_c = float(roc_auc_score(y[va], p_c))
        sm = summarise(gm_c, zone_pair(gm_c))
        worst_eod_base = max(abs(v["eod"]) for v in base_summary.values())
        worst_eod_c = max(abs(v["eod"]) for v in sm.values())
        worst_air_c = min(v["air"] for v in sm.values() if v["air"] is not None)
        gain = auc_c - base_auc
        ok_fair, msgs = passes(sm)
        decision = gain >= CAND_MIN_AUC_GAIN and ok_fair and (worst_eod_c - worst_eod_base) <= CAND_MAX_EOD_WORSEN
        gate_log.append({
            "feature": c, "label": FEATURE_META[c]["label"], "auc_with": round(auc_c, 4), "auc_without": round(base_auc, 4),
            "auc_gain": round(gain, 4), "worst_eod_with": round(worst_eod_c, 4), "worst_eod_without": round(worst_eod_base, 4),
            "worst_air_with": worst_air_c, "fairness_gate_msgs": msgs,
            "decision": "accepted" if decision else "rejected",
            "reason": ("adds predictive value without harming fairness" if decision else "; ".join(
                [r_ for r_ in (f"AUC gain {gain:+.4f} below {CAND_MIN_AUC_GAIN}" if gain < CAND_MIN_AUC_GAIN else "",
                               f"widens opportunity gap (worst |EOD| {worst_eod_base:.3f} → {worst_eod_c:.3f})"
                               if (worst_eod_c - worst_eod_base) > CAND_MAX_EOD_WORSEN else "",
                               "; ".join(msgs)) if r_])),
        })
        if decision:
            accepted.append(c)

    # ---- 2b. proxy gate: a weak feature that mostly encodes group membership goes --
    final_feats = BASE + accepted
    m_tmp = fit_scorecard(final_feats, X[tr], y[tr], cols)
    for f in list(m_tmp["features"]):
        x = X[tr][:, cols[f]]
        pa = max(max(roc_auc_score(groups_all[g][tr], x), 1 - roc_auc_score(groups_all[g][tr], x)) for g in ("female", "rural"))
        iv = m_tmp["tables"][f]["iv"]
        if pa > PROXY_AUC and iv < PROXY_MIN_IV:
            final_feats = [x_ for x_ in final_feats if x_ != f]
            gate_log.append({"feature": f, "label": FEATURE_META[f]["label"], "decision": "removed",
                             "reason": f"proxy for a protected group (AUC {pa:.2f} > {PROXY_AUC}) with weak signal (IV {iv:.3f} < {PROXY_MIN_IV})",
                             "proxy_auc": round(float(pa), 3), "iv": round(float(iv), 4)})
    # ---- final model: the test split is used here for the first and only time --
    m, (a, b), lg_ca, lg_te, p_te, approve, gm = evaluate(final_feats, "test")
    cal_choice = choose_calibration(lg_ca, y[ca])[2]
    gated_pairs = zone_pair(gm)
    summary = summarise(gm, gated_pairs)
    fair_ok, fair_msgs = passes(summary)
    auc = float(roc_auc_score(y[te], p_te))
    pr_auc = float(average_precision(y[te], p_te))
    ll = float(log_loss(y[te], p_te))
    # 95% bootstrap confidence intervals on the test split
    ci_rng = np.random.default_rng(seed + 99)
    yt = y[te]
    boot = {"auc": [], "brier": [], "ece": [], "pr_auc": []}
    pair_boot = {f"{a_}_vs_{b_}": {"air": [], "eod": []} for a_, b_ in gated_pairs}
    gnames = sorted({g for pr in gated_pairs for g in pr})
    for _ in range(200):
        ix = ci_rng.integers(0, len(te), len(te))
        boot["auc"].append(roc_auc_score(yt[ix], p_te[ix]))
        boot["brier"].append(brier_score_loss(yt[ix], p_te[ix]))
        boot["ece"].append(ece(p_te[ix], yt[ix])[0])
        boot["pr_auc"].append(average_precision(yt[ix], p_te[ix]))
        gb = group_metrics(p_te[ix], yt[ix], approve[ix], {g: groups_te[g][ix] for g in gnames})
        for k_, v_ in summarise(gb, gated_pairs).items():
            pair_boot[k_]["air"].append(v_["air"])
            pair_boot[k_]["eod"].append(v_["eod"])
    q = lambda v: [round(float(np.quantile(v, 0.025)), 4), round(float(np.quantile(v, 0.975)), 4)]
    # A gate failure is re-measured on an independent fresh draw from the generator (possible only because the
    # data are synthetic). The release decision stays BLOCKED either way; this records the investigation.
    replication = None
    if not fair_ok:
        d2 = synth.generate(20000, seed + 1000)
        lg2, _ = model_logit(m, d2["X"], cols)
        p2 = sigmoid(a + b * lg2)
        g2 = {"female": d2["female"], "male": ~d2["female"], "rural": d2["rural"], "urban": ~d2["rural"],
              "rural_female": d2["rural"] & d2["female"], "urban_male": ~d2["rural"] & ~d2["female"],
              **{f"zone_{z}": d2["zone"] == i for i, z in enumerate(synth.ZONES)},
              **{f"social_{s_}": d2["social"] == i for i, s_ in enumerate(["general", "obc", "sc", "st"])}}
        gm2 = group_metrics(p2, d2["y"], p2 < POLICY_PD, g2)
        failed = [pr for pr in gated_pairs if any(msg.startswith(f"{pr[0]}_vs_{pr[1]}") for msg in fair_msgs)]
        replication = {"fresh_draw_n": 20000, "seed": seed + 1000,
                       "pairs": {f"{x}_vs_{y_}": {**summarise(gm2, [(x, y_)])[f"{x}_vs_{y_}"],
                                                  "n": [gm2[x]["n"], gm2[y_]["n"]]} for x, y_ in failed}}
    ci95 = {k: q(v) for k, v in boot.items()}
    for k_, v_ in pair_boot.items():
        if k_ in summary and v_["eod"]:
            summary[k_]["air_ci95"] = q(v_["air"])
            summary[k_]["eod_ci95"] = q(v_["eod"])
    ks = _ks(p_te, y[te])
    brier = float(brier_score_loss(y[te], p_te))
    ece_cal, curve = ece(p_te, y[te])
    p_raw = sigmoid(lg_te)
    ece_raw, curve_raw = ece(p_raw, y[te])
    iso = Isotonic().fit(sigmoid(lg_ca), y[ca])
    ece_iso, _ = ece(iso.predict(p_raw), y[te])
    curves_by_group = {g: ece(p_te[groups_te[g]], y[te][groups_te[g]], 8)[1] for g in ("female", "male", "rural", "urban")}

    # ---- 3. challenger: gradient boosting on raw features (accuracy ceiling) ---
    gbm = GBM().fit(X[tr][:, [cols[f] for f in final_feats]], y[tr])
    auc_gbm = float(roc_auc_score(y[te], gbm.predict_proba(X[te][:, [cols[f] for f in final_feats]])))

    # ---- 4. traditional document-based policy --------------------------------
    trad = d["has_itr"] & d["has_collateral"] & (d["vintage"] >= 2) & d["bureau_ok"]
    trad_te = trad[te]
    gm_trad = group_metrics(p_te, y[te], trad_te, groups_te)
    summary_trad = summarise(gm_trad, pairs)

    # ---- 5. proxy audit: can a single feature predict gender / rural? ----------
    proxy = []
    for f in final_feats + [c for c in CANDIDATES if c not in final_feats]:
        x = X[te][:, cols[f]]
        row = {"feature": f, "label": FEATURE_META[f]["label"], "in_model": f in m["features"],
               "dropped_reason": None if f in m["features"] else ("rejected by fairness/accuracy gate" if f in CANDIDATES
                                                                  else "weak or unstable signal (IV / sign check)")}
        for g in ("female", "rural"):
            au = roc_auc_score(groups_te[g], x)
            row[f"auc_{g}"] = round(float(max(au, 1 - au)), 3)
        row["flag"] = max(row["auc_female"], row["auc_rural"]) > 0.6
        proxy.append(row)

    # ---- 6. bootstrap ensemble for uncertainty -------------------------------
    W_tr = np.column_stack([woe_transform(X[tr][:, cols[n]], m["tables"][n]["edges"], m["tables"][n]["woe"]) for n in m["features"]])
    boots = []
    for k in range(25):
        idx = rng.integers(0, len(tr), len(tr))
        lr = LogReg(C=1.0).fit(W_tr[idx], y[tr][idx])
        boots.append({"intercept": float(lr.intercept_), "coefs": [float(c) for c in lr.coef_]})

    # ---- 7. persist ----------------------------------------------------------
    k = len(m["features"])
    feats_out = []
    for j, n_ in enumerate(m["features"]):
        t = m["tables"][n_]
        pts = [-(m["coefs"][j] * w + m["intercept"] / k) * FACTOR + OFFSET / k for w in t["woe"]]
        feats_out.append({
            "name": n_, "label": FEATURE_META[n_]["label"], "direction": FEATURE_META[n_]["dir"],
            "edges": [float(e) for e in t["edges"]], "woe": [float(w) for w in t["woe"]],
            "points": [round(float(p), 2) for p in pts], "coef": float(m["coefs"][j]), "iv": round(float(t["iv"]), 4),
            "bin_counts": [int(c) for c in t["tot"]], "bin_bad_rate": [round(float(bb / max(tt, 1)), 4) for bb, tt in zip(t["bad"], t["tot"])],
        })
    version = f"saakh-scorecard-{date.today().isoformat()}-s{seed}"
    scorecard = {"version": version, "intercept": m["intercept"], "features": feats_out,
                 "calibration": {"method": cal_choice["method"], "a": a, "b": b, "selection": cal_choice}, "bootstrap": boots,
                 "policy_pd": POLICY_PD, "bands": BANDS}
    band_dist = {bn: int(((p_te >= (BANDS[i - 1][1] if i else 0)) & (p_te < ub)).sum()) for i, (bn, ub) in enumerate(BANDS)}
    good_te = y[te] == 0
    report = {
        "version": version, "trained_on": date.today().isoformat(), "train_seconds": round(time.time() - t0, 1),
        "target": "SIMULATED binary default label drawn from a hand-specified generator (risk/synth.py), not an observed "
                  "12-month 90+ DPD outcome. Outputs are a simulated risk estimate, not a validated probability of default.",
        "evaluation_protocol": "train 50% / validation 15% (candidate-feature and proxy gates) / calibration 15% (method "
                               "selection by 2-fold cross-fitting) / test 20% (final metrics, computed once). Random split "
                               "from one generator: no temporal or external validation is possible on synthetic data.",
        "data": {"n": int(n), "train": len(tr), "validation": len(va), "calibration": len(ca), "test": len(te),
                 "base_default_rate": round(float(y.mean()), 4), "synthetic": True,
                 "composition": {"female": round(float(d["female"].mean()), 3), "rural": round(float(d["rural"].mean()), 3),
                                 "thin_file": round(float((d["months"] < 9).mean()), 3)}},
        "features": [{"name": f["name"], "label": f["label"], "iv": f["iv"], "points_range": [min(f["points"]), max(f["points"])]}
                     for f in feats_out],
        "metrics": {"auc": round(auc, 4), "gini": round(2 * auc - 1, 4), "ks": round(ks, 4), "brier": round(brier, 4),
                    "pr_auc": round(pr_auc, 4), "log_loss": round(ll, 4), "ci95": ci95,
                    "ece_calibrated": round(ece_cal, 4), "ece_uncalibrated": round(ece_raw, 4),
                    "ece_isotonic": round(ece_iso, 4), "calibration_choice": cal_choice,
                    "auc_gbm_challenger": round(auc_gbm, 4),
                    "interpretability_cost_auc": round(auc_gbm - auc, 4), "band_distribution": band_dist},
        "reliability": {"overall": curve, "uncalibrated": curve_raw, "by_group": curves_by_group},
        "fairness": {"gates": {"air_min": GATE_AIR, "eod_max": GATE_EOD, "cal_gap_max": GATE_CAL},
                     "scope": "Gated pairs: " + ", ".join(f"{a_} vs {b_}" for a_, b_ in gated_pairs) +
                              ". Synthetic population where true risk is group-neutral by construction, favourable results "
                              "partly follow from that design; real-data subgroup analysis is required before any claim.",
                     "passed": fair_ok, "messages": fair_msgs,
                     "replication": replication,
                     "release_decision": ("passed all gates" if fair_ok else
                                          "BLOCKED, a fairness gate failed on the held-out test split. The rule fails closed: "
                                          "on real lender data this model would not be deployed until the gap is investigated. "
                                          "Here it is used for demonstration only."),
                     "groups": gm, "summary": summary,
                     "traditional_policy": {"rule": "ITR filed AND collateral AND ≥2 years vintage AND no bounces",
                                            "groups": gm_trad, "summary": summary_trad}},
        "access": {
            "saakh_approval_rate": round(float(approve.mean()), 4),
            "traditional_approval_rate": round(float(trad_te.mean()), 4),
            "saakh_default_rate_approved": round(float(y[te][approve].mean()), 4),
            "traditional_default_rate_approved": round(float(y[te][trad_te].mean()), 4) if trad_te.sum() else None,
            "saakh_good_borrowers_reached": round(float((approve & good_te).sum() / good_te.sum()), 4),
            "traditional_good_borrowers_reached": round(float((trad_te & good_te).sum() / good_te.sum()), 4),
        },
        "candidate_gate": gate_log,
        "gate_split": "validation",
        "proxy_audit": proxy,
    }
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "scorecard.json").write_text(json.dumps(scorecard, indent=1), encoding="utf-8")
    (ARTIFACTS / "model_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return report


def _ks(p, y):
    order = np.argsort(p)
    yb = y[order]
    cb = np.cumsum(yb) / max(yb.sum(), 1)
    cg = np.cumsum(1 - yb) / max((1 - yb).sum(), 1)
    return float(np.max(np.abs(cb - cg)))


if __name__ == "__main__":
    r = main()
    print(json.dumps({k: r[k] for k in ("metrics", "access", "candidate_gate")}, indent=1, ensure_ascii=False))
    print("fairness passed:", r["fairness"]["passed"], r["fairness"]["messages"])
    print(json.dumps(r["fairness"]["summary"], indent=1))
    print(json.dumps(r["fairness"]["traditional_policy"]["summary"], indent=1))
