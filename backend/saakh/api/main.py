"""Saakh HTTP API (FastAPI) + static frontend.

    uvicorn saakh.api.main:app --port 8000

Security model
* Each case gets a random bearer token at creation (only its SHA-256 is stored);
  every case route requires it in `X-Case-Token`. Cases cannot see each other.
* Lender routes require `X-Lender-Key`; each key maps to exactly one lender
  (env SAAKH_LENDER_KEYS="lender-id:key,..."), and a lender sees only files
  addressed to it, and only while the entrepreneur's consent to share with
  *that* lender is ACTIVE. Attachment downloads are re-verified against the
  approved SHA-256 and audit-logged.
* SAAKH_ENV=production disables demo-only routes (autopilot, seeding, case
  listing, sample data) and refuses to start without real keys.
* Clients cannot inject internal events; uploads are validated server-side.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hmac
import json
import os
import random
import threading
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from .. import __version__, consent, integrations, store, uploads
from ..config import DEMO, DEMO_LENDER_PREFIX, ENV, LENDER_KEYS, PRODUCTION
from ..agent import runtime as R
from ..autopilot import drive
from ..data.personas import PERSONAS, public_persona, statement
from ..docs.pdf import credit_memo, project_report
from ..docs.planner import DOCS
from ..facts import FACTS, fact_public
from ..risk.scorecard import ARTIFACTS
from ..schemes.engine import evaluate_all, kb_summary, load_sources
from ..util import sha256

CLIENT_EVENTS = {"message", "consent", "answer", "correct", "skip", "action", "choose_offer", "upload", "approve",
                 "set_lender", "language", "resend_code"}
_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)


SWEEP_SECONDS = max(30, int(os.environ.get("SAAKH_EXPIRY_SWEEP_SECONDS", "300")))


def sweep_expired() -> list[str]:
    """Expire lapsed consents and delete their data for every case, independent of anyone opening the case."""
    return R.sweep_due(_sweep)


async def _expiry_loop():
    while True:
        try:
            await asyncio.to_thread(sweep_expired)
        except Exception as err:  # noqa: BLE001, keep sweeping; the failure is visible in logs
            print(f"[saakh] expiry sweep failed: {err!r}")
        await asyncio.sleep(SWEEP_SECONDS)


@asynccontextmanager
async def lifespan(_app):
    if DEMO and os.environ.get("SAAKH_SEED", "1") == "1" and not store.list_applications():
        _seed()
    # One sweeper per deployment: with several workers set SAAKH_EXTERNAL_SWEEP=1 and run `python -m saakh.sweep`
    # from cron. Concurrent saves are still safe: case writes are revision-checked (store.StaleCaseError).
    task = None if os.environ.get("SAAKH_EXTERNAL_SWEEP") == "1" else asyncio.create_task(_expiry_loop())
    try:
        yield
    finally:
        if task:
            task.cancel()


app = FastAPI(title="Saakh API", version=__version__, lifespan=lifespan)


@app.exception_handler(store.StaleCaseError)
async def _stale(_req, err):
    return JSONResponse({"detail": "this case was changed by another request; reload and try again"}, status_code=409)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Case-Token", "X-Lender-Key"])


# --------------------------------------------------------------------------- models & auth
class NewCase(BaseModel):
    persona: str
    lang: Literal["hi", "en"] = "hi"
    mode: Literal["self", "assisted"] = "self"
    chaos: bool = True


class Event(BaseModel):
    type: str
    model_config = {"extra": "allow"}


class Decision(BaseModel):
    decision: Literal["sanction", "query", "decline"]
    amount: float | None = Field(default=None, ge=1000, le=10_00_00_000)
    note: str | None = Field(default=None, max_length=500)  # kept only in the (erasable) file and case, never in the audit
    reasons: list[R.ReasonCode] | None = Field(default=None, max_length=8)  # the bank's own codes, not free text
    officer: str | None = Field(default="Branch Manager", max_length=80)
    request_id: str = Field(pattern=r"^[A-Za-z0-9-]{8,64}$")  # required idempotency key; reuse it when retrying
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _decline_needs_reasons(self):
        if self.decision == "decline" and not self.reasons:
            raise ValueError("a decline needs at least one of the branch's reason codes")
        if self.decision != "decline" and self.reasons:
            raise ValueError("reason codes are only for a decline")
        if self.decision == "query" and not (self.note or "").strip():
            raise ValueError("a query must say what the branch needs")
        return self


def _decision_fingerprint(d: "Decision") -> str:
    return sha256({k: v for k, v in d.model_dump().items() if k != "request_id"})


class DocUpload(BaseModel):
    filename: str = Field(max_length=200)
    data_b64: str = Field(max_length=7_200_000)


class StatementUpload(BaseModel):
    filename: str = Field(max_length=200)
    csv_text: str = Field(max_length=5_500_000)
    consent: bool
    otp: str | None = Field(default=None, max_length=12)  # assisted mode: the entrepreneur's one-time code


class Autopilot(BaseModel):
    stop_at: list[str] | None = None


def case_auth(cid: str, x_case_token: str | None = Header(default=None)) -> dict:
    c = store.load_case(cid)
    if not c:
        raise HTTPException(404, "case not found")
    if not x_case_token or not hmac.compare_digest(sha256(x_case_token.encode()), c.get("token_hash", "")):
        raise HTTPException(401, "missing or invalid case token")
    return _sweep(cid) or c


def _sweep(cid: str) -> dict | None:
    """Expire consents past their end date and clean up their data before anyone reads the case;
    also deliver any lender decision whose notification did not reach the case yet."""
    with _locks[cid]:
        c = store.load_case(cid)
        if not c:
            return None
        c = R.enforce_expiry(c)
        return R.sync_lender_events(c)


def lender_auth(x_lender_key: str | None = Header(default=None)) -> str:
    """Returns the authenticated lender id (the principal). Every key belongs to exactly one lender."""
    principal = None
    for key, lender_id in LENDER_KEYS.items():  # compare against every key: no early exit timing signal
        if x_lender_key and hmac.compare_digest(x_lender_key.encode(), key.encode()):
            principal = lender_id
    if not principal:
        raise HTTPException(401, "missing or invalid lender key")
    return principal


def demo_only() -> None:
    if not DEMO:
        raise HTTPException(404, "not available outside demo builds")


def _pub(c: dict) -> dict:
    return R.public_case(c, demo=DEMO)


# --------------------------------------------------------------------------- meta
@app.get("/api/health")
def health():
    demo_keys = [{"lender": lid, "key": k} for k, lid in LENDER_KEYS.items() if k.startswith(DEMO_LENDER_PREFIX)] if DEMO else []
    return {"ok": True, "version": __version__, "env": ENV, "demo": DEMO,
            "demo_lender_keys": demo_keys,  # demo builds only: the published per-branch demo keys
            "simulated_integrations": ["DigiLocker e-KYC", "Account Aggregator", "Credit bureau", "Udyam", "PM SVANidhi LoR", "Lender LOS"]}


@app.get("/api/personas")
def personas():
    return [public_persona(p) for p in PERSONAS]


@app.get("/api/facts")
def facts():
    return {k: fact_public(k) for k in FACTS}


# --------------------------------------------------------------------------- entrepreneur / operator
@app.post("/api/cases")
def create_case(body: NewCase):
    if body.persona not in PERSONAS:
        raise HTTPException(400, "unknown persona")
    if PRODUCTION and body.mode == "assisted":
        raise HTTPException(400, "assisted mode needs an SMS provider for the entrepreneur's codes, and none is integrated")
    c = R.new_case(body.persona, body.lang, body.mode, body.chaos)
    token = os.urandom(16).hex()
    c["token_hash"] = sha256(token.encode())
    store.save_case(c)
    return {**_pub(c), "case_token": token}


@app.get("/api/cases", dependencies=[Depends(demo_only)])
def list_cases():
    return [{"id": c["id"], "persona": c["persona"], "updated": c["updated"], "stage": (c.get("pending") or {}).get("type"),
             "submitted": bool(c.get("submission"))} for c in store.list_cases()]


@app.get("/api/cases/{cid}")
def get_case(c: dict = Depends(case_auth)):
    return _pub(c)


@app.post("/api/cases/{cid}/events")
def post_event(cid: str, ev: Event, c: dict = Depends(case_auth)):
    e = ev.model_dump()
    if e["type"] not in CLIENT_EVENTS:
        raise HTTPException(400, f"event type {e['type']!r} is not accepted from clients")
    with _locks[cid]:
        c = store.load_case(cid)
        try:
            c = R.handle(c, e)
        except (KeyError, ValueError, IndexError, TypeError) as err:
            raise HTTPException(400, f"bad event: {err}") from err
        except integrations.PermanentError as err:
            raise HTTPException(503, f"an external (simulated) system cannot complete this: {err}") from err
        except integrations.TransientError as err:  # retries exhausted; state up to the failure is kept
            raise HTTPException(503, f"an external (simulated) system is unavailable, please retry: {err}") from err
    return _pub(c)


@app.post("/api/cases/{cid}/documents/{doc}")
def upload_document(cid: str, doc: str, body: DocUpload, c: dict = Depends(case_auth)):
    if doc not in DOCS:
        raise HTTPException(400, "unknown document type")
    planned = {i["doc"] for i in ((c.get("documents") or {}).get("items") or [])}
    if doc not in planned:
        raise HTTPException(400, "this file is not asking for that document")
    try:
        data = base64.b64decode(body.data_b64, validate=True)
    except (binascii.Error, ValueError) as err:
        raise HTTPException(400, "file must be base64-encoded") from err
    with _locks[cid]:
        try:
            meta = uploads.save_document(cid, doc, body.filename, data)
        except uploads.UploadError as err:
            raise HTTPException(400, str(err)) from err
        c = R.document_received(store.load_case(cid), doc, meta)
    return _pub(c)


@app.post("/api/cases/{cid}/statement")
def upload_statement(cid: str, body: StatementUpload, c: dict = Depends(case_auth)):
    if not body.consent:
        raise HTTPException(400, "consent to analyse the uploaded statement is required")
    assisted = c["mode"] == "assisted"
    if assisted:
        # an operator cannot grant the entrepreneur's consent: nothing is parsed or stored without their code
        with _locks[cid]:
            c = store.load_case(cid)
            verdict = R.check_otp(c, body.otp, "statement_upload")
            store.save_case(c)  # persist the attempt counter / lock / consumption
        if verdict == "locked":
            raise HTTPException(429, "too many wrong codes; code entry is locked for now")
        if verdict == "expired":
            raise HTTPException(403, "that code has expired or was already used; ask for a new code")
        if verdict != "ok":
            raise HTTPException(403, "the entrepreneur's one-time code is required to consent to this statement")
    try:
        fi = uploads.parse_statement_csv(body.csv_text, c["facts"].get("name") or "ACCOUNT HOLDER")
    except uploads.UploadError as err:
        raise HTTPException(400, str(err)) from err
    with _locks[cid]:
        c = R.statement_uploaded(store.load_case(cid), fi, body.filename,
                                 actor="entrepreneur (OTP via operator)" if assisted else "entrepreneur")
    return _pub(c)


@app.post("/api/cases/{cid}/autopilot", dependencies=[Depends(demo_only)])
def autopilot(cid: str, body: Autopilot, c: dict = Depends(case_auth)):
    """Demo fast-forward. Always stops before final approval: only a person approves."""
    with _locks[cid]:
        c = drive(store.load_case(cid), set(body.stop_at or []) | {"approval"})
    return _pub(c)


@app.post("/api/cases/{cid}/consents/{consent_id}/revoke")
def revoke(cid: str, consent_id: str, c: dict = Depends(case_auth)):
    with _locks[cid]:
        try:
            c = R.revoke(store.load_case(cid), consent_id)
        except ValueError as err:
            raise HTTPException(400, str(err)) from err
    return _pub(c)


@app.get("/api/cases/{cid}/audit")
def audit(cid: str, c: dict = Depends(case_auth)):
    return {"verify": store.verify_chain(cid), "log": store.audit_log(cid)}


@app.get("/api/cases/{cid}/dpr.pdf")
def dpr(cid: str, c: dict = Depends(case_auth)):
    if not c.get("analysis") or not any(consent.active(cid, k) for k in R.STATEMENT_CONSENTS):
        raise HTTPException(403, "project report needs an active statement consent")
    return Response(project_report(c), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="DPR-{cid}.pdf"'})


# --------------------------------------------------------------------------- lender
def _summary(a: dict) -> dict:
    p = a.get("package")
    base = {"id": a["id"], "case_id": a["case_id"], "lender": a["lender"], "status": a["status"], "created": a.get("created"),
            "decision": a.get("decision"), "persona": a.get("persona"), "redacted": bool(a.get("redacted")),
            "superseded": bool(a.get("superseded"))}
    if not p:
        return {**base, "applicant": "(withdrawn)", "business": None, "district": None, "activity": None, "amount": None,
                "scheme": None, "band": None, "pd": None, "schedule_type": None, "complete": None, "docs": 0, "pending_items": []}
    pre = [d for d in p["documents"] if not d.get("post_sanction")]
    pending = [d["doc"] for d in pre if d["status"] != "ready"]  # scheduled-offline items are still pending
    return {**base, "applicant": a.get("applicant_name") or p["applicant"].get("name"),
            "business": p["applicant"].get("business_name"), "district": p["applicant"].get("district"),
            "activity": p["applicant"].get("activity"), "amount": p["offer"]["amount"], "scheme": p["offer"]["scheme_short"],
            "band": p["risk"]["band"], "pd": p["risk"]["pd"], "schedule_type": p["schedule_type"],
            "complete": not pending, "pending_items": pending, "docs": len(p["documents"]),
            "attachments": sum(1 for d in p["documents"] if d.get("attachment")),
            "statement": p.get("statement")}


def _shared(a: dict) -> bool:
    return bool(a.get("package")) and bool(consent.active(a["case_id"], "share_with_lender", {"lender": a["lender"]["id"]}))


def _app_for(aid: str, principal: str) -> dict:
    """The file, only if it is addressed to the authenticated lender (404 otherwise: existence is not disclosed)."""
    a = store.get_application(aid)
    if not a or a["lender"]["id"] != principal:
        raise HTTPException(404, "application not found")
    _sweep(a["case_id"])  # expiry is enforced before the lender reads anything
    return store.get_application(aid)


@app.get("/api/lender/applications")
def lender_list(principal: str = Depends(lender_auth)):
    mine = [a for a in store.list_applications() if a["lender"]["id"] == principal]
    for cid in {a["case_id"] for a in mine}:
        _sweep(cid)
    return [_summary(a) for a in store.list_applications() if a["lender"]["id"] == principal]


SHARED_FACTS = ("name", "age", "gender", "district", "state", "area_type", "activity", "sector", "years_in_business",
                "ownership_type", "udyam_registered", "enterprise_class", "annual_turnover")


def _not_superseded(a: dict) -> None:
    if a.get("superseded"):
        raise HTTPException(409, "the entrepreneur changed this file after sending it; the re-approved version will replace it")


def _view(a: dict) -> dict:
    """The lender's frozen view of the approved file (written in the same row as the package at submission)."""
    if not a.get("view"):
        raise HTTPException(409, "this file has no frozen lender view; it must be re-approved and re-sent")
    return a["view"]


@app.get("/api/lender/applications/{aid}")
def lender_get(aid: str, principal: str = Depends(lender_auth)):
    a = _app_for(aid, principal)
    _not_superseded(a)
    if not _shared(a):
        raise HTTPException(403, "entrepreneur's consent to share this file is not active (withdrawn or expired)")
    c = _view(a)
    integrity = {"package_hash_ok": sha256(a["package"]) == a["hash"],
                 "approval_bound": (a.get("approval") or {}).get("hash") == a["hash"],
                 "audit": store.verify_chain(a["case_id"])}
    an = c.get("analysis") or {}
    detail = {"score": c.get("score"), "insights": an.get("insights"), "categories": an.get("categories"),
              "monthly": an.get("monthly"), "informal": an.get("informal_loans"),
              "schemes": [{k: r.get(k) for k in ("id", "short", "name", "kind", "eligibility", "provisional", "availability", "failing", "benefits",
                                                 "citations", "verification", "status_note", "scheme_status", "lender_checks", "caveats")}
                          for r in c.get("schemes", [])],
              "documents": c.get("documents"),
              # only the attachments bound into the approved package, never the case's live upload list
              "attachments": [{"doc": d["doc"], **d["attachment"], "url": f"/api/lender/applications/{aid}/documents/{d['doc']}"}
                              for d in a["package"]["documents"] if d.get("attachment")],
              "offer": c.get("selected_offer"),
              "bureau": (c.get("data") or {}).get("bureau"), "statement_source": ((c.get("data") or {}).get("statement") or {}).get("source", "aa"),
              "facts": {k: (c.get("facts") or {}).get(k) for k in SHARED_FACTS},
              "fact_meta": {k: v for k, v in (c.get("fact_meta") or {}).items() if k in SHARED_FACTS}}
    store.audit(a["case_id"], f"lender:{principal}", "lender.file_viewed", {"application": aid})
    return {**{k: v for k, v in a.items() if k not in ("view", "decision_receipts")}, "summary": _summary(a), "detail": detail,
            "integrity": integrity}


@app.get("/api/lender/applications/{aid}/documents/{doc}")
def lender_document(aid: str, doc: str, principal: str = Depends(lender_auth)):
    a = _app_for(aid, principal)
    _not_superseded(a)
    if not _shared(a):
        raise HTTPException(403, "entrepreneur's consent to share this file is not active (withdrawn or expired)")
    item = next((d for d in a["package"]["documents"] if d["doc"] == doc and d.get("attachment")), None)
    if not item:
        raise HTTPException(404, "no attachment of that type in the approved file")
    att = item["attachment"]
    try:
        data = uploads.load_document(a["case_id"], doc, att["sha256"])
    except FileNotFoundError as err:
        raise HTTPException(410, "the approved file for this document is no longer stored (replaced or erased)") from err
    except uploads.UploadError as err:
        store.audit(a["case_id"], f"lender:{principal}", "lender.document_integrity_failed", {"application": aid, "doc": doc})
        raise HTTPException(409, str(err)) from err
    store.audit(a["case_id"], f"lender:{principal}", "lender.document_accessed",
                {"application": aid, "doc": doc, "sha256": att["sha256"]})
    ext = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}.get(att["mime"], "bin")
    return Response(data, media_type=att["mime"], headers={
        "Content-Disposition": f'attachment; filename="{aid}-{doc}.{ext}"', "X-Content-SHA256": att["sha256"],
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


@app.post("/api/lender/applications/{aid}/decision")
def lender_decide(aid: str, d: Decision, principal: str = Depends(lender_auth)):
    case_id = _app_for(aid, principal)["case_id"]
    with _locks[case_id]:
        # Re-read and re-check INSIDE the case lock: a revocation may have completed since the first lookup.
        a = store.get_application(aid)
        if not a or a["lender"]["id"] != principal:
            raise HTTPException(404, "application not found")
        receipts = a.get("decision_receipts") or {}
        if d.request_id in receipts:  # every decision ever made on this file keeps a receipt
            if receipts[d.request_id] != _decision_fingerprint(d):
                raise HTTPException(409, "request_id was already used for a different request")
            return _summary(a)  # idempotent replay: nothing is recorded twice
        if a["status"] == "withdrawn" or not _shared(a):
            raise HTTPException(409, "application withdrawn by the entrepreneur")
        if a.get("superseded"):
            raise HTTPException(409, "the entrepreneur changed this file after sending it; wait for the re-approved version")
        if a["status"] not in store.DECIDABLE_FROM:
            raise HTTPException(409, f"a final decision ({a['status']}) is already recorded for this file")
        if d.decision == "sanction":
            rec = a["package"]["offer"]["amount"] or 0
            if d.amount is None or d.amount > max(rec, a["package"]["offer"].get("requested") or 0) * 1.0 + 1:
                raise HTTPException(400, "sanction amount required and must not exceed the amount applied for")
        dec = {**d.model_dump(), "id": d.request_id, "ts": store.now(), "file_hash": a["hash"]}
        expected_rev = a.get("rev") or 0
        a["decision"] = dec
        a["decision_receipts"] = {**receipts, d.request_id: _decision_fingerprint(d)}
        a["status"] = {"sanction": "sanctioned", "query": "query", "decline": "declined"}[d.decision]
        # The audit keeps that a decision was made, on which file version, with which bounded reason codes, and a
        # digest of the full record (amount, note, officer), which itself lives only in the erasable lender copy.
        entry = (case_id, f"lender:{principal}", f"lender.{d.decision}",
                 {"decision": d.decision, "decision_id": dec["id"], "reasons": d.reasons, "file_hash": a["hash"],
                  "decision_sha256": sha256(dec), "ts": dec["ts"]})
        if not store.decide_application(a, expected_rev, entry):  # atomic CAS + audit (other workers / processes)
            raise HTTPException(409, "the application changed while deciding (withdrawn, superseded or already decided); reload it")
    # The decision is durable now. Notifying the case is a separate, idempotent step: if it conflicts with a
    # concurrent save it is retried, and anything still missing is applied the next time the case is opened.
    R.deliver_lender_decisions(case_id, lambda: _locks[case_id])
    return _summary(a)


@app.get("/api/lender/applications/{aid}/memo.pdf")
def memo(aid: str, principal: str = Depends(lender_auth)):
    a = _app_for(aid, principal)
    _not_superseded(a)
    if not _shared(a):
        raise HTTPException(403, "entrepreneur's consent to share this file is not active")
    return Response(credit_memo(_view(a), a), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="credit-memo-{aid}.pdf"'})


@app.get("/api/lender/applications/{aid}/dpr.pdf")
def lender_dpr(aid: str, principal: str = Depends(lender_auth)):
    a = _app_for(aid, principal)
    _not_superseded(a)
    if not _shared(a):
        raise HTTPException(403, "entrepreneur's consent to share this file is not active")
    c = _view(a)
    if not c.get("analysis"):
        raise HTTPException(403, "entrepreneur's consent to share this file is not active")
    return Response(project_report(c), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="DPR-{aid}.pdf"'})


@app.get("/api/lenders")
def lenders():
    return integrations.LENDERS


# --------------------------------------------------------------------------- governance (public, no personal data)
@app.get("/api/governance/model")
def model_report():
    rep = json.loads((ARTIFACTS / "model_report.json").read_text(encoding="utf-8"))
    sc = json.loads((ARTIFACTS / "scorecard.json").read_text(encoding="utf-8"))
    sc.pop("bootstrap", None)
    return {"report": rep, "scorecard": sc}


@app.get("/api/governance/schemes")
def schemes():
    return {"schemes": kb_summary(), "sources": list(load_sources().values())}


# --------------------------------------------------------------------------- federation / BC cohort screening
@app.post("/api/federation/screen")
def screen(n: int = 40, seed: int = 5):
    """Screen a synthetic SHG-federation member list against every scheme.
    Profile facts only, no financial data; so no data-pull consent is involved."""
    n = max(1, min(n, 200))
    rnd = random.Random(seed)
    acts = [("tailoring", "manufacturing", "tailor"), ("dairy", "allied_agri", "none"), ("leaf_plates", "manufacturing", "none"),
            ("food_processing", "manufacturing", "none"), ("retail", "trading", "none"), ("street_food", "trading", "none")]
    members, totals = [], {}
    names = ["Sushila", "Phulmani", "Budhni", "Sarita", "Rita", "Babita", "Mangri", "Sukhmati", "Anita", "Kiran", "Lalita", "Meera"]
    for i in range(n):
        act, sector, trade = rnd.choice(acts)
        f = {"age": rnd.randint(21, 58), "gender": "female", "area_type": "rural",
             "social_category": rnd.choice(["st", "st", "sc", "obc", "general"]), "sector": sector, "activity": act,
             "ownership_type": "individual", "is_new_unit": rnd.random() < 0.35, "udyam_registered": rnd.random() < 0.15,
             "loan_amount_sought": rnd.choice([30000, 50000, 100000, 200000, 300000]), "is_defaulter": False,
             "prior_mudra_tarun_repaid": False, "availed_pmegp": False, "outstanding_mudra_or_svanidhi": rnd.random() < 0.1,
             "vishwakarma_trade": trade if rnd.random() < 0.7 else "none", "is_traditional_family_trade": rnd.random() < 0.6,
             "family_member_in_govt_service": rnd.random() < 0.05, "family_member_registered_pmv": False,
             "availed_other_govt_subsidy": False, "family_member_availed_pmegp": False, "owns_milch_animals": act == "dairy",
             "is_street_vendor": act == "street_food", "has_vending_certificate_or_lor": False,
             "education": rnd.choice(["below_8", "8th", "10th"]), "is_minority": False, "is_ex_serviceman": False, "is_pwd": False,
             "is_aspirational_district": True, "annual_turnover": rnd.randint(150000, 900000),
             "plant_investment": rnd.randint(20000, 400000), "has_b2b_buyers": rnd.random() < 0.2, "prior_scheme_unit": "none"}
        f["project_cost"] = int(f["loan_amount_sought"] * 1.1)
        res = evaluate_all(f)
        el = [r for r in res if r["eligibility"] == "eligible" and r["kind"] not in ("entitlement", "guarantee")
              and r["availability"] == "available"]
        for r in el:
            totals[r["short"]] = totals.get(r["short"], 0) + 1
        members.append({"id": f"M{i + 1:03d}", "name": f"{rnd.choice(names)} {rnd.choice(['Munda', 'Oraon', 'Devi', 'Kumari', 'Toppo'])}",
                        "activity": act, "need": f["loan_amount_sought"], "eligible": [r["short"] for r in el],
                        "value": round(sum(r["est_value"] for r in el[:1])),
                        "unlock": "Udyam" if not f["udyam_registered"] and sector != "allied_agri" else None})
    return {"members": members, "by_scheme": totals, "n": n,
            "with_any": sum(1 for m in members if m["eligible"]),
            "est_annual_value": sum(m["value"] for m in members),
            "note": "Synthetic member list; profile-only screening (no financial data, no consent needed). "
                    "'Eligible' means scheme conditions are met, lenders still appraise."}


# --------------------------------------------------------------------------- demo-only
def _seed() -> list[str]:
    made = []
    for pid in ("ramesh", "lakshmamma", "shg", "mohan"):
        c = R.new_case(pid, "en", chaos=False)
        c["token_hash"] = sha256(os.urandom(16).hex().encode())  # seeded cases are not reachable by any client
        c = drive(c)  # tests/seed only: the demo actor approves synthetic files; recorded as "demo-autopilot"
        made.append(c["id"])
    return made


@app.post("/api/demo/seed", dependencies=[Depends(demo_only)])
def seed(reset: bool = False):
    if reset:
        store.reset()
    return {"seeded": _seed()}


@app.get("/api/demo/sample-statement/{persona}.csv", dependencies=[Depends(demo_only)])
def sample_statement(persona: str):
    if persona not in PERSONAS:
        raise HTTPException(404)
    return PlainTextResponse(uploads.statement_to_csv(statement(persona)), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="sample-statement-{persona}.csv"'})


# --------------------------------------------------------------------------- frontend
DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = (DIST / path).resolve()
        if path and f.is_file() and DIST.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
else:
    @app.get("/")
    def root():
        return JSONResponse({"message": "Saakh API running. Build the frontend (frontend/) to serve the UI here."})
