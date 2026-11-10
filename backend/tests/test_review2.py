"""Regression tests for the second external review (each test pins one verified finding)."""
import hashlib
import os
import secrets
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from saakh import consent, integrations, store, uploads
from saakh.agent import runtime as R
from saakh.api.main import app
from saakh.autopilot import ACTOR, SAMPLE_PDF, drive
from saakh.data.personas import statement

BACKEND = Path(__file__).resolve().parents[1]
OTHER_PDF = SAMPLE_PDF.replace(b"200 100", b"300 150")


def _rid():
    import uuid
    return uuid.uuid4().hex


def LH(lender_id):
    return {"X-Lender-Key": "demo-" + lender_id}


def client():
    return TestClient(app)


def new_api_case(cl, persona="sunita", mode="self"):
    r = cl.post("/api/cases", json={"persona": persona, "lang": "en", "mode": mode}).json()
    return r["id"], {"X-Case-Token": r["case_token"]}, r


def _attached(c):
    return [d for d in c["application"]["package"]["documents"] if d["attachment"]]


# ------------------------------------------------------------------ answers & corrections
def test_answers_are_accepted_only_for_the_question_being_asked():
    c = drive(R.new_case("sunita", "en"), stop_at={"question"})
    asked = c["pending"]["fact"]
    other = "is_minority" if asked != "is_minority" else "is_pwd"
    with pytest.raises(ValueError, match="not the question"):
        R.handle(c, {"type": "answer", "fact": other, "value": True})
    assert other not in c["facts"] or c["fact_meta"][other]["source"] != "entrepreneur"


def test_correcting_a_sourced_fact_records_a_dispute_and_never_changes_the_decision_input():
    c = drive(R.new_case("ramesh", "en"), stop_at={"approval"})
    assert c["fact_meta"]["age"]["source"] == "ekyc" and c["fact_meta"]["is_defaulter"]["source"] == "bureau"
    old_age, h1 = c["facts"]["age"], c["application"]["hash"]
    schemes_before = [(r["id"], r["eligibility"]) for r in c["schemes"]]
    c = R.handle(c, {"type": "correct", "fact": "is_defaulter", "value": not c["facts"]["is_defaulter"],
                     "reason": "loan was settled"}, actor=ACTOR)
    c = R.handle(c, {"type": "correct", "fact": "age", "value": old_age + 1, "reason": "DigiLocker DOB is wrong"}, actor=ACTOR)
    assert c["facts"]["age"] == old_age and c["fact_meta"]["age"]["source"] == "ekyc"  # sourced value stays operative
    assert c["fact_meta"]["age"]["dispute"]["claimed"] == old_age + 1 and c["fact_meta"]["age"]["dispute"]["status"] == "open"
    assert [(r["id"], r["eligibility"]) for r in c["schemes"]] == schemes_before
    assert {d["fact"] for d in c["application"]["package"]["disputes"]} == {"age", "is_defaulter"}  # the lender sees it
    assert c["application"]["hash"] != h1 and c["approval"] is None and c["pending"]["type"] == "approval"
    assert sum(e["action"] == "fact.disputed" for e in store.audit_log(c["id"])) == 2


def test_correcting_the_entrepreneurs_own_answer_replaces_it_with_provenance():
    c = drive(R.new_case("ramesh", "en"), stop_at={"approval"})
    own = next(k for k, m in c["fact_meta"].items() if m["source"] == ACTOR and isinstance(c["facts"][k], bool))
    old = c["facts"][own]
    c = R.handle(c, {"type": "correct", "fact": own, "value": not old, "reason": "answered wrongly"}, actor=ACTOR)
    meta = c["fact_meta"][own]
    assert c["facts"][own] is (not old) and meta["corrected_from"] == {"value": old, "source": ACTOR}
    assert any(e["action"] == "fact.corrected" for e in store.audit_log(c["id"]))
    with pytest.raises(ValueError):
        R.handle(c, {"type": "correct", "fact": "in_negative_list", "value": False})  # derived facts are not editable


# ------------------------------------------------------------------ model release gate
def test_blocked_model_fails_closed_in_production(monkeypatch):
    monkeypatch.setattr(R, "PRODUCTION", True)
    monkeypatch.setattr(R, "release_status", lambda: {"status": "blocked", "reason": "fairness gate failed"})
    c = drive(R.new_case("ramesh", "en"))
    assert c["closed"] and not c["offers"] and c["score"] is None and not c["submission"]
    assert any(t.get("status") == "blocked" and "release gate" in t["name"] for t in c["trace"])


def test_demo_offers_carry_the_blocked_release_label():
    c = drive(R.new_case("ramesh", "en"), stop_at={"choose_offer"})
    assert c["offers"] and c["model_release"]["status"] == "blocked"  # the shipped report's ST gate fails


# ------------------------------------------------------------------ attachments bound to approval
def test_attachment_fingerprints_are_in_the_approved_package_and_replacing_one_voids_approval():
    c = drive(R.new_case("ramesh", "en"), stop_at={"approval"})
    att = _attached(c)
    assert att and all(len(d["attachment"]["sha256"]) == 64 for d in att)
    card = c["messages"][-1]["card"]
    assert card["type"] == "approval" and {a["doc"] for a in card["attachments"]} == {d["doc"] for d in att}
    h1, doc = c["application"]["hash"], att[0]["doc"]
    c["approval"] = {"hash": h1, "ts": store.now(), "by": "test"}
    meta = uploads.save_document(c["id"], doc, "new.pdf", OTHER_PDF)
    c = R.document_received(c, doc, meta, actor=ACTOR)
    assert c["approval"] is None and c["application"]["hash"] != h1
    assert c["pending"] == {"type": "approval", "hash": c["application"]["hash"]}
    assert next(d for d in c["application"]["package"]["documents"] if d["doc"] == doc)["attachment"]["sha256"] == meta["sha256"]


def test_lender_downloads_only_the_approved_bytes_and_access_is_audited():
    c = drive(R.new_case("ramesh", "en"))
    aid, lid = c["application"]["id"], c["application"]["lender"]["id"]
    d = _attached(c)[0]
    cl = client()
    url = f"/api/lender/applications/{aid}/documents/{d['doc']}"
    assert cl.get(url).status_code == 401
    r = cl.get(url, headers=LH(lid))
    assert r.status_code == 200 and hashlib.sha256(r.content).hexdigest() == d["attachment"]["sha256"]
    assert r.headers["x-content-sha256"] == d["attachment"]["sha256"]
    log = store.audit_log(c["id"])
    assert any(e["action"] == "lender.document_accessed" and e["actor"] == f"lender:{lid}" for e in log)
    detail = cl.get(f"/api/lender/applications/{aid}", headers=LH(lid)).json()["detail"]
    assert "uploads" not in detail and detail["attachments"][0]["sha256"]
    # tampering with the stored bytes is detected, not served
    f = next((uploads.UPLOAD_DIR / c["id"]).glob(f"{d['doc']}-*"))
    f.write_bytes(f.read_bytes() + b"x")
    assert cl.get(url, headers=LH(lid)).status_code in (409, 410)


def test_a_document_changed_after_submission_supersedes_the_lender_copy_until_re_approved():
    c = drive(R.new_case("ramesh", "en"))
    aid, lid, ref1 = c["application"]["id"], c["application"]["lender"]["id"], c["submission"]["los_ref"]
    doc = _attached(c)[0]["doc"]
    meta = uploads.save_document(c["id"], doc, "v2.pdf", OTHER_PDF)
    c = R.document_received(c, doc, meta, actor=ACTOR)
    assert store.get_application(aid)["superseded"] and c["pending"]["type"] == "approval"
    cl = client()
    assert cl.post(f"/api/lender/applications/{aid}/decision", headers=LH(lid), json={"request_id": _rid(), "decision": "query", "note": "rent agreement"}).status_code == 409
    c = drive(c)  # entrepreneur re-approves the changed file
    a = store.get_application(aid)
    assert not a.get("superseded") and a["hash"] == c["application"]["hash"] and c["submission"]["los_ref"] != ref1


# ------------------------------------------------------------------ lender isolation & completeness
def test_lenders_see_only_files_addressed_to_them():
    c = drive(R.new_case("imran", "en"))
    aid, lid = c["application"]["id"], c["application"]["lender"]["id"]
    other = next(l["id"] for l in integrations.LENDERS if l["id"] != lid)
    cl = client()
    assert aid in {a["id"] for a in cl.get("/api/lender/applications", headers=LH(lid)).json()}
    assert aid not in {a["id"] for a in cl.get("/api/lender/applications", headers=LH(other)).json()}
    for path in ("", "/memo.pdf", "/dpr.pdf"):
        assert cl.get(f"/api/lender/applications/{aid}{path}", headers=LH(other)).status_code == 404
    assert cl.post(f"/api/lender/applications/{aid}/decision", headers=LH(other), json={"request_id": _rid(), "decision": "query", "note": "rent agreement"}).status_code == 404
    assert cl.get("/api/lender/applications", headers={"X-Lender-Key": "branch-demo"}).status_code == 401  # old shared key gone


def test_items_scheduled_for_a_cafe_visit_are_pending_not_complete():
    c = drive(R.new_case("sunita", "en"))
    pkg = c["application"]["package"]["documents"]
    offline = [d["doc"] for d in pkg if d["scheduled_offline"]]
    assert offline == ["csc_registration"]  # PM Vishwakarma registration is done with the operator
    s = client().get("/api/lender/applications", headers=LH(c["application"]["lender"]["id"])).json()
    mine = next(a for a in s if a["id"] == c["application"]["id"])
    assert mine["complete"] is False and set(offline) <= set(mine["pending_items"])
    appr = next(m for m in c["messages"] if (m.get("card") or {}).get("type") == "approval")
    assert "complete" not in appr["text"]["en"] and "still to be done at a JanAI Café" in appr["text"]["en"]
    assert appr["card"]["pending_items"] == ["csc_registration"]
    sent = next(m for m in c["messages"] if (m.get("card") or {}).get("type") == "submitted")
    assert "complete file" not in sent["text"]["en"]


# ------------------------------------------------------------------ consent lifecycle
def _expire(case_id, kind):
    art = next(a for a in store.case_consents(case_id) if a["kind"] == kind and a["status"] == "ACTIVE")
    art["consentExpiry"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    store.put_consent(art["consentId"], case_id, kind, art["status"], art)
    return art["consentId"]


def test_expired_statement_consent_is_marked_and_its_data_purged_on_next_access():
    cl = client()
    cid, h, _ = new_api_case(cl, "lakshmamma")
    c = drive(store.load_case(cid), stop_at={"choose_offer"})
    assert c["analysis"]
    aid = _expire(cid, "bank_statement")
    got = cl.get(f"/api/cases/{cid}", headers=h).json()
    assert got["analysis"] is None and not got["data"].get("statement") and not got["offers"]
    assert store.get_consent(aid)["status"] == "EXPIRED"
    assert any(e["action"] == "consent.expired" for e in store.audit_log(cid))


def test_revoking_bureau_or_ekyc_deletes_what_came_under_it_and_withdraws_a_sent_file():
    c = drive(R.new_case("imran", "en"))
    aid = c["application"]["id"]
    assert any(m["source"] == "bureau" for m in c["fact_meta"].values())
    c = R.revoke(c, consent.active(c["id"], "bureau")["consentId"])
    assert not any(m["source"] == "bureau" for m in c["fact_meta"].values()) and "bureau" not in c["data"]
    assert store.get_application(aid)["status"] == "withdrawn" and c["closed"]
    c2 = drive(R.new_case("sunita", "en"), stop_at={"choose_offer"})
    c2 = R.revoke(c2, consent.active(c2["id"], "ekyc")["consentId"])
    assert not any(m["source"] == "ekyc" for m in c2["fact_meta"].values()) and c2["data"]["ekyc"]["purged"]


def test_assisted_statement_upload_needs_the_entrepreneurs_code():
    cl = client()
    cid, h, pub = new_api_case(cl, "lakshmamma", mode="assisted")
    c = cl.post(f"/api/cases/{cid}/events", headers=h, json={"type": "message", "text": "need 3 lakh for cows"}).json()
    kinds = {a["consentId"]: a["kind"] for a in store.case_consents(cid)}
    dec = {i: kinds[i] == "ekyc" for i in c["pending"]["ids"]}
    consent_code = c["demo_sms_otp"]
    c = cl.post(f"/api/cases/{cid}/events", headers=h, json={"type": "consent", "decisions": dec, "otp": consent_code}).json()
    assert c["pending"]["type"] == "fallback_statement" and c["demo_sms_purpose"] == "statement_upload"
    otp = c["demo_sms_otp"]
    body = {"filename": "s.csv", "csv_text": uploads.statement_to_csv(statement("lakshmamma")), "consent": True}
    for bad in (None, "000000" if otp != "000000" else "111111"):
        assert cl.post(f"/api/cases/{cid}/statement", headers=h, json={**body, "otp": bad}).status_code == 403
    assert store.get_statement(cid) is None and not consent.active(cid, "statement_upload")
    r = cl.post(f"/api/cases/{cid}/statement", headers=h, json={**body, "otp": otp})
    assert r.status_code == 200 and consent.active(cid, "statement_upload")


# ------------------------------------------------------------------ honest coverage
def test_short_uploaded_statement_is_labelled_with_its_real_coverage():
    cl = client()
    cid, h, _ = new_api_case(cl, "lakshmamma")
    c = cl.post(f"/api/cases/{cid}/events", headers=h, json={"type": "message", "text": "need 3 lakh for cows"}).json()
    kinds = {a["consentId"]: a["kind"] for a in store.case_consents(cid)}
    cl.post(f"/api/cases/{cid}/events", headers=h, json={"type": "consent", "decisions": {i: kinds[i] == "ekyc" for i in c["pending"]["ids"]}})
    lines = uploads.statement_to_csv(statement("lakshmamma")).splitlines()
    cutoff = sorted({ln.split(",")[0][:7] for ln in lines[1:]})[-6]
    short = "\n".join([lines[0]] + [ln for ln in lines[1:] if ln.split(",")[0][:7] >= cutoff])
    c = cl.post(f"/api/cases/{cid}/statement", headers=h, json={"filename": "s.csv", "csv_text": short, "consent": True}).json()
    card = next(m["card"] for m in c["messages"] if (m.get("card") or {}).get("type") == "insights")
    assert card["months"] == 6 and card["source"] == "upload" and card["simulated"] is False
    msg = next(m["text"]["en"] for m in c["messages"] if (m.get("card") or {}).get("type") == "insights")
    assert "I read 6 months" in msg and "Only 6 months" in msg and "12 months" not in msg


# ------------------------------------------------------------------ idempotent submission
CRASH_CHILD = """
import os, sys
sys.path.insert(0, sys.argv[1])
from saakh import store
from saakh.agent import runtime as R
from saakh.autopilot import ACTOR, drive
c = drive(R.new_case("ramesh", "en"), stop_at={"approval"})
print(c["id"], flush=True)
store.put_application = lambda app: os._exit(17)  # the process dies after the LOS accepted the file
R.handle(c, {"type": "approve", "hash": c["pending"]["hash"], "confirm": True}, actor=ACTOR)
"""


def test_submission_resumes_in_a_new_process_without_a_duplicate():
    # The first process is killed after the (simulated) LOS accepted the file but before the record was saved.
    # This test process plays the restarted server: same database, fresh memory.
    child = subprocess.run([sys.executable, "-c", CRASH_CHILD, str(BACKEND)], env=dict(os.environ),
                           capture_output=True, text=True, timeout=120)
    assert child.returncode == 17, child.stderr
    cid = child.stdout.split()[0]
    c = store.load_case(cid)
    intent = c["submission_intent"]["key"]
    app_id, lender_id, h = intent.split(":")
    assert (app_id, lender_id, h) == (c["application"]["id"], c["application"]["lender"]["id"], c["application"]["hash"])
    receipt = store.los_get(intent)
    assert receipt and not c.get("submission")
    c = R.run(c)
    assert c["submission"]["los_ref"] == receipt["los_ref"] and "submission_intent" not in c
    assert store.get_application(c["application"]["id"])["los_ref"] == receipt["los_ref"]
    assert any("replayed" in (t.get("summary") or "") for t in c["trace"])


def test_idempotency_key_is_scoped_to_application_lender_and_version():
    a = {"id": "APP-1", "lender": {"id": "boi-pimpri"}, "hash": "h1"}
    r1 = integrations.los_submit(a)
    assert integrations.los_submit(a)["los_ref"] == r1["los_ref"]
    assert integrations.los_submit({**a, "lender": {"id": "aye-finance"}})["los_ref"] != r1["los_ref"]
    assert integrations.los_submit({**a, "hash": "h2"})["los_ref"] != r1["los_ref"]
    assert integrations.los_submit({**a, "id": "APP-2"})["los_ref"] != r1["los_ref"]


# ------------------------------------------------------------------ configuration
def _import_config(env):
    e = {k: v for k, v in os.environ.items() if not k.startswith("SAAKH_")}
    e.update(env)
    return subprocess.run([sys.executable, "-c", "import saakh.config as c; print(sorted(set(c.LENDER_KEYS.values())))"],
                          cwd=BACKEND, env=e, capture_output=True, text=True)


def test_production_refuses_missing_demo_or_weak_secrets_and_unknown_envs():
    strong, key2 = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    for weak in ("s" * 40, "ab" * 20, "0123456789" * 4):  # long but predictable
        assert _import_config({"SAAKH_ENV": "production", "SAAKH_SIGNING_KEY": weak,
                               "SAAKH_LENDER_KEYS": f"pnb-barabanki:{key2}"}).returncode != 0, weak
    assert _import_config({"SAAKH_ENV": "staging"}).returncode != 0
    assert _import_config({"SAAKH_ENV": "production"}).returncode != 0
    assert _import_config({"SAAKH_ENV": "production", "SAAKH_SIGNING_KEY": "saakh-demo-signing-key",
                           "SAAKH_LENDER_KEYS": f"pnb-barabanki:{key2}"}).returncode != 0
    assert _import_config({"SAAKH_ENV": "production", "SAAKH_SIGNING_KEY": strong,
                           "SAAKH_LENDER_KEYS": "pnb-barabanki:demo-pnb-barabanki"}).returncode != 0
    assert _import_config({"SAAKH_ENV": "production", "SAAKH_SIGNING_KEY": strong,
                           "SAAKH_LENDER_KEYS": "pnb-barabanki:short"}).returncode != 0
    ok = _import_config({"SAAKH_ENV": "production", "SAAKH_SIGNING_KEY": strong, "SAAKH_LENDER_KEYS": f"pnb-barabanki:{key2}"})
    assert ok.returncode == 0, ok.stderr
    assert "pnb-barabanki" in ok.stdout
