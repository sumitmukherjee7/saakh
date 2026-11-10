"""Regression tests for the sixth external review."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from saakh import consent, store
from saakh.agent import runtime as R
from saakh.api import main as api
from saakh.autopilot import ACTOR, drive


def LH(lender_id):
    return {"X-Lender-Key": "demo-" + lender_id}


def new_api_case(cl, persona="sunita", mode="self"):
    r = cl.post("/api/cases", json={"persona": persona, "lang": "en", "mode": mode}).json()
    return r["id"], {"X-Case-Token": r["case_token"]}


def _decide(cl, aid, lid, **body):
    body.setdefault("request_id", uuid.uuid4().hex)
    return cl.post(f"/api/lender/applications/{aid}/decision", headers=LH(lid), json=body)


# ------------------------------------------------------------------ strict, typed events
def test_truthy_strings_never_grant_consent_or_approval():
    cl = TestClient(api.app)
    cid, h = new_api_case(cl)
    c = cl.post(f"/api/cases/{cid}/events", headers=h, json={"type": "message", "text": "need 1.5 lakh"}).json()
    ids = c["pending"]["ids"]
    for bad in ("no", "false", 0, 1, None, [], "yes"):
        r = cl.post(f"/api/cases/{cid}/events", headers=h, json={"type": "consent", "decisions": {i: bad for i in ids}})
        assert r.status_code == 400, bad
    assert not any(a["status"] == "ACTIVE" for a in store.case_consents(cid))
    case = drive(store.load_case(cid), stop_at={"approval"})
    h_ = case["pending"]["hash"]
    for bad in ("false", "true", 1, 0, None):
        r = cl.post(f"/api/cases/{cid}/events", headers=h, json={"type": "approve", "hash": h_, "confirm": bad})
        assert r.status_code == 400, bad
    assert not store.load_case(cid)["approval"] and not store.load_case(cid)["submission"]


def test_events_reject_unknown_fields_and_wrong_types():
    for ev in ({"type": "message", "text": "hi", "admin": True}, {"type": "choose_offer", "index": "0"},
               {"type": "choose_offer", "index": True}, {"type": "action", "action": "register_udyam", "go": "yes"},
               {"type": "language", "lang": "fr"}, {"type": "message", "text": "x" * 2001},
               {"type": "correct", "fact": "age", "value": 40, "reason": "r" * 301}, {"type": "upload", "doc": "selfie"},
               {"type": "approve", "hash": "not-a-hash", "confirm": True}, {"type": "nonsense"}):
        with pytest.raises(ValueError):
            R.validate_event(ev)


def test_upload_scheduling_needs_the_document_checkpoint_and_a_planned_document():
    c = drive(R.new_case("sunita", "en"), stop_at={"documents"})
    planned = c["pending"]["docs"][0]
    with pytest.raises(ValueError):
        R.handle(c, {"type": "upload", "doc": "ration_card", "assisted": True}, actor=ACTOR)  # not in this plan
    c2 = drive(R.new_case("sunita", "en"), stop_at={"question"})
    with pytest.raises(ValueError):
        R.handle(c2, {"type": "upload", "doc": planned, "assisted": True}, actor=ACTOR)  # not at the documents step
    c = R.handle(c, {"type": "upload", "doc": planned, "assisted": True}, actor=ACTOR)
    assert planned in c["scheduled"]


# ------------------------------------------------------------------ one-time, expiring, per-step codes
def _assisted_at_consent():
    c = R.new_case("sunita", "en", mode="assisted")
    return R.handle(c, {"type": "message", "text": "need 1.5 lakh"})


def test_a_code_works_once_for_one_step_and_is_stored_only_as_a_verifier():
    c = _assisted_at_consent()
    code = c["demo_sms"]["code"]
    assert code not in json.dumps(c["otp_challenge"]) and len(c["otp_challenge"]["verifier"]) == 64
    c = R.handle(c, {"type": "consent", "decisions": {i: True for i in c["pending"]["ids"]}, "otp": code})
    assert consent.active(c["id"], "ekyc")
    assert c["otp_challenge"] is None or c["otp_challenge"]["purpose"] != "consent"
    assert R.check_otp(c, code, "consent") == "expired"  # consumed
    c = drive(c, stop_at={"approval"})
    assert c["demo_sms"]["purpose"] == "approval"
    if code != c["demo_sms"]["code"]:  # (a fresh 6-digit code can coincide with the old one by chance)
        assert R.check_otp(c, code, "approval") == "wrong"  # the consent code is no key to the approval


def test_a_code_expires():
    c = _assisted_at_consent()
    code = c["demo_sms"]["code"]
    c["otp_challenge"]["expires"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds")
    c = R.handle(c, {"type": "consent", "decisions": {i: True for i in c["pending"]["ids"]}, "otp": code})
    assert not consent.active(c["id"], "ekyc") and "expired" in c["messages"][-1]["text"]["en"]
    c["otp_challenge"]["issued"] = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat(timespec="seconds")
    c = R.handle(c, {"type": "resend_code"})
    c = R.handle(c, {"type": "consent", "decisions": {i: True for i in c["pending"]["ids"]}, "otp": c["demo_sms"]["code"]})
    assert consent.active(c["id"], "ekyc")


def test_new_codes_are_rate_limited_and_capped_and_failures_have_a_lifetime_cap():
    c = _assisted_at_consent()
    with pytest.raises(ValueError, match="less than a minute"):
        R.handle(c, {"type": "resend_code"})
    wrong = "000000" if c["demo_sms"]["code"] != "000000" else "111111"
    for _ in range(R.OTP_LIFETIME_FAILS):
        c.pop("otp_locked_until", None)  # skip the 15-minute waits
        if not c.get("otp_challenge"):
            R.issue_otp(c, "consent")
        c = R.handle(c, {"type": "consent", "decisions": {i: True for i in c["pending"]["ids"]}, "otp": wrong})
    assert c["otp_disabled"] and R.check_otp(c, "123456", "consent") == "locked"
    assert any(e["action"] == "otp.disabled" for e in store.audit_log(c["id"]))


def test_production_refuses_assisted_mode_without_an_sms_provider(monkeypatch):
    monkeypatch.setattr(api, "PRODUCTION", True)
    r = TestClient(api.app).post("/api/cases", json={"persona": "sunita", "lang": "en", "mode": "assisted"})
    assert r.status_code == 400 and "SMS" in r.json()["detail"]


# ------------------------------------------------------------------ lender views come only from the frozen snapshot
def test_lender_views_never_read_the_live_case(monkeypatch):
    c = drive(R.new_case("ramesh", "en"))
    aid, lid = c["application"]["id"], c["application"]["lender"]["id"]
    live = store.load_case(c["id"])
    live["facts"]["name"] = "CHANGED AFTER APPROVAL"
    live["analysis"]["insights"] = [{"id": "x", "tone": "bad", "title": {"en": "unapproved", "hi": "x"}, "detail": {"en": "", "hi": ""}}]
    store.save_case(live)  # e.g. another worker's unapproved change, racing the lender's read
    real = store.load_case
    monkeypatch.setattr(api, "_sweep", lambda cid: None)  # expiry enforcement may load the case; it is not under test here
    monkeypatch.setattr(store, "load_case", lambda cid: (_ for _ in ()).throw(AssertionError("lender route read the live case"))
                        if cid == c["id"] else real(cid))
    cl = TestClient(api.app)
    d = cl.get(f"/api/lender/applications/{aid}", headers=LH(lid))
    assert d.status_code == 200
    body = json.dumps(d.json())
    assert "CHANGED AFTER APPROVAL" not in body and "unapproved" not in body
    for path in ("/memo.pdf", "/dpr.pdf"):
        assert cl.get(f"/api/lender/applications/{aid}{path}", headers=LH(lid)).status_code == 200


def test_withdrawal_erases_the_frozen_view():
    c = drive(R.new_case("imran", "en"))
    aid = c["application"]["id"]
    assert store.get_application(aid)["view"]["facts"]["name"]
    R.revoke(store.load_case(c["id"]), consent.active(c["id"], "bank_statement")["consentId"])
    assert "view" not in store.get_application(aid)


# ------------------------------------------------------------------ lender's own reasons; complete idempotency
def test_a_decline_carries_only_the_banks_own_reasons():
    c = drive(R.new_case("imran", "en"))
    aid, lid = c["application"]["id"], c["application"]["lender"]["id"]
    cl = TestClient(api.app)
    assert _decide(cl, aid, lid, decision="decline").status_code == 422  # reasons required
    assert _decide(cl, aid, lid, decision="decline", reasons=["bounces_12m"]).status_code == 422  # a model factor is not a bank reason
    assert _decide(cl, aid, lid, decision="query", note="x", reasons=["other"]).status_code == 422
    assert _decide(cl, aid, lid, decision="decline", reasons=["business_viability"]).status_code == 200
    assert "the branch's reasons: business viability" in store.load_case(c["id"])["messages"][-1]["text"]["en"]


def test_idempotency_needs_an_id_compares_the_whole_request_and_keeps_every_receipt():
    c = drive(R.new_case("imran", "en"))
    aid, lid = c["application"]["id"], c["application"]["lender"]["id"]
    cl = TestClient(api.app)
    assert cl.post(f"/api/lender/applications/{aid}/decision", headers=LH(lid), json={"decision": "query", "note": "x"}).status_code == 422
    assert _decide(cl, aid, lid, decision="query", note="rent agreement", request_id="req-q-00000001").status_code == 200
    assert _decide(cl, aid, lid, decision="query", note="a different note", request_id="req-q-00000001").status_code == 409
    assert _decide(cl, aid, lid, decision="query", note="electricity bill", request_id="req-q-00000002").status_code == 200
    assert _decide(cl, aid, lid, decision="query", note="rent agreement", request_id="req-q-00000001").status_code == 200  # older receipt
    log = [e["action"] for e in store.audit_log(c["id"])]
    assert log.count("lender.query") == 2 and len(store.load_case(c["id"])["lender_events"]) == 2


# ------------------------------------------------------------------ self-review
def test_unknown_lender_is_a_400_and_a_query_needs_its_question():
    cl = TestClient(api.app)
    cid, h = new_api_case(cl, "ramesh")
    drive(store.load_case(cid), stop_at={"approval"})
    r = cl.post(f"/api/cases/{cid}/events", headers=h, json={"type": "set_lender", "lender_id": "no-such-bank"})
    assert r.status_code == 400
    c = drive(R.new_case("imran", "en"))
    assert _decide(cl, c["application"]["id"], c["application"]["lender"]["id"], decision="query").status_code == 422
