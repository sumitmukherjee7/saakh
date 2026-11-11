"""Regression tests for the fifth external review and the self-review done alongside it."""
import json

import pytest
from fastapi.testclient import TestClient

from saakh import consent, store, uploads
from saakh.agent import runtime as R
from saakh.api import main as api
from saakh.autopilot import ACTOR, SAMPLE_PDF, drive
from saakh.schemes import engine

OTHER_PDF = SAMPLE_PDF.replace(b"200 100", b"333 111")


def LH(lender_id):
    return {"X-Lender-Key": "demo-" + lender_id}


def _sent(persona="imran"):
    c = drive(R.new_case(persona, "en"))
    return c, c["application"]["id"], c["application"]["lender"]["id"]


def _decide(cl, aid, lid, **body):
    import uuid
    body.setdefault("request_id", uuid.uuid4().hex)
    return cl.post(f"/api/lender/applications/{aid}/decision", headers=LH(lid), json=body)


# ------------------------------------------------------------------ decision state, version and idempotency
def test_a_supersede_by_another_worker_between_check_and_write_blocks_the_decision(monkeypatch):
    c, aid, lid = _sent()
    real = store.decide_application

    def other_worker_supersedes_first(app, expected_rev, entry=None):
        other = store.get_application(app["id"])  # a different process changes the file at this moment
        other.update(superseded=True, superseded_reason="document replaced")
        store.put_application(other)
        return real(app, expected_rev, entry)

    monkeypatch.setattr(store, "decide_application", other_worker_supersedes_first)
    r = _decide(TestClient(api.app), aid, lid, decision="sanction", amount=10000)
    assert r.status_code == 409
    a = store.get_application(aid)
    assert a["superseded"] and a["decision"] is None and a["status"] == "submitted"  # newer copy kept, nothing overwritten
    assert not any(e["action"].startswith("lender.sanction") for e in store.audit_log(c["id"]))


def test_stale_revision_cannot_be_written_even_with_the_same_status():
    c, aid, _ = _sent()
    stale = store.get_application(aid)
    fresh = store.get_application(aid)
    store.put_application(fresh)  # e.g. re-sent with the same status: revision moves on
    stale.update(status="sanctioned", decision={"decision": "sanction"})
    assert store.decide_application(stale, stale["rev"]) is False


def test_final_decisions_are_final_and_retries_are_idempotent():
    c, aid, lid = _sent()
    cl = TestClient(api.app)
    assert _decide(cl, aid, lid, decision="query", note="please add rent agreement", request_id="req-query-0001").status_code == 200
    assert _decide(cl, aid, lid, decision="query", note="please add rent agreement", request_id="req-query-0001").status_code == 200
    assert _decide(cl, aid, lid, decision="sanction", amount=10000, request_id="req-sanction-001").status_code == 200
    assert _decide(cl, aid, lid, decision="sanction", amount=10000, request_id="req-sanction-001").status_code == 200  # replay
    r = _decide(cl, aid, lid, decision="decline", reasons=["other"], request_id="req-decline-0001")
    assert r.status_code == 409 and "final decision" in r.json()["detail"]
    log = [e["action"] for e in store.audit_log(c["id"])]
    assert log.count("lender.query") == 1 and log.count("lender.sanction") == 1 and "lender.decline" not in log
    events = store.load_case(c["id"])["lender_events"]
    assert [e["decision"] for e in events] == ["query", "sanction"]  # each delivered exactly once


# ------------------------------------------------------------------ bounded, minimal decision data
def test_decision_reasons_are_bounded_codes_and_the_audit_keeps_no_amount_note_or_officer():
    c, aid, lid = _sent()
    cl = TestClient(api.app)
    assert _decide(cl, aid, lid, decision="decline", reasons=["applicant owes Rs 40,000 to Ramkumar"]).status_code == 422
    assert _decide(cl, aid, lid, decision="decline", reasons=["other"] * 9).status_code == 422
    r = _decide(cl, aid, lid, decision="decline", reasons=["credit_history", "repayment_capacity"],
                note="Ramkumar loan of Rs 40,000 seen", officer="Officer A. Sharma")
    assert r.status_code == 200
    e = next(e for e in store.audit_log(c["id"]) if e["action"] == "lender.decline")
    text = json.dumps(e["payload"])
    assert "40,000" not in text and "Sharma" not in text and "amount" not in e["payload"]
    assert e["payload"]["reasons"] == ["credit_history", "repayment_capacity"] and len(e["payload"]["decision_sha256"]) == 64
    msg = store.load_case(c["id"])["messages"][-1]["text"]["en"]
    assert "branch's reasons: credit history, repayment capacity" in msg  # the bank's codes, shown as labels


def test_revoking_after_a_decision_erases_its_notes_from_the_case():
    c, aid, lid = _sent()
    cl = TestClient(api.app)
    assert _decide(cl, aid, lid, decision="query", note="Ramkumar loan of Rs 40,000 seen").status_code == 200
    case = store.load_case(c["id"])
    assert any("Ramkumar" in m["text"]["en"] for m in case["messages"])
    case = R.revoke(case, consent.active(c["id"], "share_with_lender", {"lender": lid})["consentId"])
    blob = json.dumps({"m": case["messages"], "e": case["lender_events"]}, ensure_ascii=False)
    assert "Ramkumar" not in blob and "40,000" not in blob
    assert case["lender_events"] == [{"id": case["lender_events"][0]["id"], "decision": "query",
                                      "ts": case["lender_events"][0]["ts"], "redacted": True}]
    assert "Ramkumar" not in json.dumps(store.get_application(aid))
    assert "Ramkumar" not in json.dumps([e["payload"] for e in store.audit_log(c["id"])])


def test_a_case_save_conflict_after_the_decision_is_recorded_does_not_lose_or_duplicate_it(monkeypatch):
    c, aid, lid = _sent()
    real = R.lender_event
    calls = {"n": 0}

    def conflicting(case, dec):
        calls["n"] += 1
        if calls["n"] <= 3:  # every immediate attempt collides with a concurrent save
            raise store.StaleCaseError("concurrent save")
        return real(case, dec)

    monkeypatch.setattr(R, "lender_event", conflicting)
    cl = TestClient(api.app)
    r = _decide(cl, aid, lid, decision="sanction", amount=10000, request_id="req-sanction-777")
    assert r.status_code == 200 and store.get_application(aid)["status"] == "sanctioned"  # durable, and reported as such
    assert store.load_case(c["id"])["lender_events"] == []  # not yet delivered ...
    api._sweep(c["id"])  # ... until the case is next opened
    events = store.load_case(c["id"])["lender_events"]
    assert [e["id"] for e in events] == ["req-sanction-777"]
    api._sweep(c["id"])
    assert len(store.load_case(c["id"])["lender_events"]) == 1  # applied once, never twice


# ------------------------------------------------------------------ events only at their checkpoint
def test_events_are_only_accepted_at_their_own_checkpoint():
    c = drive(R.new_case("ramesh", "en"))  # submitted
    for ev in ({"type": "choose_offer", "index": 0}, {"type": "approve", "hash": c["application"]["hash"], "confirm": True},
               {"type": "set_lender", "lender_id": "aye-finance"}, {"type": "skip", "fact": "is_minority"},
               {"type": "action", "action": "register_udyam", "go": True}):
        with pytest.raises(ValueError):
            R.handle(store.load_case(c["id"]), ev, actor=ACTOR)
    after = store.load_case(c["id"])
    assert after["submission"] and after["selected_offer"] == c["selected_offer"]
    assert after["application"]["lender"] == c["application"]["lender"]


# ------------------------------------------------------------------ lender view
def test_a_superseded_file_is_not_served_from_the_live_case():
    c, aid, lid = _sent("ramesh")
    doc = next(d["doc"] for d in c["application"]["package"]["documents"] if d["attachment"])
    meta = uploads.save_document(c["id"], doc, "v2.pdf", OTHER_PDF)
    R.document_received(store.load_case(c["id"]), doc, meta, actor=ACTOR)
    cl = TestClient(api.app)
    for path in ("", "/memo.pdf", "/dpr.pdf", f"/documents/{doc}"):
        assert cl.get(f"/api/lender/applications/{aid}{path}", headers=LH(lid)).status_code == 409, path
    listed = next(x for x in cl.get("/api/lender/applications", headers=LH(lid)).json() if x["id"] == aid)
    assert listed["superseded"]


def test_lender_detail_exposes_provenance_only_for_shared_facts():
    c, aid, lid = _sent("sunita")
    case = store.load_case(c["id"])
    case["fact_meta"].setdefault("social_category", {"source": ACTOR})["dispute"] = {"claimed": "sc"}
    store.save_case(case)
    d = TestClient(api.app).get(f"/api/lender/applications/{aid}", headers=LH(lid)).json()["detail"]
    assert set(d["fact_meta"]) <= set(api.SHARED_FACTS) and "social_category" not in d["fact_meta"]


# ------------------------------------------------------------------ PMEGP negative list wording
def test_negative_list_yes_shows_the_exceptions_and_partly_stays_open():
    f = dict(age=34, gender="female", area_type="rural", sector="services", activity="other", ownership_type="individual",
             is_new_unit=True, project_cost=3_00_000, availed_other_govt_subsidy=False, availed_pmegp=False,
             family_member_availed_pmegp=False, education="8th")
    yes = engine.evaluate_scheme("pmegp", {**f, "negative_list_declared": "yes"})
    assert yes["eligibility"] == "not_eligible"
    assert any("hotel or dhaba" in cv["text"]["en"] for cv in yes["caveats"])  # a permitted activity is not silently excluded
    assert engine.evaluate_scheme("pmegp", {**f, "negative_list_declared": "unsure"})["eligibility"] == "needs_info"
    from saakh.facts import FACTS
    q = FACTS["negative_list_declared"].question["en"]
    assert "hotel or dhaba is allowed" in q and "under 75 microns" in q and "dairy, poultry, fish or silkworms" in q


# ------------------------------------------------------------------ self-review: OTP brute force, request-id reuse
def test_assisted_otp_locks_after_five_wrong_codes_and_issues_a_new_one():
    c = R.new_case("sunita", "en", mode="assisted")
    c = R.handle(c, {"type": "message", "text": "need 1.5 lakh"})
    ids, first = c["pending"]["ids"], c["demo_sms"]["code"]
    wrong = "000000" if first != "000000" else "111111"
    for _ in range(R.OTP_MAX_FAILS):
        c = R.handle(c, {"type": "consent", "decisions": {i: True for i in ids}, "otp": wrong})
    assert c["otp_challenge"] is None and c["otp_locked_until"] and not consent.active(c["id"], "ekyc")
    c = R.handle(c, {"type": "consent", "decisions": {i: True for i in ids}, "otp": first})  # the guessed-at code is void
    assert not consent.active(c["id"], "ekyc")
    with pytest.raises(ValueError):
        R.handle(c, {"type": "resend_code"})  # no new code while locked
    assert any(e["action"] == "otp.locked" for e in store.audit_log(c["id"]))
    pub = R.public_case(c)
    assert not {"otp_challenge", "otp_fails", "demo_sms"} & set(pub)


def test_a_reused_request_id_with_a_different_decision_is_refused():
    c, aid, lid = _sent()
    cl = TestClient(api.app)
    assert _decide(cl, aid, lid, decision="query", note="x", request_id="req-reused-0001").status_code == 200
    assert _decide(cl, aid, lid, decision="decline", reasons=["other"], request_id="req-reused-0001").status_code == 409
