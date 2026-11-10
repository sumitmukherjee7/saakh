import json

import numpy as np
import pytest

from saakh.cashflow.analyze import analyse, categorise, implied_rate
from saakh.cashflow.sizing import apr, structure
from saakh.data.personas import PERSONAS, statement
from saakh.risk import scorecard
from saakh.risk.ml import GBM, Isotonic, LogReg, auc
from saakh.util import annuity_emi, inr


def _a(pid):
    p = PERSONAS[pid]
    return analyse(statement(pid), p.get("informal_principal"), p["answers"]["activity"])


@pytest.mark.parametrize("nar,typ,cat", [
    ("UPI/CR/1/PRIYA VERMA/SBIN/priya1@oksbi/Payment", "CREDIT", "sales_upi"),
    ("NEFT/CR/2/KALYANI AUTO COMPONENTS PVT LTD/INV PAYMENT", "CREDIT", "sales_b2b"),
    ("NEFT/CR/3/MANDYA DIST CO OP MILK PRODUCERS UNION/MILK BILL", "CREDIT", "sales_coop"),
    ("NEFT/CR/4/JSLPS REVOLVING FUND", "CREDIT", "grant"),
    ("ACH/DR/BAJAJ FINANCE/EMI 123456", "DEBIT", "emi"),
    ("BBPS/DR/5/UPPCL ELECTRICITY BILL", "DEBIT", "utilities"),
    ("IMPS/P2A/6/SELF TRANSFER/drawings", "DEBIT", "transfer_out"),
])
def test_categorise(nar, typ, cat):
    assert categorise({"narration": nar, "type": typ, "mode": "UPI"}) == cat


def test_informal_loan_detected_without_false_positives():
    a = _a("sunita")
    cps = [i["counterparty"] for i in a["informal_loans"]]
    assert cps == ["RAMKUMAR YADAV"]  # weekly ₹1,200, and NOT the monthly phone recharge
    assert 0.4 < a["informal_loans"][0]["implied_annual_rate"] < 0.8
    assert _a("ramesh")["informal_loans"] == []


def test_implied_rate():
    r = implied_rate(50000, 1200, 52, 52)
    assert 0.4 < r < 0.8
    assert implied_rate(50000, 500, 52, 52) is None  # pays back less than principal


def test_deseasonalised_trend_not_fooled_by_season():
    # Sunita's ledger grows ~1.2%/month; raw Nov→Oct slope is negative because Nov is peak season.
    assert _a("sunita")["features"]["inflow_trend"] > 0
    assert _a("mohan")["features"]["inflow_trend"] < -0.15


def test_derived_facts_with_evidence():
    a = _a("ramesh")
    assert a["derived_facts"]["has_b2b_buyers"] is True and "business buyers" in a["evidence"]["has_b2b_buyers"]
    assert "owns_milch_animals" in _a("lakshmamma")["evidence"]
    assert _a("shg")["flags"][0]["fact"] == "availed_other_govt_subsidy"


def test_scorecard_points_are_monotone_in_declared_direction():
    sc = scorecard.load()
    for f in sc["features"]:
        pts = f["points"]
        if f["direction"] > 0:
            assert pts == sorted(pts), f["name"]
        else:
            assert pts == sorted(pts, reverse=True), f["name"]


def test_protected_attributes_are_not_model_inputs():
    names = {f["name"] for f in scorecard.load()["features"]}
    assert not names & {"gender", "female", "rural", "area_type", "social_category", "zone", "state", "district"}


def test_pd_responds_to_bounces_and_explains_itself():
    base = _a("sunita")["features"] | {"proposed_dsr": 0.05}
    s0 = scorecard.score(base)
    s1 = scorecard.score(base | {"bounces_12m": 6})
    assert s1["pd"] > s0["pd"]
    assert any(r["feature"] == "bounces_12m" for r in s1["reason_codes"])
    assert s0["pd_low"] <= s0["pd"] <= s0["pd_high"]
    assert s0["output_kind"] == "simulated_risk_estimate"


def test_model_report_is_honest_about_protocol_and_gates():
    rep = json.loads((scorecard.ARTIFACTS / "model_report.json").read_text(encoding="utf-8"))
    assert "SIMULATED" in rep["target"] and rep["gate_split"] == "validation"
    assert rep["data"]["validation"] > 0 and rep["data"]["test"] > 0
    assert rep["metrics"]["ece_calibrated"] < 0.02 and rep["metrics"]["auc"] > 0.7
    lo, hi = rep["metrics"]["ci95"]["auc"]
    assert lo < rep["metrics"]["auc"] < hi
    assert "pr_auc" in rep["metrics"] and "log_loss" in rep["metrics"]
    f = rep["fairness"]
    assert "social_st vs social_general" in f["scope"]
    if not f["passed"]:  # a failed gate must be investigated and must block release
        assert f["replication"] and f["release_decision"].startswith("BLOCKED")
    assert rep["access"]["saakh_good_borrowers_reached"] > rep["access"]["traditional_good_borrowers_reached"]
    assert {g["feature"]: g["decision"] for g in rep["candidate_gate"]}["log_avg_inflow"] == "rejected"


def test_season_matched_schedule_reduces_stress_with_same_pv():
    st = structure(_a("lakshmamma"), "pmmy", 300000, "female", uplift=0.45)
    assert st["seasonal"]["stress_months"] < st["flat"]["stress_months"]
    r = st["rate"] / 12
    pv = lambda xs: sum(x / (1 + r) ** (t + 1) for t, x in enumerate(xs))
    assert pv(st["seasonal"]["instalments"]) == pytest.approx(st["recommended"], rel=0.01)
    assert st["binding_constraint"] == "affordability_seasonal"


def test_stressed_business_gets_not_now():
    st = structure(_a("mohan"), "pmmy", 300000, "male")
    assert st["recommended"] == 0 and st["risk_at_request"]["band"] in ("D", "E")


def test_apr_equals_rate_without_fees():
    emi = annuity_emi(100000, 0.12, 24)
    assert apr(100000, [emi] * 24) == pytest.approx(0.12, abs=1e-3)
    assert apr(99000, [emi] * 24) > 0.12


def test_ml_primitives():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(3000, 3))
    y = (rng.random(3000) < 1 / (1 + np.exp(-(X[:, 0] - 1)))).astype(int)
    lr = LogReg(C=10).fit(X, y)
    assert lr.coef_[0] > 0.7 and abs(lr.coef_[1]) < 0.2
    assert auc(y, lr.predict_proba(X)) > 0.7
    assert auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
    iso = Isotonic().fit(np.array([1, 2, 3, 4]), np.array([0, 1, 0, 1]))
    assert list(iso.predict(np.array([1, 4]))) == [0.0, 1.0]
    g = GBM(n_iter=30).fit(X, y)
    assert auc(y, g.predict_proba(X)) > 0.7


def test_inr_format():
    assert inr(150000) == "₹1,50,000" and inr(12345678) == "₹1,23,45,678" and inr(250000, short=True) == "₹2.5 lakh"


def test_csv_statement_parser_round_trip_and_rejects_bad_input():
    from saakh.uploads import UploadError, parse_statement_csv, statement_to_csv
    fi = parse_statement_csv(statement_to_csv(statement("sunita")))
    a = analyse(fi, None, "tailoring")
    assert a["informal_loans"][0]["counterparty"] == "RAMKUMAR YADAV"
    with pytest.raises(UploadError):
        parse_statement_csv("date,narration,debit,credit,balance" + chr(10) + "2026-01-01,x,abc,,1" + chr(10))
    with pytest.raises(UploadError):
        parse_statement_csv("when,what" + chr(10) + "1,2" + chr(10))
