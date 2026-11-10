import base64
import json

import pytest
from fastapi.testclient import TestClient

from saakh import consent, store
from saakh.agent import nlu
from saakh.agent import runtime as R
from saakh.agent.tools import GuardError, call
from saakh.api.main import app
from saakh.autopilot import SAMPLE_PDF, drive
from saakh.data.personas import PERSONAS, statement
from saakh.uploads import statement_to_csv

def _rid():
    import uuid
    return uuid.uuid4().hex


def LH(aid):  # the demo key of the branch the file is addressed to
    return {"X-Lender-Key": "demo-" + store.get_application(aid)["lender"]["id"]}


def client():
    # no `with`: lifespan (demo seeding) is not needed and is disabled by SAAKH_SEED=0 anyway
    return TestClient(app)


def new_api_case(cl, persona="sunita", mode="self"):
    r = cl.post("/api/cases", json={"persona": persona, "lang": "en", "mode": mode}).json()
    return r["id"], {"X-Case-Token": r["case_token"]}


@pytest.mark.parametrize("pid", list(PERSONAS))
def test_every_persona_reaches_submission_with_intact_audit(pid):
    c = drive(R.new_case(pid, "en"))
    assert c["submission"], c["pending"]
    assert c["approval"]["hash"] == c["application"]["hash"]
    assert store.verify_chain(c["id"])["ok"]
    assert any(t["kind"] == "retry" for t in c["trace"])  # simulated AA timeout was recovered
    assert len(c["asked"]) <= R.MAX_QUESTIONS + 2
    actors = {e["actor"] for e in store.audit_log(c["id"])}
    assert "demo-autopilot" in actors and "entrepreneur" not in actors  # demo runs never impersonate the person


def test_expected_routes():
    got = {}
    for pid in ("sunita", "lakshmamma", "imran", "mohan"):
        c = drive(R.new_case(pid, "en"))
        got[pid] = (c["offers"][0]["scheme_id"], c["offers"][0]["amount"])
    assert got["sunita"] == ("pm_vishwakarma", 100000)
    assert got["lakshmamma"][0] == "pmmy" and 100000 < got["lakshmamma"][1] < 300000
    assert got["imran"][0] == "pm_svanidhi"
    assert got["mohan"][1] == 0  # honest "not now"


def test_udyam_message_never_promises_cgtmse():
    c = drive(R.new_case("sunita", "en"))
    texts = " ".join(m["text"]["en"] for m in c["messages"] if m["role"] == "agent")
    assert "now open" not in texts.lower()
    assert "decided by your lender" in texts
    cg = next(r for r in c["schemes"] if r["id"] == "cgtmse")
    assert any("Member Lending Institution" in lc["text"]["en"] for lc in cg["lender_checks"])
    assert c["facts"]["enterprise_class"] == "micro"  # derived from declared investment AND turnover


def test_guard_blocks_data_pull_without_consent():
    c = R.new_case("sunita", "en")
    with pytest.raises(GuardError, match="consent"):
        call(c, "fetch_bank_statement", c["trace"])
    assert c["trace"][-1]["status"] == "blocked"


def test_submit_blocked_until_exact_file_approved():
    c = drive(R.new_case("ramesh", "en"), stop_at={"approval"})
    assert c["pending"]["type"] == "approval"
    with pytest.raises(GuardError, match="approval"):
        call(c, "submit_application", c["trace"])
    c = R.handle(c, {"type": "approve", "hash": "0" * 64, "confirm": True})
    assert not c["approval"]


def test_changing_file_after_approval_voids_approval():
    c = drive(R.new_case("ramesh", "en"), stop_at={"approval"})
    h = c["application"]["hash"]
    c["approval"] = {"hash": h, "ts": store.now(), "by": "test"}
    c["selected_offer"]["amount"] = 1  # tamper with the file
    call(c, "assemble_application", c["trace"])
    assert c["application"]["hash"] != h and c["approval"] is None


def test_revoking_statement_consent_deletes_derived_data():
    c = drive(R.new_case("lakshmamma", "en"), stop_at={"choose_offer"})
    assert c["analysis"]
    art = consent.active(c["id"], "bank_statement")
    c = R.revoke(c, art["consentId"])
    assert c["analysis"] is None and not c["data"].get("statement") and not c["offers"]
    with pytest.raises(GuardError):
        call(c, "analyze_cashflow", c["trace"])


def test_revocation_after_submission_erases_lender_copy():
    c = drive(R.new_case("imran", "en"))
    aid = c["application"]["id"]
    assert store.get_application(aid)["package"]
    c = R.revoke(c, consent.active(c["id"], "bank_statement")["consentId"])
    a = store.get_application(aid)
    assert a["status"] == "withdrawn" and a["package"] is None and a["redacted"]
    assert c["application"]["package"] is None and c["uploads"] == {}
    cl = client()
    assert cl.get(f"/api/lender/applications/{aid}", headers=LH(aid)).status_code == 403
    assert cl.get(f"/api/lender/applications/{aid}/memo.pdf", headers=LH(aid)).status_code == 403
    assert cl.get(f"/api/lender/applications/{aid}/dpr.pdf", headers=LH(aid)).status_code == 403
    assert cl.post(f"/api/lender/applications/{aid}/decision", headers=LH(aid), json={"request_id": _rid(), "decision": "query", "note": "rent agreement"}).status_code == 409


def test_lender_access_ends_when_sharing_consent_revoked():
    c = drive(R.new_case("imran", "en"))
    aid = c["application"]["id"]
    cl = client()
    assert cl.get(f"/api/lender/applications/{aid}").status_code == 401  # no key
    assert cl.get(f"/api/lender/applications/{aid}", headers=LH(aid)).status_code == 200
    assert cl.get(f"/api/lender/applications/{aid}/memo.pdf", headers=LH(aid)).status_code == 200
    share = consent.active(c["id"], "share_with_lender", {"lender": c["application"]["lender"]["id"]})
    R.revoke(store.load_case(c["id"]), share["consentId"])
    assert store.get_application(aid)["status"] == "withdrawn"
    assert cl.get(f"/api/lender/applications/{aid}", headers=LH(aid)).status_code == 403
    assert cl.get(f"/api/lender/applications/{aid}/memo.pdf", headers=LH(aid)).status_code == 403
    assert cl.post(f"/api/lender/applications/{aid}/decision", headers=LH(aid), json={"request_id": _rid(), "decision": "sanction", "amount": 5000}).status_code == 409


def test_case_routes_require_the_case_token():
    cl = client()
    cid, h = new_api_case(cl)
    cid2, h2 = new_api_case(cl)
    assert cl.get(f"/api/cases/{cid}").status_code == 401
    assert cl.get(f"/api/cases/{cid}", headers=h2).status_code == 401  # another case's token
    r = cl.get(f"/api/cases/{cid}", headers=h)
    assert r.status_code == 200 and "token_hash" not in r.json() and "otp" not in r.json()
    assert cl.post(f"/api/cases/{cid}/events", json={"type": "message", "text": "hi"}).status_code == 401


def test_clients_cannot_inject_internal_events_or_fake_uploads():
    cl = client()
    cid, h = new_api_case(cl)
    for t in ("_sample_upload", "fallback_upload", "document.received"):
        assert cl.post(f"/api/cases/{cid}/events", headers=h, json={"type": t}).status_code == 400
    # an 'upload' event can only schedule a café visit for a document the file is waiting for; it never marks receipt
    c = drive(store.load_case(cid), stop_at={"documents"})
    assert c["pending"]["type"] == "documents"
    doc = c["pending"]["docs"][0]
    assert cl.post(f"/api/cases/{cid}/events", headers=h, json={"type": "upload", "doc": doc}).status_code == 400
    assert cl.post(f"/api/cases/{cid}/events", headers=h, json={"type": "upload", "doc": "ration_card", "assisted": True}).status_code == 400
    assert doc not in store.load_case(cid)["uploads"]


def test_document_upload_is_validated_and_fingerprinted():
    cl = client()
    cid, h = new_api_case(cl)
    good = {"filename": "me.pdf", "data_b64": base64.b64encode(SAMPLE_PDF).decode()}
    assert cl.post(f"/api/cases/{cid}/documents/selfie", headers=h, json=good).status_code == 400  # no document plan yet
    drive(store.load_case(cid), stop_at={"documents"})
    bad = base64.b64encode(b"MZ\x90\x00not a pdf").decode()
    assert cl.post(f"/api/cases/{cid}/documents/selfie", headers=h, json={"filename": "x.pdf", "data_b64": bad}).status_code == 400
    assert cl.post(f"/api/cases/{cid}/documents/nonsense", headers=h,
                   json={"filename": "x.pdf", "data_b64": base64.b64encode(SAMPLE_PDF).decode()}).status_code == 400
    r = cl.post(f"/api/cases/{cid}/documents/selfie", headers=h,
                json={"filename": "me.pdf", "data_b64": base64.b64encode(SAMPLE_PDF).decode()})
    assert r.status_code == 200
    meta = r.json()["uploads"]["selfie"]
    assert len(meta["sha256"]) == 64 and meta["verified_by_saakh"] is False


def test_statement_upload_uses_its_own_consent_and_never_revives_aa():
    cl = client()
    cid, h = new_api_case(cl, "lakshmamma")
    c = cl.post(f"/api/cases/{cid}/events", headers=h, json={"type": "message", "text": "need 3 lakh for cows"}).json()
    ids = c["pending"]["ids"]
    kinds = {a["consentId"]: a["kind"] for a in store.case_consents(cid)}
    dec = {i: kinds[i] == "ekyc" for i in ids}  # decline AA, bureau, Udyam
    c = cl.post(f"/api/cases/{cid}/events", headers=h, json={"type": "consent", "decisions": dec}).json()
    assert c["pending"]["type"] == "fallback_statement"
    csv_text = statement_to_csv(statement("lakshmamma"))
    assert cl.post(f"/api/cases/{cid}/statement", headers=h, json={"filename": "s.csv", "csv_text": csv_text, "consent": False}).status_code == 400
    c = cl.post(f"/api/cases/{cid}/statement", headers=h, json={"filename": "s.csv", "csv_text": csv_text, "consent": True}).json()
    assert c["data"]["statement"]["source"] == "upload" and c["analysis"]
    aa = [a for a in store.case_consents(cid) if a["kind"] == "bank_statement"][0]
    assert aa["status"] == "REJECTED"
    assert not any(t.get("name") == "fetch_bank_statement" for t in c["trace"])
    up = consent.active(cid, "statement_upload")
    c = cl.post(f"/api/cases/{cid}/consents/{up['consentId']}/revoke", headers=h).json()
    assert store.get_statement(cid) is None and c["analysis"] is None


def test_consent_ids_are_bound_to_the_case():
    cl = client()
    a, ha = new_api_case(cl)
    b, hb = new_api_case(cl)
    ca = cl.post(f"/api/cases/{a}/events", headers=ha, json={"type": "message", "text": "1 lakh"}).json()
    cl.post(f"/api/cases/{b}/events", headers=hb, json={"type": "message", "text": "1 lakh"})
    foreign = ca["pending"]["ids"][0]
    r = cl.post(f"/api/cases/{b}/events", headers=hb, json={"type": "consent", "decisions": {foreign: True}})
    assert r.status_code == 400
    assert store.get_consent(foreign)["status"] == "PENDING"
    assert cl.post(f"/api/cases/{b}/consents/{foreign}/revoke", headers=hb).status_code == 400


def test_events_are_idempotent():
    cl = client()
    cid, h = new_api_case(cl)
    ev = {"type": "message", "text": "I need 1 lakh for a sewing machine", "event_id": "evt-123"}
    n1 = len(cl.post(f"/api/cases/{cid}/events", headers=h, json=ev).json()["messages"])
    n2 = len(cl.post(f"/api/cases/{cid}/events", headers=h, json=ev).json()["messages"])
    assert n1 == n2


def test_api_autopilot_never_approves():
    cl = client()
    cid, h = new_api_case(cl, "ramesh")
    c = cl.post(f"/api/cases/{cid}/autopilot", headers=h, json={"stop_at": []}).json()
    assert c["pending"]["type"] == "approval" and not c["approval"] and not c["submission"]


def test_lender_decision_is_validated():
    c = drive(R.new_case("ramesh", "en"))
    aid = c["application"]["id"]
    cl = client()
    assert cl.post(f"/api/lender/applications/{aid}/decision", headers=LH(aid), json={"request_id": _rid(), "decision": "approve!"}).status_code == 422
    assert cl.post(f"/api/lender/applications/{aid}/decision", headers=LH(aid), json={"request_id": _rid(), "decision": "sanction"}).status_code == 400
    assert cl.post(f"/api/lender/applications/{aid}/decision", headers=LH(aid),
                   json={"request_id": _rid(), "decision": "sanction", "amount": 99_00_00_000}).status_code in (400, 422)
    assert cl.post(f"/api/lender/applications/{aid}/decision", headers=LH(aid),
                   json={"request_id": _rid(), "decision": "sanction", "amount": 500000}).status_code == 200


def test_audit_tamper_detected_and_sensitive_answers_redacted():
    c = R.new_case("sunita", "en")
    R.handle(c, {"type": "message", "text": "need 1 lakh for machine"})
    c = store.load_case(c["id"])
    c["pending"] = {"type": "question", "fact": "social_category"}
    R.handle(c, {"type": "answer", "fact": "social_category", "value": "obc"})
    log = store.audit_log(c["id"])
    ans = [e for e in log if e["action"] == "event.answer"][0]
    assert "value" not in ans["payload"] and ans["payload"]["value_recorded_in_case"]
    store.conn().execute("UPDATE audit SET actor='mallory' WHERE case_id=? AND seq=1", (c["id"],))
    v = store.verify_chain(c["id"])
    assert not v["ok"] and v["broken_at"] == 1


def test_assisted_mode_requires_entrepreneurs_one_time_code():
    c = R.new_case("sunita", "hi", mode="assisted")
    assert not c.get("otp_challenge")  # no code exists until a step needs one
    c = R.handle(c, {"type": "message", "text": "डेढ़ लाख चाहिए"})
    ids, code = c["pending"]["ids"], c["demo_sms"]["code"]
    assert c["demo_sms"]["purpose"] == "consent" and code not in json.dumps(c["otp_challenge"])  # only a verifier is stored
    for wrong in ("000000", "482913", None):
        if wrong == code:
            continue
        c = R.handle(c, {"type": "consent", "decisions": {i: True for i in ids}, "otp": wrong})
        assert c["pending"]["type"] == "consent" and not consent.active(c["id"], "ekyc")
    c = R.handle(c, {"type": "consent", "decisions": {i: True for i in ids}, "otp": code})
    assert consent.active(c["id"], "ekyc")


def test_declining_optional_consents_falls_back_to_questions():
    c = R.new_case("sunita", "en")
    c = R.handle(c, {"type": "message", "text": "I need 1.5 lakh for sewing machines"})
    arts = {a["kind"]: a["consentId"] for a in store.case_consents(c["id"])}
    dec = {arts["ekyc"]: False, arts["bank_statement"]: True, arts["bureau"]: False, arts["udyam"]: False}
    c = R.handle(c, {"type": "consent", "decisions": dec})
    assert c["data"]["ekyc"].get("manual") and not c["data"].get("bureau")
    assert c["analysis"] is not None


def test_hindi_nlu():
    assert nlu.intake("मुझे दो नई सिलाई मशीनें चाहिए, डेढ़ लाख")["loan_amount_sought"] == 150000
    assert nlu.intake("पच्चीस हज़ार रुपये ठेले के लिए")["loan_amount_sought"] == 25000
    assert nlu.intake("Our group needs leaf-plate machines, 4 lakh")["ownership_type"] == "shg"
    assert nlu.intake("दुकान में माल भरने के लिए तीन लाख चाहिए")["activity"] == "retail"
    assert nlu.answer("is_new_unit", "नहीं") is False
    assert nlu.answer("loan_amount_sought", "2.5 lakh") == 250000
    assert nlu.answer("education", "10th pass") == "10th"


def test_why_question_answers_with_citations_on_every_sentence():
    c = drive(R.new_case("sunita", "en"), stop_at={"question"})
    assert c["pending"]["fact"]
    c = R.handle(c, {"type": "message", "text": "Why not PMEGP?"})
    card = c["messages"][-1]["card"]
    assert card["type"] == "explanation" and card["scheme"] == "pmegp"
    assert all(s["cites"] for s in card["sentences"])
