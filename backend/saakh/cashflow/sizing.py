"""Loan structuring: affordability-based sizing, season-matched repayment and
a Key-Facts-Statement style cost disclosure (APR incl. fees).

Principles
* Size the loan from *observed* disposable cash flow, not from a stated need.
* Check the proposed EMI through the risk model (proposed_dsr feature) so the
  recommended amount keeps PD inside policy.
* Offer a repayment schedule shaped like the business's own seasons: the same
  present value as a flat EMI, but small instalments in lean months.
* Disclose all-in cost as an APR (annualised IRR of every cash flow, fees
  included), RBI's KFS requirement for MSME term loans (RBI/2024-25/18).
"""
from __future__ import annotations

import numpy as np

from ..risk.scorecard import POLICY_PD, band_of, score
from ..util import annuity_emi, annuity_pv, inr

# Indicative terms (assumptions, shown as "indicative, lender's KFS is binding")
TERMS = {
    "pmmy": {"rate": 0.11, "tenure": 36, "fee": 0.005, "fee_waived_below": 50_000},
    "pm_vishwakarma": {"rate": 0.05, "tenure": 18, "fee": 0.0},
    "kcc_ah": {"rate": 0.07, "tenure": 12, "fee": 0.0},
    "day_nrlm": {"rate": 0.07, "tenure": 36, "fee": 0.0},
    "pm_svanidhi": {"rate": 0.07, "tenure": 12, "fee": 0.0},
    "pmegp": {"rate": 0.11, "tenure": 60, "fee": 0.005},
    "pmegp_upgrade": {"rate": 0.11, "tenure": 60, "fee": 0.005},
    "standup_india": {"rate": 0.11, "tenure": 84, "fee": 0.005},
    "default": {"rate": 0.12, "tenure": 36, "fee": 0.01},
}
# Scheme ceilings on the loan itself. KCC and SHG limits are assessed by the bank,
# so no scheme cap is applied there (₹2 lakh / ₹20 lakh are collateral-free thresholds).
CAPS = {"pmmy": 20_00_000, "pm_vishwakarma": 1_00_000, "pm_svanidhi": 15_000, "pmegp": 50_00_000,
        "pmegp_upgrade": 1_00_00_000}
ALPHA = {"A": 0.6, "B": 0.55, "C": 0.45, "D": 0.35, "E": 0.25}  # share of disposable income an EMI may take
STRESS = 0.6
UPLIFT_HAIRCUT = 0.5  # only half of the projected extra margin is counted towards repayment  # an instalment above 60% of that month's disposable income = stressed month


def disposable(monthly: dict, refinance_informal: bool = False) -> np.ndarray:
    bi = np.asarray(monthly["biz_in"])
    bo = np.asarray(monthly["biz_out"])
    ho = np.asarray(monthly["hh_out"])
    tr = np.asarray(monthly.get("transfers_out") or np.zeros_like(bi))
    em = np.asarray(monthly["emi_out"])
    inf = np.asarray(monthly["informal_out"])
    consumption = ho - tr  # owner drawings/self-transfers are discretionary, not consumption
    d = bi - bo - consumption - em - (0 if refinance_informal else inf)
    return d


def _by_calendar(months: list[str], values: np.ndarray) -> np.ndarray:
    """Average a series into 12 calendar-month buckets (Jan..Dec)."""
    acc, cnt = np.zeros(12), np.zeros(12)
    for mk, v in zip(months, values):
        k = int(mk[5:7]) - 1
        acc[k] += v
        cnt[k] += 1
    prof = np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan)
    if np.isnan(prof).any():
        prof = np.where(np.isnan(prof), np.nanmean(prof), prof)
    return prof


def schedule(principal: float, rate: float, tenure: int, start_month: int, weights: np.ndarray | None) -> list[float]:
    """Instalments with PV = principal. weights: 12 calendar-month weights (None = flat)."""
    if weights is None:
        e = annuity_emi(principal, rate, tenure)
        return [round(e, 0)] * tenure
    r = rate / 12
    w = np.array([weights[(start_month - 1 + t) % 12] for t in range(tenure)])
    disc = np.array([(1 + r) ** -(t + 1) for t in range(tenure)])
    k = principal / float((w * disc).sum())
    return [round(float(k * x), 0) for x in w]


def apr(net_disbursed: float, payments: list[float]) -> float:
    lo, hi = 0.0, 0.2
    for _ in range(200):
        r = (lo + hi) / 2
        pv = sum(p / (1 + r) ** (t + 1) for t, p in enumerate(payments))
        if pv > net_disbursed:
            lo = r
        else:
            hi = r
    return round(lo * 12, 4)


def structure(analysis: dict, scheme_id: str | None, requested: float, gender: str | None = None,
              informal_outstanding: float | None = None, with_cgtmse: bool = False, start_month: int = 12,
              uplift: float = 0.0) -> dict:
    """uplift: projected % increase in business income from the financed asset
    (from the project report); counted at a 50% haircut, net of input costs."""
    monthly = analysis["monthly"]
    months = monthly["months"]
    feats = dict(analysis["features"])
    avg_in = max(float(np.mean(monthly["biz_in"])), 1.0)
    terms = TERMS.get(scheme_id or "default", TERMS["default"])
    rate, tenure = terms["rate"], terms["tenure"]
    cap = CAPS.get(scheme_id or "", 1e12)
    refinance = bool(analysis.get("informal_loans")) and bool(informal_outstanding)
    need = requested + (informal_outstanding if refinance else 0)

    disp = disposable(monthly, refinance_informal=refinance)
    bi_arr = np.asarray(monthly["biz_in"])
    input_ratio = float(np.sum(monthly["biz_out"]) / max(bi_arr.sum(), 1))
    incremental = uplift * bi_arr * max(0.0, 1 - input_ratio) * UPLIFT_HAIRCUT
    disp = disp + incremental
    prof = _by_calendar(months, disp)
    floor = max(0.15 * float(np.mean(prof)), 1.0)
    w = np.maximum(prof, floor)
    w = w / w.mean()

    def pd_for(amount: float) -> dict:
        f = dict(feats)
        f["proposed_dsr"] = annuity_emi(amount, rate, tenure) / avg_in
        if refinance:  # informal repayments stop once refinanced
            f["informal_share"] = 0.0
            f["debt_service_ratio"] = max(0.0, f["debt_service_ratio"] - analysis["features"]["informal_share"])
        return score(f)

    s_req = pd_for(need)
    alpha = ALPHA[s_req["band"]]
    disp_mean = float(np.mean(disp))
    flat_cap_emi = max(alpha * float(np.median(disp)), 0.0)
    max_flat = annuity_pv(flat_cap_emi, rate, tenure) if flat_cap_emi > 0 else 0.0
    # seasonal capacity: instalment_t = alpha * expected disposable in that calendar month
    r = rate / 12
    seas_inst = [alpha * max(prof[(start_month - 1 + t) % 12], 0.0) for t in range(tenure)]
    max_seasonal = sum(x / (1 + r) ** (t + 1) for t, x in enumerate(seas_inst))
    # PD-constrained maximum (binary search on amount)
    lo, hi = 0.0, max(need, 1.0) * 1.5
    if pd_for(hi)["pd"] < POLICY_PD:
        max_pd = hi
    else:
        for _ in range(40):
            mid = (lo + hi) / 2
            if pd_for(mid)["pd"] < POLICY_PD:
                lo = mid
            else:
                hi = mid
        max_pd = lo
    limits = {"requested": need, "scheme_cap": cap, "affordability_seasonal": max_seasonal, "risk_policy": max_pd}
    binding = min(limits, key=limits.get)
    rec = max(0.0, min(limits.values()))
    rec = float(int(rec // 5000 * 5000)) if rec >= 10000 else float(int(rec // 1000 * 1000))
    s_rec = pd_for(rec) if rec > 0 else s_req

    flat = schedule(rec, rate, tenure, start_month, None) if rec > 0 else []
    seas = schedule(rec, rate, tenure, start_month, w) if rec > 0 else []
    exp_disp = [float(prof[(start_month - 1 + t) % 12]) for t in range(tenure)]

    def stress(inst):
        return int(sum(1 for i, dsp in zip(inst, exp_disp) if dsp <= 0 or i > STRESS * dsp))

    fee_rate = terms["fee"] if rec >= terms.get("fee_waived_below", 0) else 0.0
    proc_fee = round(rec * fee_rate)
    from ..schemes.benefits import cgtmse_fee_rate
    cg_fee = round(rec * cgtmse_fee_rate(rec, gender == "female") / 100) if with_cgtmse else 0
    net = rec - proc_fee - cg_fee
    kfs = None
    if rec > 0:
        kfs = {
            "loan_amount": rec, "interest_rate": rate, "tenure_months": tenure,
            "processing_fee": proc_fee, "guarantee_fee_year1": cg_fee, "net_disbursed": net,
            "total_interest_flat": round(sum(flat) - rec), "total_interest_seasonal": round(sum(seas) - rec),
            "apr_flat": apr(net, flat), "apr_seasonal": apr(net, seas),
            "indicative": True,
            "note": {"en": "Indicative terms for planning. The lender's Key Facts Statement (KFS) is binding.",
                     "hi": "योजना हेतु सांकेतिक शर्तें। बैंक का मुख्य तथ्य विवरण (KFS) ही मान्य है।"},
        }
    savings = None
    if refinance:
        inf_year = sum(monthly["informal_out"]) * 12 / max(len(months), 1)
        savings = {"informal_outflow_year": round(inf_year), "informal_outstanding": informal_outstanding,
                   "note": {"en": f"Paying off the moneylender ({inr(informal_outstanding)}) stops ≈{inr(inf_year)}/year of informal repayments.",
                            "hi": f"साहूकार का ऋण ({inr(informal_outstanding)}) चुकाने से ≈{inr(inf_year)}/वर्ष का अनौपचारिक भुगतान बंद होगा।"}}
    why = {
        "requested": {"en": "Full amount you asked for fits within limits.", "hi": "आपकी माँगी पूरी राशि सीमा के भीतर है।"},
        "scheme_cap": {"en": f"Capped at the scheme limit ({inr(cap)}).", "hi": f"योजना सीमा ({inr(cap)}) तक सीमित।"},
        "affordability_seasonal": {"en": "Limited by what your cash flow can repay comfortably, even with season-matched instalments.",
                                   "hi": "आपकी नकदी प्रवाह से आराम से चुकाई जा सकने वाली राशि तक सीमित।"},
        "risk_policy": {"en": "Limited so that the repayment burden keeps risk within policy.",
                        "hi": "सीमित ताकि किस्त का बोझ जोखिम को नीति के भीतर रखे।"},
    }[binding]
    return {
        "scheme_id": scheme_id, "requested": requested, "refinance_informal": refinance, "need": need,
        "recommended": rec, "binding_constraint": binding, "why": why,
        "limits": {k: round(v) for k, v in limits.items() if v < 1e11},
        "alpha": alpha, "rate": rate, "tenure": tenure, "start_month": start_month,
        "risk_at_request": {k: s_req[k] for k in ("pd", "band")},
        "risk_at_recommended": {k: s_rec[k] for k in ("pd", "pd_low", "pd_high", "band")},
        "flat": {"instalments": flat, "stress_months": stress(flat) if flat else None},
        "seasonal": {"instalments": seas, "stress_months": stress(seas) if seas else None,
                     "weights": [round(float(x), 2) for x in w]},
        "expected_disposable": [round(x) for x in exp_disp],
        "disposable_mean": round(disp_mean), "kfs": kfs, "refinance": savings,
        "uplift": {"projected": uplift, "haircut": UPLIFT_HAIRCUT, "monthly_counted": round(float(np.mean(incremental)))},
        "dscr": round(float(np.mean(disp) * 12 / max(sum(flat[:12]) if flat else 1, 1)), 2) if flat else None,
    }
