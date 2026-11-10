"""Regression tests for the fourth external review."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from saakh import consent, integrations, store, uploads
from saakh.agent import runtime as R
from saakh.agent.tools import call
from saakh.api import main as api
from saakh.autopilot import ACTOR, drive
from saakh.data.personas import statement

BACKEND = Path(__file__).resolve().parents[1]


def _rid():
    import uuid
    return uuid.uuid4().hex


def LH(lender_id):
    return {"X-Lender-Key": "demo-" + lender_id}


# ------------------------------------------------------------------ PMEGP provisional status reaches every surface
def test_pmegp_offer_is_provisional_in_results_offers_and_the_approved_package():
    c = drive(R.new_case("shg", "en"), stop_at={"approval"})
    pm = next(r for r in c["schemes"] if r["id"] == "pmegp")
    assert pm["eligibility"] == "eligible" and [p["id"] for p in pm["provisional"]] == ["pmegp.negative_list"]
    assert "DIC" in pm["provisional"][0]["by"]["en"]
    off = next(o for o in c["offers"] if o["scheme_id"] == "pmegp")
    assert off["provisional"], "an unverified activity must not produce an unqualified offer"
    if c["selected_offer"]["scheme_id"] == "pmegp":
        assert c["application"]["package"]["offer"]["provisional"]
    offers_card = next(m["card"] for m in c["messages"] if (m.get("card") or {}).get("type") == "offers")
    assert next(o for o in offers_card["offers"] if o["scheme_id"] == "pmegp")["provisional"]  # what the UI renders


# ------------------------------------------------------------------ lender decision vs revocation
def test_a_revocation_during_a_lender_decision_cannot_restore_the_package(monkeypatch):
    c = drive(R.new_case("imran", "en"))
    aid, lid, cid = c["application"]["id"], c["application"]["lender"]["id"], c["id"]
    real = api._app_for

    def lookup_then_revoke(a_id, principal):
        a = real(a_id, principal)  # the lender's first lookup succeeds ...
        share = consent.active(cid, "share_with_lender", {"lender": lid})
        R.revoke(store.load_case(cid), share["consentId"])  # ... then the entrepreneur revokes
        return a  # stale copy, still holding the package

    monkeypatch.setattr(api, "_app_for", lookup_then_revoke)
    r = TestClient(api.app).post(f"/api/lender/applications/{aid}/decision", headers=LH(lid),
                                 json={"request_id": _rid(), "decision": "sanction", "amount": 10000})
    assert r.status_code == 409
    a = store.get_application(aid)
    assert a["status"] == "withdrawn" and a["package"] is None and a["decision"]["decision"] == "withdrawn"
    monkeypatch.setattr(api, "_app_for", real)
    listed = next(x for x in TestClient(api.app).get("/api/lender/applications", headers=LH(lid)).json() if x["id"] == aid)
    assert listed["redacted"] and listed["amount"] is None


def test_decision_write_is_a_compare_and_set_at_the_database():
    c = drive(R.new_case("imran", "en"))
    a = store.get_application(c["application"]["id"])
    stale = json.loads(json.dumps(a))
    R.revoke(store.load_case(c["id"]), consent.active(c["id"], "bank_statement")["consentId"])
    stale.update(status="sanctioned", decision={"decision": "sanction"})
    assert store.decide_application(stale, "submitted") is False  # another worker withdrew it first
    assert store.get_application(a["id"])["package"] is None


# ------------------------------------------------------------------ audit minimisation
def _payloads(cid):
    return json.dumps([e["payload"] for e in store.audit_log(cid)], ensure_ascii=False)


def test_audit_keeps_no_answer_values_correction_reasons_or_raw_errors(monkeypatch):
    c = drive(R.new_case("ramesh", "en"), stop_at={"approval"})
    c["pending"] = {"type": "question", "fact": "loan_amount_sought"}
    c = R.handle(c, {"type": "answer", "fact": "loan_amount_sought", "value": 765432}, actor=ACTOR)
    own = next(k for k, m in c["fact_meta"].items() if m["source"] == ACTOR and isinstance(c["facts"][k], bool))
    c = R.handle(c, {"type": "correct", "fact": own, "value": not c["facts"][own], "reason": "my cousin Ravi Kumar said so"},
                 actor=ACTOR)
    monkeypatch.setattr(integrations, "bureau", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("PAN ABCDE1234F not found")))
    with pytest.raises(RuntimeError):
        call(c, "fetch_bureau", c["trace"])
    text = _payloads(c["id"])
    for secret in ("765432", "Ravi Kumar", "ABCDE1234F"):
        assert secret not in text, secret
    err = [e for e in store.audit_log(c["id"]) if e["action"] == "tool.error"][-1]
    assert err["payload"]["error_type"] == "RuntimeError" and len(err["payload"]["error_sha256"]) == 64
    assert store.verify_chain(c["id"])["ok"]


# ------------------------------------------------------------------ statement provenance
def test_facts_from_an_uploaded_statement_are_labelled_as_such_and_purged_with_it():
    c = R.new_case("lakshmamma", "en")
    c = R.handle(c, {"type": "message", "text": "need 3 lakh for cows"})
    kinds = {a["consentId"]: a["kind"] for a in store.case_consents(c["id"])}
    c = R.handle(c, {"type": "consent", "decisions": {i: kinds[i] == "ekyc" for i in c["pending"]["ids"]}})
    fi = uploads.parse_statement_csv(uploads.statement_to_csv(statement("lakshmamma")))
    c = R.statement_uploaded(c, fi, "s.csv")
    assert c["fact_meta"]["annual_turnover"]["source"] == "statement_upload"
    assert not any(m["source"] in ("aa", "aa-inferred") for m in c["fact_meta"].values())
    c = R.revoke(c, consent.active(c["id"], "statement_upload")["consentId"])
    assert "annual_turnover" not in c["facts"]


# ------------------------------------------------------------------ cross-process lost updates
def test_a_stale_copy_cannot_overwrite_a_newer_save():
    c = R.new_case("sunita", "en")
    a, b = store.load_case(c["id"]), store.load_case(c["id"])
    a["lang"] = "hi"
    store.save_case(a)
    b["lang"] = "en"
    with pytest.raises(store.StaleCaseError):
        store.save_case(b)
    assert store.load_case(c["id"])["lang"] == "hi"


OTHER_WORKER = """
import sys
sys.path.insert(0, sys.argv[1])
from saakh import store
c = store.load_case(sys.argv[2])
c["lang"] = "hi"
store.save_case(c)
"""


def test_a_save_from_another_process_is_detected():
    c = R.new_case("sunita", "en")
    mine = store.load_case(c["id"])
    r = subprocess.run([sys.executable, "-c", OTHER_WORKER, str(BACKEND), c["id"]], env=dict(os.environ),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    mine["lang"] = "en"
    with pytest.raises(store.StaleCaseError):
        store.save_case(mine)
    assert store.load_case(c["id"])["lang"] == "hi"


def test_api_reports_a_concurrent_change_as_409(monkeypatch):
    cl = TestClient(api.app)
    r = cl.post("/api/cases", json={"persona": "sunita", "lang": "en", "mode": "self"}).json()
    h = {"X-Case-Token": r["case_token"]}

    def boom(case, ev, actor=None):
        raise store.StaleCaseError("changed")

    monkeypatch.setattr(R, "handle", boom)
    assert cl.post(f"/api/cases/{r['id']}/events", headers=h, json={"type": "message", "text": "hi"}).status_code == 409
