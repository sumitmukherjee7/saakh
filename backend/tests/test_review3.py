"""Regression tests for the third external review."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from saakh import consent, store
from saakh.agent import runtime as R
from saakh.api.main import sweep_expired
from saakh.autopilot import drive
from saakh.facts import coerce, derive
from saakh.schemes import engine
from saakh.schemes.benefits import benefits


# ------------------------------------------------------------------ PMEGP negative list
def test_a_yes_declaration_always_beats_a_broad_activity_label():
    assert derive({"activity": "tailoring"})["in_negative_list"] is False
    assert derive({"activity": "tailoring", "negative_list_declared": "yes"})["in_negative_list"] is True
    assert "in_negative_list" not in derive({"activity": "tailoring", "negative_list_declared": "unsure"})
    assert "in_negative_list" not in derive({"activity": "dairy"})
    assert derive({"activity": "dairy", "negative_list_declared": "no"})["in_negative_list"] is False
    with pytest.raises(ValueError):
        coerce("negative_list_declared", True)  # old boolean form is no longer accepted


def test_pmegp_match_is_marked_provisional_pending_dic_check():
    f = dict(age=34, gender="female", area_type="rural", sector="manufacturing", activity="tailoring", ownership_type="individual",
             is_new_unit=True, project_cost=3_00_000, availed_other_govt_subsidy=False, availed_pmegp=False,
             family_member_availed_pmegp=False, education="8th")
    r = engine.evaluate_scheme("pmegp", {**f, "negative_list_declared": "unsure"})
    assert r["eligibility"] != "eligible"
    checks = " ".join(lc["text"]["en"] for lc in engine.evaluate_scheme("pmegp", f)["lender_checks"])
    assert "provisional" in checks and "negative list" in checks


# ------------------------------------------------------------------ SVANidhi tranche counts
def test_svanidhi_repayment_count_is_bounded_and_the_ladder_ends():
    for bad in (-1, 4, 10):
        with pytest.raises(ValueError):
            coerce("svanidhi_tranche_repaid", bad)
    amounts = {n: [b["amount"] for b in benefits("pm_svanidhi", {"svanidhi_tranche_repaid": n}) if b["amount"] and b["kind"] == "loan"] for n in range(4)}
    assert amounts[0] == [15_000] and amounts[1] == [25_000] and amounts[2] == [50_000] and amounts[3] == []
    assert any("no further" in b["label"]["en"] for b in benefits("pm_svanidhi", {"svanidhi_tranche_repaid": 3}))
    assert not any(b["amount"] and b["kind"] == "loan" for b in benefits("pm_svanidhi", {"svanidhi_tranche_repaid": -1}))  # defensive path


# ------------------------------------------------------------------ revocation scrubs history
def _visible_text(c):
    return json.dumps({"m": c["messages"], "t": c["trace"], "f": c["facts"], "fm": c["fact_meta"]}, ensure_ascii=False)


def test_revoking_the_statement_removes_cards_trace_and_derived_facts():
    c = drive(R.new_case("lakshmamma", "en"), stop_at={"choose_offer"})
    inflow = f"{round(sum(c['analysis']['monthly']['biz_in']) / len(c['analysis']['monthly']['biz_in'])):,}"
    assert c["facts"].get("annual_turnover") and any((m.get("card") or {}).get("type") == "insights" for m in c["messages"])
    c = R.revoke(c, consent.active(c["id"], "bank_statement")["consentId"])
    types = [(m.get("card") or {}).get("type") for m in c["messages"]]
    assert "insights" not in types and "offers" not in types and "redacted" in types
    assert "annual_turnover" not in c["facts"] and "owns_milch_animals" not in c["facts"]
    assert not any(t.get("name") == "analyze_cashflow" and "inflow" in (t.get("summary") or "") for t in c["trace"])
    assert inflow not in _visible_text(R.public_case(c))


def test_audit_chain_never_holds_personal_or_financial_tool_summaries():
    c = drive(R.new_case("lakshmamma", "en"), stop_at={"choose_offer"})
    log = store.audit_log(c["id"])
    for name in ("fetch_ekyc", "analyze_cashflow", "fetch_bank_statement", "score_and_structure"):
        e = next(e for e in log if e["action"] == f"tool.{name}")
        assert "summary" not in e["payload"] and len(e["payload"]["summary_sha256"]) == 64
    assert "Lakshmamma" not in json.dumps([e["payload"] for e in log], ensure_ascii=False)
    assert store.verify_chain(c["id"])["ok"]


def test_revoking_ekyc_redacts_explanations_and_corrections_derived_from_it():
    c = drive(R.new_case("sunita", "en"), stop_at={"question"})
    c = R.handle(c, {"type": "message", "text": "Why not PMEGP?"})
    assert any((m.get("card") or {}).get("type") == "explanation" for m in c["messages"])
    name = c["facts"]["name"]
    c = R.revoke(c, consent.active(c["id"], "ekyc")["consentId"])
    assert not any((m.get("card") or {}).get("type") == "explanation" for m in c["messages"])
    trace = json.dumps(c["trace"], ensure_ascii=False)
    assert name not in trace and "name" not in c["facts"]


# ------------------------------------------------------------------ background expiry
def test_expiry_sweep_runs_without_anyone_opening_the_case():
    c = drive(R.new_case("lakshmamma", "en"), stop_at={"choose_offer"})
    art = consent.active(c["id"], "bank_statement")
    art["consentExpiry"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
    store.put_consent(art["consentId"], c["id"], "bank_statement", "ACTIVE", art)
    assert c["id"] in consent.due_case_ids()
    assert c["id"] in sweep_expired()  # what the API's background task (and `python -m saakh.sweep`) runs
    after = store.load_case(c["id"])
    assert after["analysis"] is None and "annual_turnover" not in after["facts"]
    assert store.get_consent(art["consentId"])["status"] == "EXPIRED"
    assert c["id"] not in consent.due_case_ids()


# ------------------------------------------------------------------ signing-key rotation
def test_artefacts_signed_with_a_previous_key_still_verify(monkeypatch):
    art = consent.request("C-ROTATE", "ekyc", "x@saakh-aa")
    old = consent.SECRET
    monkeypatch.setattr(consent, "SECRET", b"a-new-key-after-rotation")
    monkeypatch.setattr(consent, "_VERIFY_SECRETS", [b"a-new-key-after-rotation", old])
    assert consent.verify(art["consentId"])
    monkeypatch.setattr(consent, "_VERIFY_SECRETS", [b"a-new-key-after-rotation"])
    assert not consent.verify(art["consentId"])  # once the old key is retired, its artefacts stop verifying
