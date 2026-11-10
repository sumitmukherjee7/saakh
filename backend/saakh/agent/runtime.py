"""Saakh agent runtime: case memory, a goal-driven planner, guarded tools,
failure recovery and human-in-the-loop checkpoints.

The planner pursues the entrepreneur's goal ("get the right credit, on good
terms, with a complete file") through these goals, re-evaluated after every
event, so the agent resumes correctly after interruptions, new facts,
consent revocation or a lender query:

  intake → consent → fetch data (retry/fallback) → analyse cash flow →
  evaluate schemes → offer unlock actions → ask high-value questions →
  structure offers (entrepreneur chooses) → plan documents (uploads) →
  generate DPR → assemble file → ENTREPRENEUR APPROVAL → submit → track lender

Checkpoints where the agent always stops for the human: every consent, every
outward action (registrations), the choice of offer, final approval of the
exact file, and any lender query.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from .. import consent, integrations, store
from ..cashflow.analyze import analyse
from ..cashflow.sizing import structure
from ..data.personas import PERSONAS
from ..docs import planner as docplan
from ..facts import FACTS, classify_msme, coerce, derive, fact_public
from ..config import PRODUCTION
from ..risk.scorecard import POLICY_PD, release_status
from ..schemes import benefits as B
from ..schemes.engine import evaluate_all, explain, unlock_actions, unlock_prerequisites
from ..schemes.questions import next_question, rank_questions
from ..util import inr, sha256
from . import nlu
from .tools import GuardError, call, tool

MAX_QUESTIONS = 10
LOAN_KINDS = ("loan", "subsidy_loan", "subsidised_loan", "credit_line", "group_loan")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def tr(en: str, hi: str) -> dict:
    return {"en": en, "hi": hi}


def say(case: dict, en: str, hi: str, card: dict | None = None, role: str = "agent", src: list[str] | None = None) -> None:
    m = {"id": uuid.uuid4().hex[:10], "role": role, "ts": store.now(), "text": tr(en, hi), "card": card}
    if src:
        m["src"] = src  # data groups this message was built from (for redaction on revocation/expiry)
    case["messages"].append(m)


def note(case: dict, kind: str, en: str, **extra) -> None:
    case["trace"].append({"ts": store.now(), "kind": kind, "name": en, **extra})


def set_fact(case: dict, key: str, value: Any, source: str, evidence: str | None = None) -> None:
    value = coerce(key, value)
    if case["facts"].get(key) != value:
        case["facts_version"] += 1
    case["facts"][key] = value
    case["fact_meta"][key] = {"source": source, "evidence": evidence, "ts": store.now()}


def _persona(case: dict) -> dict:
    return PERSONAS[case["persona"]]


# --------------------------------------------------------------------------- #
# tools (registered with the guard)
# --------------------------------------------------------------------------- #
@tool("fetch_ekyc", "Fetch identity & address via DigiLocker e-KYC", needs_consent=["ekyc"], external=True, simulated=True)
def _t_ekyc(case):
    r = integrations.ekyc(case["id"], case["persona"])
    for k, v in r["facts"].items():
        if k in FACTS:
            set_fact(case, k, v, "ekyc", r["source"])
    case["data"]["ekyc"] = {"ref": r["ref"], "source": r["source"], "simulated": True}
    return {"summary": f"{r['facts']['name']}, {r['facts']['age']}y, {r['facts']['district']}"}


@tool("fetch_bank_statement", "Fetch 12-month DEPOSIT statement via Account Aggregator", needs_consent=["bank_statement"],
      external=True, simulated=True)
def _t_aa(case):
    r = integrations.aa_fetch(case["id"], case["persona"], chaos=case.get("chaos", True))
    acc = r["fi"]["account"]
    case["data"]["statement"] = {"session": r["sessionId"], "source": r["source"], "simulated": True,
                                 "txns": len(acc["transactions"]["transaction"]), "masked": acc["maskedAccNumber"],
                                 "branch": acc["summary"]["branch"], "from": acc["transactions"]["startDate"],
                                 "to": acc["transactions"]["endDate"]}
    return {"summary": f"{case['data']['statement']['txns']} transactions, {acc['maskedAccNumber']}"}


@tool("fetch_bureau", "Soft-pull credit bureau report", needs_consent=["bureau"], external=True, simulated=True)
def _t_bureau(case):
    r = integrations.bureau(case["id"], case["persona"])
    for k, v in r["facts"].items():
        set_fact(case, k, v, "bureau", r["source"])
    case["data"]["bureau"] = {"score": r["report"]["score"], "loans": r["report"]["loans"], "simulated": True}
    return {"summary": f"score {r['report']['score'] or 'NTC (new to credit)'}, {len(r['report']['loans'])} active loans"}


@tool("lookup_udyam", "Look up Udyam registration", needs_consent=["udyam"], external=True, simulated=True)
def _t_udyam(case):
    r = integrations.udyam_lookup(case["id"], case["persona"])
    for k, v in r["facts"].items():
        set_fact(case, k, v, "udyam", r["source"])
    case["data"]["udyam"] = {**r["record"], "simulated": True}
    return {"summary": r["record"].get("udyam_number") or "not registered"}


STATEMENT_CONSENTS = ["bank_statement", "statement_upload"]


def _statement(case: dict) -> dict:
    """The statement this case is analysed from: re-fetched from the (simulated)
    AA under consent, or the file the entrepreneur uploaded (stored until revoked)."""
    meta = case["data"].get("statement") or {}
    if meta.get("source") == "upload":
        fi = store.get_statement(case["id"])
        if fi is None:
            raise GuardError("uploaded statement no longer available (consent revoked)")
        return fi
    return integrations.aa_fetch(case["id"], case["persona"], chaos=False)["fi"]


@tool("analyze_cashflow", "Categorise transactions, detect informal debt, compute features", needs_any_consent=STATEMENT_CONSENTS)
def _t_analyse(case):
    st = _statement(case)  # processed in memory; AA data is never persisted
    a = analyse(st, case["facts"].get("informal_outstanding"), case["facts"].get("activity"))
    a.pop("txn_categories", None)
    case["analysis"] = a
    src = "statement_upload" if (case["data"].get("statement") or {}).get("source") == "upload" else "aa"
    for k, v in a["derived_facts"].items():
        if case["facts"].get(k) is None:
            set_fact(case, k, v, src, a["evidence"].get(k))
    if "owns_milch_animals" in a["evidence"] and case["facts"].get("owns_milch_animals") is None:
        set_fact(case, "owns_milch_animals", True, f"{src}-inferred", a["evidence"]["owns_milch_animals"])
    return {"summary": f"avg business inflow {inr(sum(a['monthly']['biz_in']) / max(len(a['monthly']['biz_in']), 1))}/month; "
                       f"{len(a['informal_loans'])} informal loan pattern(s); {a['monthly']['bounces']} bounce(s)"}


@tool("evaluate_schemes", "Evaluate all schemes with the cited rule engine")
def _t_schemes(case):
    res = evaluate_all(case["facts"])
    case["schemes"] = res
    case["unlocks"] = unlock_actions(case["facts"])
    case["schemes_version"] = case["facts_version"]
    n = {k: sum(1 for r in res if r["eligibility"] == k) for k in ("eligible", "needs_info", "not_eligible", "lapsed")}
    return {"summary": f"{n['eligible']} eligible, {n['needs_info']} need info, {n['not_eligible']} not eligible"}


@tool("score_and_structure", "Score risk and structure loan offers", needs_any_consent=STATEMENT_CONSENTS)
def _t_offers(case):
    f = case["facts"]
    plan = B.best_financing_plan(case["schemes"], f)
    case["financing_plan"] = plan
    offers = []
    cands = ([plan["primary"]] + plan["alternatives"][:2]) if plan else []
    requested = f.get("loan_amount_sought") or 100000
    by_id = {r["id"]: r for r in case["schemes"]}
    for sid in cands:
        r = by_id[sid]
        req = requested
        subsidy = 0
        if sid == "pmegp":
            rates = B.pmegp_rates(derive(f)) or (0.25, 0.1)
            pc = f.get("project_cost") or requested
            subsidy = round(rates[0] * pc)
            req = round(pc * (1 - rates[1]))
        elif sid == "pmegp_upgrade":
            pc = f.get("project_cost") or requested
            subsidy = round((0.20 if f.get("is_special_region") else 0.15) * pc)
            req = round(pc * 0.90)
        # CGTMSE is only ever a *possibility* the lender may pursue, never assumed in the offer
        cg = "cgtmse" in (plan or {}).get("addons", []) and sid in ("pmmy", "pmegp", "pmegp_upgrade")
        st = structure(case["analysis"], sid, req, f.get("gender"), f.get("informal_outstanding"), with_cgtmse=cg,
                       uplift=(case.get("project") or {}).get("uplift", 0.0))
        grants = [b for b in r["benefits"] if b.get("kind") == "grant"]
        offers.append({
            "index": len(offers), "scheme_id": sid, "scheme_short": r["short"], "scheme_name": r["name"],
            "requested": st["need"], "amount": st["recommended"], "rate": st["rate"], "tenure": st["tenure"],
            "binding": st["binding_constraint"], "why": st["why"], "limits": st["limits"],
            "risk": st["risk_at_recommended"], "risk_at_request": st["risk_at_request"],
            "seasonal": st["seasonal"], "flat": st["flat"], "expected_disposable": st["expected_disposable"],
            "kfs": st["kfs"], "refinance": st["refinance"], "uplift": st["uplift"],
            "subsidy": subsidy, "grants": grants, "cgtmse_possible": cg, "start_month": st["start_month"],
            "benefits": r["benefits"], "est_value": r["est_value"],
            "provisional": r.get("provisional") or [],  # conditions an agency still has to verify
        })
    case["offers"] = offers
    from ..risk.scorecard import score as score_fn
    feats = dict(case["analysis"]["features"])
    best = next((o for o in offers if o["amount"] > 0), offers[0] if offers else None)
    from ..util import annuity_emi
    amt = best["amount"] if best and best["amount"] > 0 else requested
    rate = best["rate"] if best else 0.12
    ten = best["tenure"] if best else 36
    feats["proposed_dsr"] = annuity_emi(amt, rate, ten) / max(sum(case["analysis"]["monthly"]["biz_in"]) / 12, 1)
    case["score"] = score_fn(feats)
    case["not_now"] = not any(o["amount"] > 0 for o in offers)
    return {"summary": f"{len(offers)} offer(s); simulated risk {case['score']['pd'] * 100:.1f}% band {case['score']['band']}"}


@tool("register_udyam", "Register the enterprise on Udyam", needs_consent=["ekyc"], needs_go_ahead="register_udyam",
      external=True, simulated=True)
def _t_reg_udyam(case):
    cls = classify_msme(case["facts"].get("plant_investment"), case["facts"].get("annual_turnover"))
    if cls is None:
        raise GuardError("register_udyam: investment and turnover must both be known to classify the enterprise")
    r = integrations.udyam_register(case["id"], case["persona"], case["facts"], cls)
    set_fact(case, "udyam_registered", True, "udyam_portal", r["source"])  # own registration, not the lookup consent
    set_fact(case, "enterprise_class", cls, "udyam_portal", f"{r['source']}, declared investment & turnover")
    case["data"]["udyam"] = {"udyam_registered": True, "udyam_number": r["udyam_number"], "simulated": True,
                             "registered_by_saakh": True}
    return {"summary": r["udyam_number"]}


@tool("apply_lor", "Apply for PM SVANidhi Letter of Recommendation", needs_go_ahead="apply_lor", external=True, simulated=True)
def _t_lor(case):
    r = integrations.svanidhi_lor(case["id"], case["persona"])
    set_fact(case, "has_vending_certificate_or_lor", True, "svanidhi", f"{r['lor_ref']} (simulated instant ULB approval)")
    case["data"]["lor"] = r
    return {"summary": r["lor_ref"]}


@tool("plan_documents", "Compute the minimum-effort document set")
def _t_docs(case):
    o = case["selected_offer"]
    schemes = [o["scheme_id"]] + (["cgtmse"] if o.get("cgtmse_possible") else [])
    ctx = {"ekyc": bool(case["data"].get("ekyc") and not case["data"]["ekyc"].get("manual")),
           "bank_statement": bool(case["data"].get("statement")), "bureau": bool(case["data"].get("bureau")),
           "uploads": case.get("uploads", {}),
           "milk_union_seen": "owns_milch_animals" in (case["analysis"] or {}).get("evidence", {})}
    case["documents"] = docplan.plan(case["facts"], schemes, ctx, set(case.get("uploads", {})))
    c = case["documents"]["counts"]
    return {"summary": f"{c['total']} docs: {c['auto']} auto, {c['generated']} generated, {c['you_do']} by you"}


@tool("generate_project_report", "Generate the project report (DPR) PDF", needs_any_consent=STATEMENT_CONSENTS)
def _t_dpr(case):
    from ..docs.pdf import project_report
    pdf = project_report(case)
    case["dpr"] = {"ready": True, "bytes": len(pdf), "hash": sha256(pdf)}
    return {"summary": f"DPR {len(pdf) // 1024} KB"}


@tool("assemble_application", "Assemble the lender-ready application package")
def _t_assemble(case):
    f = case["facts"]
    lender = (case.get("application") or {}).get("lender") or (integrations.lenders_for(f.get("state")) or integrations.LENDERS)[0]
    pkg = {
        "applicant": {k: f.get(k) for k in ("name", "business_name", "district", "state", "activity", "sector",
                                            "ownership_type", "years_in_business", "udyam_registered")},
        "offer": {k: case["selected_offer"].get(k) for k in ("scheme_id", "scheme_short", "amount", "requested", "rate", "tenure",
                                                              "subsidy", "cgtmse_possible", "provisional")},
        "schedule_type": case["selected_offer"]["schedule_type"],
        "schedule": case["selected_offer"]["schedule"],
        "risk": {k: case["score"][k] for k in ("pd", "pd_low", "pd_high", "band", "score", "model_version")},
        "reasons": [r["feature"] for r in case["score"]["reason_codes"]],
        "eligibility": [{"id": r["id"], "eligibility": r["eligibility"],
                         "cites": [c["source"] + ":" + c["loc"] for c in r["citations"]]} for r in case["schemes"]],
        # the approval hash binds the actual uploaded bytes via their SHA-256
        "documents": [{"doc": d["doc"], "how": d["how"], "status": d["status"], "post_sanction": d["post_sanction"],
                       "scheduled_offline": d["doc"] in case["scheduled"],
                       "attachment": ({k: case["uploads"][d["doc"]][k] for k in ("sha256", "bytes", "mime")}
                                      if d["doc"] in case.get("uploads", {}) else None)}
                      for d in case["documents"]["items"]],
        "statement": {k: (case["data"].get("statement") or {}).get(k) for k in ("source", "from", "to", "txns", "simulated")},
        "cashflow": {k: case["analysis"]["monthly"][k] for k in ("months", "biz_in", "biz_out", "emi_out", "informal_out")},
        "features": case["analysis"]["features"],
        "disputes": [{"fact": k, "source": m.get("source"), "claimed": m["dispute"]["claimed"], "reason": m["dispute"]["reason"]}
                     for k, m in sorted(case["fact_meta"].items()) if (m.get("dispute") or {}).get("status") == "open"],
        "dpr_hash": (case.get("dpr") or {}).get("hash"),
    }
    h = sha256(pkg)
    prev = case.get("application") or {}
    case["application"] = {"id": prev.get("id") or "APP-" + uuid.uuid4().hex[:8].upper(), "lender": lender,
                           "package": pkg, "hash": h, "created": prev.get("created") or store.now(),
                           "status": "draft" if not prev.get("status") else prev["status"]}
    if case.get("approval") and case["approval"].get("hash") != h:
        note(case, "guard", "Application changed after approval, previous approval invalidated", status="blocked")
        case["approval"] = None
    return {"summary": f"package {h[:12]}… for {lender['name']}"}


LENDER_FACTS = ("name", "age", "gender", "district", "state", "area_type", "activity", "sector", "years_in_business",
                "ownership_type", "udyam_registered", "enterprise_class", "annual_turnover", "business_name", "project_cost")
LENDER_SCHEME_KEYS = ("id", "short", "name", "kind", "eligibility", "provisional", "availability", "failing", "benefits",
                      "citations", "verification", "status_note", "scheme_status", "lender_checks", "caveats")


def lender_snapshot(case: dict) -> dict:
    """Everything the lender may see, frozen at the moment the entrepreneur approved the file. Lender routes
    read only this (never the live case), so they cannot mix the approved file with later, unapproved changes."""
    import copy
    an = copy.deepcopy(case.get("analysis") or {})
    an.pop("txn_categories", None)
    data = case.get("data") or {}
    return copy.deepcopy({
        "id": case["id"], "persona": case.get("persona"), "lang": case.get("lang"),
        "facts": {k: (case.get("facts") or {}).get(k) for k in LENDER_FACTS},
        "fact_meta": {k: v for k, v in (case.get("fact_meta") or {}).items() if k in LENDER_FACTS},
        "analysis": an, "score": case.get("score"), "documents": case.get("documents"),
        "schemes": [{k: r.get(k) for k in LENDER_SCHEME_KEYS} for r in case.get("schemes") or []],
        "selected_offer": case.get("selected_offer"), "offers": [case["selected_offer"]] if case.get("selected_offer") else [],
        "project": case.get("project"), "uploads": case.get("uploads"),
        "data": {"statement": data.get("statement"), "bureau": data.get("bureau")},
    })


@tool("submit_application", "Submit the approved file to the lender's LOS", needs_approval=True, external=True, simulated=True)
def _t_submit(case):
    app = case["application"]
    key = integrations.los_key(app)  # application id + lender + approved file version
    case["submission_intent"] = {"key": key, "ts": store.now()}
    store.save_case(case)  # record intent before the external call, so a crash can be resumed safely
    r = integrations.los_submit(app, idempotency_key=key)
    consents = [consent.public(c) for c in store.case_consents(case["id"]) if c["status"] == "ACTIVE"]
    prior = store.get_application(app["id"]) or {}
    record = {"view": lender_snapshot(case), "decision_receipts": prior.get("decision_receipts") or {},
              "id": app["id"], "case_id": case["id"], "lender": app["lender"], "status": "submitted",
              "created": store.now(), "package": app["package"], "hash": app["hash"], "approval": case["approval"],
              "consents": consents, "los_ref": r["los_ref"], "audit_head": store.verify_chain(case["id"]).get("head"),
              "persona": case["persona"], "decision": None,
              "applicant_name": case["facts"].get("name"), "lang": case["lang"]}
    store.put_application(record)
    app["status"] = "submitted"
    case["submission"] = {"los_ref": r["los_ref"], "ts": store.now(), "simulated": True, "key": key}
    case.pop("submission_intent", None)
    return {"summary": f"{r['los_ref']} at {app['lender']['name']}" + (" (replayed, not duplicated)" if r.get("replayed") else "")}


# --------------------------------------------------------------------------- #
# case lifecycle
# --------------------------------------------------------------------------- #
def new_case(persona: str, lang: str = "hi", mode: str = "self", chaos: bool = True) -> dict:
    p = PERSONAS[persona]
    case = {
        "id": "C-" + uuid.uuid4().hex[:8].upper(), "created": store.now(), "persona": persona, "lang": lang, "mode": mode,
        "chaos": chaos, "facts": {}, "fact_meta": {}, "facts_version": 0, "schemes_version": -1,
        "data": {}, "analysis": None, "schemes": [], "unlocks": [], "offers": [], "selected_offer": None,
        "score": None, "documents": None, "uploaded": [], "scheduled": [], "application": None, "approval": None,
        "submission": None, "messages": [], "trace": [], "pending": None, "asked": [], "skipped": [], "go_ahead": {},
        "offered_actions": [], "intake_done": False, "consents_requested": False, "project": p["project"],
        "lender_events": [], "closed": False, "uploads": {}, "processed_events": [],
        # assisted mode: a one-time code the entrepreneur reads from their own phone (simulated SMS)
        "otp_challenge": None,  # assisted mode: one short-lived, single-use code per consequential step
    }
    store.audit(case["id"], "system", "case.created", {"persona": persona, "mode": mode})
    if mode == "assisted":
        say(case, "Namaste! I am Saakh. You're helping an entrepreneur at a JanAI Café. Ask them what they need the money for "
                  "and type or speak it below, consents will still be approved by the entrepreneur with an OTP on their own phone.",
            "नमस्ते! मैं साख हूँ। आप JanAI कैफ़े पर एक उद्यमी की मदद कर रहे हैं। उनसे पूछें कि पैसे किस काम के लिए चाहिए और नीचे लिखें या बोलें, "
            "सहमति फिर भी उद्यमी अपने फ़ोन पर OTP से देंगे।")
    else:
        say(case, "Namaste! I am Saakh; I find the government schemes and the loan that fit your business, "
                  "and prepare a complete file for the bank. Nothing is shared or submitted without your approval. "
                  "Tell me in your own words: what do you need money for, and roughly how much?",
            "नमस्ते! मैं साख हूँ, मैं आपके व्यवसाय के लिए सही सरकारी योजनाएँ और ऋण ढूँढता हूँ, और बैंक के लिए पूरी फ़ाइल तैयार करता हूँ। "
            "आपकी मंज़ूरी के बिना कुछ भी साझा या जमा नहीं होगा। अपने शब्दों में बताइए: पैसे किस काम के लिए और लगभग कितने चाहिए?",
            card={"type": "suggestion", "text": p["utterance"]})
    case["pending"] = {"type": "intake"}
    store.save_case(case)
    return case


def _askable(case: dict) -> set[str]:
    have = case["data"]
    unavailable = set()
    if not have.get("ekyc") or have["ekyc"].get("manual"):
        unavailable.add("ekyc")
    if not have.get("bureau"):
        unavailable.add("bureau")
    if not have.get("udyam"):
        unavailable.add("udyam")
    if not have.get("statement"):
        unavailable.add("aa")
    return {k for k, f in FACTS.items() if f.question and (f.source in ("user", "derived") or f.source in unavailable)}


def _consent_status(case: dict, kind: str) -> str | None:
    arts = [a for a in store.case_consents(case["id"]) if a["kind"] == kind]
    return arts[-1]["status"] if arts else None


def _question_card(case: dict, key: str, ranked: dict | None) -> dict:
    fp = fact_public(key)
    why = fp["why"]
    if key == "availed_other_govt_subsidy":
        flag = next((fl for fl in (case["analysis"] or {}).get("flags", []) if fl["fact"] == key), None)
        if flag:
            why = flag["note"]
    if key == "informal_outstanding" and case["analysis"] and case["analysis"]["informal_loans"]:
        il = case["analysis"]["informal_loans"][0]
        why = tr(f"Seen: {il['count']} {il['cadence']} payments of {inr(il['amount'])} to {il['counterparty']}.",
                 f"दिखा: {il['counterparty']} को {inr(il['amount'])} के {il['count']} भुगतान।")
    return {"type": "question", "fact": fp, "why": why, "affects": (ranked or {}).get("affects", []),
            "voi": (ranked or {}).get("voi"), "n": len(case["asked"]) + 1}


def _call_retry(case: dict, name: str, attempts: int = 3):
    """Bounded retry with backoff for transient failures of an external (simulated) system."""
    for i in range(1, attempts + 1):
        try:
            return call(case, name, case["trace"])
        except integrations.TransientError as e:
            if i == attempts:
                raise
            note(case, "retry", f"{name}: {e}, retrying (attempt {i + 1}/{attempts})", status="retry")
            time.sleep(min(0.2 * 2 ** (i - 1), 0.6))


def _step(case: dict) -> bool:
    """Advance one goal. Return True if progress was made without needing the human."""
    if case["closed"]:
        return False
    if not case["intake_done"]:
        case["pending"] = {"type": "intake"}
        return False

    # ---- consent (one screen, separate artefacts, optional ones can be declined)
    if not case["consents_requested"]:
        customer = f"{case['persona']}@saakh-aa"
        arts = [consent.request(case["id"], k, customer) for k in ("ekyc", "bank_statement", "bureau", "udyam")]
        case["consents_requested"] = True
        note(case, "plan", "Requested 4 purpose-bound consents (DigiLocker, AA, bureau, Udyam)")
        say(case, "To check schemes and prepare your file I need your permission to read the data below. "
                  "Each permission is for one purpose only, expires automatically, and you can withdraw it any time.",
            "योजनाएँ जाँचने और फ़ाइल बनाने के लिए मुझे नीचे दी गई जानकारी पढ़ने की अनुमति चाहिए। हर अनुमति केवल एक उद्देश्य के लिए है, "
            "अपने आप समाप्त होती है, और आप इसे कभी भी वापस ले सकते हैं।",
            card={"type": "consent", "consents": [consent.public(a) for a in arts], "otp_required": case["mode"] == "assisted"})
        case["pending"] = {"type": "consent", "ids": [a["consentId"] for a in arts]}
        ensure_otp(case, "consent")
        return False

    d = case["data"]
    # ---- identity
    if not d.get("ekyc"):
        if _consent_status(case, "ekyc") == "ACTIVE":
            _call_retry(case, "fetch_ekyc")
        else:
            d["ekyc"] = {"manual": True}
            note(case, "fallback", "e-KYC declined, will ask identity facts directly (assisted verification at branch)")
        return True
    # ---- statement with retry & fallback
    if not d.get("statement"):
        if _consent_status(case, "bank_statement") == "ACTIVE":
            for attempt in range(1, 4):
                try:
                    call(case, "fetch_bank_statement", case["trace"])
                    if attempt > 1:
                        say(case, f"The bank's data service was slow; I retried and got your statement (attempt {attempt}).",
                            f"बैंक की डेटा सेवा धीमी थी, मैंने दोबारा कोशिश की और आपका विवरण मिल गया (प्रयास {attempt})।")
                    break
                except integrations.TransientError as e:
                    wait = 0.5 * 2 ** (attempt - 1)
                    note(case, "retry", f"Account Aggregator: {e}, retrying in {wait:.1f}s (attempt {attempt + 1}/3)", status="retry")
                    time.sleep(min(wait, 0.6))
            else:
                case["pending"] = {"type": "fallback_statement"}
                ensure_otp(case, "statement_upload")
                say(case, "I could not reach your bank through the Account Aggregator. You can upload your statement as a CSV file, or get help at a JanAI Café.",
                    "अकाउंट एग्रीगेटर से बैंक तक नहीं पहुँच सका। आप अपना विवरण CSV फ़ाइल के रूप में अपलोड कर सकते हैं, या JanAI कैफ़े पर मदद ले सकते हैं।",
                    card={"type": "fallback_statement"})
                return False
            return True
        case["pending"] = {"type": "fallback_statement"}
        ensure_otp(case, "statement_upload")
        if not any(m.get("card", {}) and m["card"].get("type") == "fallback_statement" for m in case["messages"][-3:]):
            say(case, "Without a bank statement I can't show the bank your real income. You can upload your statement as a CSV file "
                      "(it is analysed only for this application), or visit a JanAI Café.",
                "बैंक विवरण के बिना मैं बैंक को आपकी असली आय नहीं दिखा सकता। आप अपना विवरण CSV फ़ाइल के रूप में अपलोड कर सकते हैं "
                "(केवल इसी आवेदन के लिए विश्लेषण होगा), या JanAI कैफ़े जाएँ।", card={"type": "fallback_statement"})
        return False
    if not d.get("bureau") and _consent_status(case, "bureau") == "ACTIVE":
        _call_retry(case, "fetch_bureau")
        return True
    if not d.get("udyam") and _consent_status(case, "udyam") == "ACTIVE":
        _call_retry(case, "lookup_udyam")
        return True

    # ---- analysis
    if not case["analysis"]:
        call(case, "analyze_cashflow", case["trace"])
        a = case["analysis"]
        meta = case["data"].get("statement") or {}
        n = a["data_quality"]["months"]
        src_en = "the statement you uploaded" if meta.get("source") == "upload" else "your account (via the Account Aggregator)"
        src_hi = "आपके अपलोड किए विवरण" if meta.get("source") == "upload" else "आपके खाते (अकाउंट एग्रीगेटर से)"
        short_en = "" if n >= 12 else f" Only {n} months: seasonal patterns and yearly figures are extrapolated, treat them with care."
        short_hi = "" if n >= 12 else f" केवल {n} महीने: मौसमी पैटर्न और सालाना आँकड़े अनुमानित हैं, सावधानी से देखें।"
        say(case, f"I read {n} months ({a['data_quality']['first']} to {a['data_quality']['last']}) from {src_en}. "
                  f"Here is what it says about your business.{short_en}",
            f"मैंने {src_hi} के {n} महीने ({a['data_quality']['first']} से {a['data_quality']['last']}) पढ़े। "
            f"आपके व्यवसाय के बारे में यह पता चलता है।{short_hi}",
            card={"type": "insights", "insights": a["insights"], "monthly": a["monthly"], "categories": a["categories"][:8],
                  "informal": a["informal_loans"], "simulated": bool(meta.get("simulated", True)),
                  "source": meta.get("source", "aa"), "months": n})
        return True

    # ---- schemes (re-evaluate whenever facts changed)
    if case["schemes_version"] != case["facts_version"]:
        first = not case["schemes"]
        call(case, "evaluate_schemes", case["trace"])
        if first:
            el = [r for r in case["schemes"] if r["eligibility"] == "eligible"]
            prov = [r["short"] for r in el if r.get("provisional")]
            pen = f" ({', '.join(prov)} provisional until the agency verifies your declaration)" if prov else ""
            phi = f" ({', '.join(prov)}, एजेंसी के सत्यापन तक अस्थायी)" if prov else ""
            say(case, f"I checked {len(case['schemes'])} schemes against their official rules. "
                      f"{len(el)} already fit{pen}; a few more depend on answers only you know; I'll ask only what matters.",
                f"मैंने {len(case['schemes'])} योजनाओं को उनके आधिकारिक नियमों से जाँचा। {len(el)} पहले से उपयुक्त हैं{phi}; "
                f"कुछ आपके जवाबों पर निर्भर हैं, मैं केवल ज़रूरी सवाल पूछूँगा।",
                card={"type": "schemes"})
        return True

    # ---- outward actions the entrepreneur said yes to
    if case["go_ahead"].get("register_udyam") and not case["facts"].get("udyam_registered"):
        if case["facts"].get("plant_investment") is None or case["facts"].get("annual_turnover") is None:
            if "plant_investment" not in case["asked"]:
                case["asked"].append("plant_investment")
                fp = FACTS["plant_investment"]
                say(case, fp.question["en"] + " (Udyam needs it to classify your enterprise.)",
                    fp.question["hi"] + " (उद्यम श्रेणी तय करने के लिए ज़रूरी।)", card=_question_card(case, "plant_investment", None))
                case["pending"] = {"type": "question", "fact": "plant_investment"}
                return False
        else:
            call(case, "register_udyam", case["trace"])
            cls = case["facts"]["enterprise_class"]
            num = case["data"]["udyam"]["udyam_number"]
            say(case, f"Registered (simulated): {num}, classified as a {cls} enterprise from the investment and turnover you declared. "
                      "Udyam is one condition for CGTMSE, whether a loan gets CGTMSE cover is decided by your lender, which must be a "
                      "CGTMSE member and appraises the loan.",
                f"पंजीकृत (सिम्युलेटेड): {num}, आपके बताए निवेश और कारोबार से {cls} उद्यम। उद्यम CGTMSE की एक शर्त है, "
                "ऋण पर CGTMSE गारंटी मिलेगी या नहीं, यह आपका बैंक तय करता है, जो CGTMSE सदस्य होना चाहिए और ऋण का आकलन करता है।")
            return True
    if case["go_ahead"].get("apply_lor") and not case["facts"].get("has_vending_certificate_or_lor"):
        call(case, "apply_lor", case["trace"])
        say(case, f"LoR application filed ({case['data']['lor']['lor_ref']}, simulated). The municipality verifies it; PM SVANidhi can then proceed.",
            f"LoR आवेदन दर्ज ({case['data']['lor']['lor_ref']}, सिम्युलेटेड)। नगर निकाय सत्यापन करेगा; फिर पीएम स्वनिधि आगे बढ़ सकती है।")
        return True

    # ---- unlock actions (agent offers to do it; human decides)
    for u in case["unlocks"]:
        if u["action"] not in case["offered_actions"]:
            case["offered_actions"].append(u["action"])
            names = ", ".join(x["short"] for x in u["unlocks"])
            say(case, f"One step meets a condition for {names}: {u['label']['en']}. I can do it for you now, "
                      "it does not by itself guarantee any loan or cover.",
                f"एक कदम से {names} की एक शर्त पूरी होती है: {u['label']['hi']}। मैं अभी आपके लिए कर सकता हूँ, "
                "इससे अपने आप कोई ऋण या गारंटी पक्की नहीं होती।",
                card={"type": "action", "action": u})
            case["pending"] = {"type": "action", "action": u["action"]}
            return False

    # ---- facts needed to judge whether an action (e.g. Udyam) would actually help
    if len(case["asked"]) < MAX_QUESTIONS:
        askable = _askable(case)
        for act, sid, missing in unlock_prerequisites(case["facts"]):
            cand = {x for x in missing if x in askable and x not in case["asked"] and x not in case["skipped"]
                    and case["facts"].get(x) is None}
            if not cand:
                continue
            # most decisive first (value of information under the counterfactual "action taken")
            alt = {**case["facts"], **{k: f.action.target for k, f in FACTS.items() if f.action and f.action.id == act}}
            ranked = rank_questions(alt, cand)
            m = ranked[0]["fact"] if ranked else sorted(cand)[0]
            if m:
                case["asked"].append(m)
                fp = FACTS[m]
                note(case, "decision", f"Ask '{m}' to check whether '{act}' would meet {sid}'s conditions")
                say(case, fp.question["en"], fp.question["hi"], card=_question_card(case, m, None))
                case["pending"] = {"type": "question", "fact": m}
                return False

    # ---- value-of-information questions
    if len(case["asked"]) < MAX_QUESTIONS:
        q = next_question(case["facts"], _askable(case), set(case["asked"]) | set(case["skipped"]))
        if q:
            case["asked"].append(q["fact"])
            fp = FACTS[q["fact"]]
            note(case, "decision", f"Ask '{q['fact']}' (VOI {q['voi']:.0f}; settles {', '.join(a['short'] for a in q['affects'][:3])})")
            say(case, fp.question["en"], fp.question["hi"], card=_question_card(case, q["fact"], q))
            case["pending"] = {"type": "question", "fact": q["fact"]}
            return False
    if (case["analysis"]["informal_loans"] and case["facts"].get("informal_outstanding") is None
            and "informal_outstanding" not in case["skipped"] and "informal_outstanding" not in case["asked"]):
        case["asked"].append("informal_outstanding")
        fp = FACTS["informal_outstanding"]
        say(case, fp.question["en"], fp.question["hi"], card=_question_card(case, "informal_outstanding", None))
        case["pending"] = {"type": "question", "fact": "informal_outstanding"}
        return False

    # ---- offers
    if not case["offers"] and not case.get("not_now"):
        if not B.best_financing_plan(case["schemes"], case["facts"]):
            case["closed"] = True
            say(case, "None of the loan schemes fit right now. I've saved your profile and will alert you when a scheme opens up "
                      "(for example the revamped Stand-Up India).",
                "अभी कोई ऋण योजना उपयुक्त नहीं है। मैंने आपकी प्रोफ़ाइल सहेज ली है और कोई योजना खुलने पर सूचित करूँगा।")
            return False
        if PRODUCTION and release_status()["status"] != "released":
            case["closed"] = True
            note(case, "guard", "Risk model release gate is BLOCKED, no score-based offers in production", status="blocked")
            say(case, "The risk model has not passed its release checks, so I will not size a loan. Your scheme results and "
                      "documents are ready; the branch will appraise the loan itself.",
                "जोखिम मॉडल अपनी रिलीज़ जाँच में पास नहीं हुआ है, इसलिए मैं ऋण राशि तय नहीं करूँगा। आपकी योजना जानकारी और "
                "दस्तावेज़ तैयार हैं; बैंक ऋण का आकलन स्वयं करेगा।")
            return False
        call(case, "score_and_structure", case["trace"])
        case["model_release"] = release_status()  # demo: shown on every offer so a blocked model is never presented as validated
        if case["not_now"]:
            say(case, "Honest answer: a new loan now would likely strain your business. Here is why, and a concrete plan "
                      "to become loan-ready. You can still choose to apply; the bank decides.",
                "सच्चा जवाब: अभी नया ऋण आपके व्यवसाय पर बोझ बन सकता है। कारण और ऋण-योग्य बनने की ठोस योजना यह है। "
                "आप फिर भी आवेदन चुन सकते हैं, फ़ैसला बैंक करेगा।",
                card={"type": "not_now", "score": case["score"], "offers": case["offers"], "model_release": case["model_release"]})
        else:
            say(case, "Here are your best options. I matched the repayments to your busy and slow months. Pick one.",
                "ये आपके सबसे अच्छे विकल्प हैं। मैंने किस्तों को आपके व्यस्त और धीमे महीनों से मिलाया है। एक चुनिए।",
                card={"type": "offers", "offers": case["offers"], "score": case["score"], "model_release": case["model_release"]})
        case["pending"] = {"type": "choose_offer"}
        return False
    if not case["selected_offer"]:
        case["pending"] = {"type": "choose_offer"}
        return False

    # ---- documents
    if not case["documents"]:
        call(case, "plan_documents", case["trace"])
        dd = case["documents"]
        say(case, f"Your file needs {dd['counts']['total']} items instead of the usual {dd['traditional']['count']} papers. "
                  f"I fetched or prepared {dd['counts']['auto'] + dd['counts']['generated']}; only {dd['counts']['you_do']} need you.",
            f"आपकी फ़ाइल में सामान्य {dd['traditional']['count']} काग़ज़ों की जगह {dd['counts']['total']} चीज़ें चाहिए। "
            f"{dd['counts']['auto'] + dd['counts']['generated']} मैंने ले लीं या बना दीं; केवल {dd['counts']['you_do']} आपको करनी हैं।",
            card={"type": "documents"})
        return True
    todo = [i for i in case["documents"]["items"] if i["status"] == "pending" and not i["post_sanction"]
            and i["doc"] not in case.get("uploads", {}) and i["doc"] not in case["scheduled"]]
    if todo:
        case["pending"] = {"type": "documents", "docs": [i["doc"] for i in todo]}
        return False

    # ---- DPR & application
    if not case.get("dpr"):
        call(case, "generate_project_report", case["trace"])
        return True
    if not case["application"] or case["application"].get("stale"):
        call(case, "assemble_application", case["trace"])
        return True
    if not case["approval"]:
        lenders = integrations.lenders_for(case["facts"].get("state")) or integrations.LENDERS
        o = case["selected_offer"]
        pend_items = [d for d in case["application"]["package"]["documents"] if d["status"] != "ready" and not d["post_sanction"]]
        extra_en = "" if not pend_items else f" {len(pend_items)} item(s) are still to be done at a JanAI Café; the bank will see them as pending."
        extra_hi = "" if not pend_items else f" {len(pend_items)} काम अभी JanAI कैफ़े पर बाकी हैं, बैंक इन्हें बाकी के रूप में देखेगा।"
        say(case, f"Your file is ready for review.{extra_en} I will send it to {case['application']['lender']['name']} only after you approve.",
            f"आपकी फ़ाइल देखने के लिए तैयार है।{extra_hi} आपकी मंज़ूरी के बाद ही मैं इसे {case['application']['lender']['name']} भेजूँगा।",
            card={"type": "approval", "hash": case["application"]["hash"], "lenders": lenders,
                  "lender": case["application"]["lender"], "offer": {k: o[k] for k in ("scheme_short", "amount", "rate", "tenure", "schedule_type")},
                  "kfs": o.get("kfs"), "shares": [d["label"] for d in case["documents"]["items"]] + [
                      tr("Cash-flow summary & risk assessment", "नकदी प्रवाह सारांश और जोखिम आकलन")],
                  "otp_required": case["mode"] == "assisted",
                  "attachments": [{"doc": d["doc"], **d["attachment"]} for d in case["application"]["package"]["documents"] if d["attachment"]],
                  "pending_items": [d["doc"] for d in pend_items]})
        case["pending"] = {"type": "approval", "hash": case["application"]["hash"]}
        ensure_otp(case, "approval")
        return False
    if not case["submission"]:
        call(case, "submit_application", case["trace"])
        say(case, f"Submitted to {case['application']['lender']['name']} (ref {case['submission']['los_ref']}). "
                  "The branch now has your file and its attached documents (each bound by its fingerprint to what you approved). "
                  "I'll tell you as soon as they respond. You can withdraw consent any time.",
            f"{case['application']['lender']['name']} को जमा किया (संदर्भ {case['submission']['los_ref']})। "
            "शाखा के पास अब आपकी फ़ाइल और संलग्न दस्तावेज़ हैं (हर दस्तावेज़ आपकी मंज़ूरी से फ़िंगरप्रिंट द्वारा जुड़ा)। "
            "जवाब आते ही मैं बताऊँगा। आप कभी भी सहमति वापस ले सकते हैं।",
            card={"type": "submitted", "ref": case["submission"]["los_ref"], "lender": case["application"]["lender"]})
        return True
    case["pending"] = None
    return False


def run(case: dict, max_steps: int = 40) -> dict:
    for _ in range(max_steps):
        if case.get("pending"):
            break
        try:
            if not _step(case):
                break
        except GuardError as e:
            say(case, f"I stopped: {e}. Nothing was sent.", f"मैं रुक गया: {e}। कुछ भी नहीं भेजा गया।")
            case["pending"] = None
            break
    store.save_case(case)
    return case


# --------------------------------------------------------------------------- #
# events from the entrepreneur / operator / lender
# --------------------------------------------------------------------------- #
AUDIT_FIELDS = {  # allowlist per event type; values, free text, OTPs and file bytes never enter the hash chain
    "consent": ("decisions",), "answer": ("fact",), "correct": ("fact",), "skip": ("fact",),
    "action": ("action", "go"), "choose_offer": ("index", "schedule"), "upload": ("doc", "assisted"),
    "approve": ("hash", "confirm"), "set_lender": ("lender_id",), "language": ("lang",),
}


OTP_MAX_FAILS = 5
OTP_LOCK_MINUTES = 15


OTP_TTL_MINUTES = 10
OTP_LIFETIME_FAILS = 15  # after this many wrong codes on one case, code entry is disabled (visit the branch)
OTP_MAX_ISSUED = 12      # codes a case may ever be sent
PENDING_OTP_PURPOSE = {"consent": "consent", "approval": "approval", "fallback_statement": "statement_upload"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _otp_verifier(case_id: str, purpose: str, salt: str, code: str) -> str:
    from ..config import SIGNING_KEY
    return hmac.new(SIGNING_KEY.encode(), f"{case_id}|{purpose}|{salt}|{code}".encode(), hashlib.sha256).hexdigest()


def _challenge_live(case: dict, purpose: str) -> bool:
    ch = case.get("otp_challenge") or {}
    return ch.get("purpose") == purpose and ch.get("expires", "") > _now().isoformat(timespec="seconds")


def issue_otp(case: dict, purpose: str) -> None:
    """New single-use code for one step. Only an HMAC verifier is stored; the code itself goes to the
    entrepreneur's phone (simulated SMS, demo builds only)."""
    if case.get("otp_issued", 0) >= OTP_MAX_ISSUED:
        case["otp_disabled"] = True
        return
    code, salt = f"{secrets.randbelow(10 ** 6):06d}", secrets.token_hex(8)
    case["otp_challenge"] = {"purpose": purpose, "salt": salt, "verifier": _otp_verifier(case["id"], purpose, salt, code),
                             "expires": (_now() + timedelta(minutes=OTP_TTL_MINUTES)).isoformat(timespec="seconds"),
                             "issued": _now().isoformat(timespec="seconds")}
    case["otp_issued"] = case.get("otp_issued", 0) + 1
    integrations.sms_send(case, code, purpose)
    store.audit(case["id"], "system", "otp.issued", {"purpose": purpose, "ttl_minutes": OTP_TTL_MINUTES})


def ensure_otp(case: dict, purpose: str) -> None:
    if case["mode"] == "assisted" and not _challenge_live(case, purpose):
        issue_otp(case, purpose)


def check_otp(case: dict, otp: Any, purpose: str) -> str:
    """Assisted-mode code check. Returns "ok", "wrong", "expired" or "locked".
    A code is valid for one purpose, for OTP_TTL_MINUTES, and only once. OTP_MAX_FAILS wrong codes void the
    code and lock entry for OTP_LOCK_MINUTES; OTP_LIFETIME_FAILS wrong codes disable code entry for the case."""
    if case["mode"] != "assisted":
        return "ok"
    if case.get("otp_disabled"):
        return "locked"
    locked = case.get("otp_locked_until")
    if locked and _now().isoformat(timespec="seconds") < locked:
        return "locked"
    if not _challenge_live(case, purpose):
        return "expired"
    ch = case["otp_challenge"]
    given = str(otp or "")
    if re.fullmatch(r"\d{6}", given) and hmac.compare_digest(_otp_verifier(case["id"], purpose, ch["salt"], given), ch["verifier"]):
        case["otp_challenge"] = None  # consumed: a code works once
        case.pop("demo_sms", None)
        case["otp_fails"] = 0
        store.audit(case["id"], "operator", "otp.verified", {"purpose": purpose})
        return "ok"
    case["otp_fails"] = case.get("otp_fails", 0) + 1
    case["otp_lifetime_fails"] = case.get("otp_lifetime_fails", 0) + 1
    store.audit(case["id"], "operator", "otp.failed", {"purpose": purpose, "attempt": case["otp_fails"]})
    if case["otp_lifetime_fails"] >= OTP_LIFETIME_FAILS:
        case["otp_disabled"], case["otp_challenge"] = True, None
        case.pop("demo_sms", None)
        store.audit(case["id"], "system", "otp.disabled", {"after_failures": OTP_LIFETIME_FAILS})
        say(case, "Too many wrong codes on this case. Code entry is now disabled; please complete this at the bank branch.",
            "इस मामले में बहुत बार गलत कोड। कोड दर्ज करना बंद कर दिया गया है; कृपया यह बैंक शाखा में पूरा करें।", role="system")
        return "locked"
    if case["otp_fails"] >= OTP_MAX_FAILS:
        case["otp_challenge"], case["otp_fails"] = None, 0  # the guessed-at code is void
        case.pop("demo_sms", None)
        case["otp_locked_until"] = (_now() + timedelta(minutes=OTP_LOCK_MINUTES)).isoformat(timespec="seconds")
        store.audit(case["id"], "system", "otp.locked", {"minutes": OTP_LOCK_MINUTES})
        note(case, "guard", f"{OTP_MAX_FAILS} wrong codes: code voided, entry locked for {OTP_LOCK_MINUTES} min", status="blocked")
        say(case, f"Too many wrong codes. That code no longer works; after {OTP_LOCK_MINUTES} minutes, ask for a new code.",
            f"बहुत बार गलत कोड। वह कोड अब काम नहीं करेगा; {OTP_LOCK_MINUTES} मिनट बाद नया कोड माँगें।", role="system")
        return "locked"
    return "wrong"


_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_OTP = re.compile(r"^\d{0,6}$")


def _is_bool(v):
    return type(v) is bool


def _is_int(v):
    return type(v) is int


def _short(n):
    return lambda v: isinstance(v, str) and 0 < len(v) <= n


def _opt(check):
    return lambda v: v is None or check(v)


EVENT_SCHEMA: dict[str, dict[str, tuple]] = {  # field -> (validator, required)
    "message": {"text": (_short(2000), True)},
    "consent": {"decisions": (lambda v: isinstance(v, dict) and 0 < len(v) <= 10
                              and all(isinstance(k, str) and _is_bool(x) for k, x in v.items()), True),
                "otp": (_opt(lambda v: isinstance(v, str) and bool(_OTP.match(v))), False)},
    "answer": {"fact": (_short(64), True), "value": (lambda v: v is None or isinstance(v, (bool, int, float, str)), False)},
    "correct": {"fact": (_short(64), True), "value": (lambda v: isinstance(v, (bool, int, float, str)), True),
                "reason": (_opt(lambda v: isinstance(v, str) and len(v) <= 300), False)},
    "skip": {"fact": (_short(64), True)},
    "action": {"action": (_short(32), True), "go": (_is_bool, True)},
    "choose_offer": {"index": (lambda v: _is_int(v) and 0 <= v < 10, True),
                     "schedule": (lambda v: v in ("seasonal", "flat"), False)},
    "upload": {"doc": (_short(64), True), "assisted": (lambda v: v is True, True)},
    "approve": {"hash": (lambda v: isinstance(v, str) and bool(_HEX64.match(v)), True), "confirm": (_is_bool, True),
                "otp": (_opt(lambda v: isinstance(v, str) and bool(_OTP.match(v))), False)},
    "set_lender": {"lender_id": (_short(64), True)},
    "language": {"lang": (lambda v: v in ("hi", "en"), True)},
    "resend_code": {},
}


def validate_event(ev: dict) -> None:
    """Strict, typed event schema: exact booleans/ints (no truthy strings), bounded strings, no unknown fields."""
    if not isinstance(ev, dict) or ev.get("type") not in EVENT_SCHEMA:
        raise ValueError(f"unknown event type {ev.get('type') if isinstance(ev, dict) else ev!r}")
    spec = EVENT_SCHEMA[ev["type"]]
    extra = set(ev) - set(spec) - {"type", "event_id"}
    if extra:
        raise ValueError(f"unexpected field(s) {sorted(extra)} for '{ev['type']}'")
    if "event_id" in ev and not _short(80)(ev["event_id"]):
        raise ValueError("event_id must be a short string")
    for k, (ok, required) in spec.items():
        if k not in ev:
            if required:
                raise ValueError(f"'{ev['type']}' needs '{k}'")
            continue
        if not ok(ev[k]):
            raise ValueError(f"invalid value for '{k}' in '{ev['type']}'")


def _audit_payload(ev: dict) -> dict:
    """What the append-only audit keeps about an event: that it happened and to what, never the content.
    Answer values and correction reasons live in the case (where revocation and expiry can delete them)."""
    t = ev.get("type")
    out = {"type": t, **({"event_id": ev["event_id"]} if ev.get("event_id") else {})}
    for k in AUDIT_FIELDS.get(t, ()):
        if k in ev:
            out[k] = ev[k]
    if t == "message":
        out["text_chars"] = len(ev.get("text") or "")
    if t in ("answer", "correct"):
        out["value_recorded_in_case"] = True
    if t == "correct":
        out["has_reason"] = bool(ev.get("reason"))
    return out


def handle(case: dict, ev: dict, actor: str | None = None) -> dict:
    validate_event(ev)
    t = ev.get("type")
    pend = case.get("pending") or {}
    eid = ev.get("event_id")
    seen = case.setdefault("processed_events", [])
    if eid and eid in seen:  # idempotent replay (offline outbox, retried request)
        return case
    actor = actor or ("entrepreneur" if case["mode"] == "self" else "operator")
    store.audit(case["id"], actor, f"event.{t}", _audit_payload(ev))
    if t == "message":
        _on_message(case, ev.get("text", ""))
    elif t == "consent":
        decisions = ev.get("decisions") or {}
        allowed = set(pend.get("ids") or []) if pend.get("type") == "consent" else set()
        for cid in decisions:
            art = store.get_consent(cid)
            if cid not in allowed or not art or art["caseId"] != case["id"]:
                raise ValueError(f"consent {cid} is not a pending request of this case")
        verdict = check_otp(case, ev.get("otp"), "consent")
        if verdict == "wrong":
            say(case, "The OTP did not match. Ask the entrepreneur to read the 6-digit code from their phone.",
                "OTP मेल नहीं खाया। उद्यमी से उनके फ़ोन पर आया 6 अंकों का कोड पूछें।")
        elif verdict == "expired":
            say(case, "That code has expired or was already used. Ask for a new code.",
                "वह कोड समाप्त हो गया या पहले इस्तेमाल हो चुका है। नया कोड माँगें।", role="system")
        elif verdict == "locked":
            pass  # check_otp already explained the lock
        else:
            for cid, ok in decisions.items():
                consent.set_status(cid, "ACTIVE" if ok else "REJECTED", actor=actor)
            case["pending"] = None
            granted = [k for k, v in decisions.items() if v]
            note(case, "human", f"{actor} approved {len(granted)} consent(s)")
    elif t == "answer":
        if pend.get("type") != "question" or pend.get("fact") != ev.get("fact"):
            raise ValueError(f"'{ev.get('fact')}' is not the question being asked, use a correction instead")
        _answer(case, ev["fact"], ev.get("value"), actor)
    elif t == "correct":
        _correct(case, ev.get("fact"), ev.get("value"), ev.get("reason"), actor)
    elif t == "skip":
        if pend.get("type") != "question" or pend.get("fact") != ev.get("fact"):
            raise ValueError("only the question being asked can be skipped")
        case["skipped"].append(ev["fact"])
        case["pending"] = None
        say(case, "No problem, skipped.", "कोई बात नहीं, छोड़ दिया।", role="system")
    elif t == "action":
        act = ev["action"]
        if act not in ("register_udyam", "apply_lor"):
            raise ValueError(f"unknown action {act}")
        if pend.get("type") != "action" or pend.get("action") != act:
            raise ValueError(f"'{act}' is not the action being offered")
        case["pending"] = None
        if ev.get("go"):
            case["go_ahead"][act] = True  # executed by the planner once any facts it needs are known
        else:
            say(case, "Okay, we'll leave that for later.", "ठीक है, इसे बाद के लिए छोड़ते हैं।", role="system")
    elif t == "choose_offer":
        if pend.get("type") != "choose_offer":
            raise ValueError("offers can only be chosen when they are being offered (use a correction to change a sent file)")
        o = dict(case["offers"][int(ev["index"])])
        sched = ev.get("schedule", "seasonal")
        o["schedule_type"] = sched
        o["schedule"] = o["seasonal"]["instalments"] if sched == "seasonal" else o["flat"]["instalments"]
        if o["amount"] <= 0:  # applying despite a 'not now' recommendation, entrepreneur's right
            o["amount"] = o["requested"]
            o["against_advice"] = True
        case["selected_offer"] = o
        case["documents"] = None
        case["dpr"] = None
        if case.get("application"):
            case["application"]["stale"] = True
        case["pending"] = None
        say(case, f"You chose {o['scheme_short']}, {inr(o['amount'])}, {sched} repayment.",
            f"आपने चुना {o['scheme_short']}, {inr(o['amount'])}, {'मौसमी' if sched == 'seasonal' else 'समान'} किस्तें।", role="user",
            src=["statement", "bureau"])
    elif t == "upload":
        # Clients can only *schedule* a document for a JanAI Café visit here. A document is
        # marked received solely by the file-upload endpoint, after the bytes are validated.
        doc = ev["doc"]
        if pend.get("type") != "documents" or doc not in (pend.get("docs") or []):
            raise ValueError(f"'{doc}' is not a document this file is waiting for")
        if doc not in case["scheduled"]:
            case["scheduled"].append(doc)
        say(case, "Marked for a JanAI Café visit; the operator will complete it with you. Your file moves ahead meanwhile.",
            "JanAI कैफ़े के लिए चिह्नित; ऑपरेटर आपके साथ पूरा करेगा। तब तक फ़ाइल आगे बढ़ेगी।", role="system")
        if case["documents"]:
            call(case, "plan_documents", case["trace"])
        case["pending"] = None
    elif t == "approve":
        if pend.get("type") != "approval":
            raise ValueError("there is no file waiting for approval")
        _approve(case, ev, actor)
    elif t == "set_lender":
        if pend.get("type") != "approval":
            raise ValueError("the lender can only be changed on the approval screen, before sending")
        lender = next((l for l in integrations.LENDERS if l["id"] == ev["lender_id"]), None)
        if lender is None:
            raise ValueError(f"unknown lender {ev['lender_id']!r}")
        case["application"]["lender"] = lender
        case["application"]["stale"] = True
        case["approval"] = None
        case["pending"] = None
    elif t == "language":
        case["lang"] = ev["lang"]
    elif t == "resend_code":
        purpose = PENDING_OTP_PURPOSE.get(pend.get("type"))
        if case["mode"] != "assisted" or not purpose:
            raise ValueError("no code is needed right now")
        if case.get("otp_disabled") or (case.get("otp_locked_until") or "") > _now().isoformat(timespec="seconds"):
            raise ValueError("code entry is locked")
        issued = (case.get("otp_challenge") or {}).get("issued", "")
        if issued and issued > (_now() - timedelta(seconds=60)).isoformat(timespec="seconds"):
            raise ValueError("a code was sent less than a minute ago")
        issue_otp(case, purpose)
        if case.get("otp_disabled"):
            raise ValueError("no more codes can be sent for this case; please visit the branch")
    else:
        raise ValueError(f"unknown event type {t!r}")
    if eid:
        seen.append(eid)
        del seen[:-300]
    return run(case)


def document_received(case: dict, doc: str, meta: dict, actor: str = "entrepreneur") -> dict:
    """Called by the upload endpoint after the file bytes were validated and stored."""
    replaced = doc in case.get("uploads", {})
    case.setdefault("uploads", {})[doc] = meta
    if doc in case["scheduled"]:
        case["scheduled"].remove(doc)
    item = next((i for i in ((case.get("documents") or {}).get("items") or []) if i["doc"] == doc), None)
    if not (item and item["post_sanction"] and case.get("submission")):
        _invalidate_application(case, f"document {doc} {'replaced' if replaced else 'added'}")
    store.audit(case["id"], actor, "document.received", {"doc": doc, "sha256": meta["sha256"], "bytes": meta["bytes"]})
    note(case, "human", f"Received {doc} ({meta['bytes'] if meta['bytes'] < 1024 else meta['bytes'] // 1024} {'B' if meta['bytes'] < 1024 else 'KB'}, sha256 {meta['sha256'][:12]}…), not read by Saakh; lender verifies")
    if case["documents"]:
        call(case, "plan_documents", case["trace"])
    if (case.get("pending") or {}).get("type") == "documents":
        case["pending"] = None
    return run(case)


def statement_uploaded(case: dict, fi: dict, filename: str, actor: str = "entrepreneur") -> dict:
    """Entrepreneur uploaded a statement under its own consent (never revives a declined AA consent)."""
    art = consent.request(case["id"], "statement_upload", f"{case['persona']}@saakh-aa", {"filename": filename})
    consent.set_status(art["consentId"], "ACTIVE", actor=actor)
    store.put_statement(case["id"], fi)
    txns = fi["account"]["transactions"]
    case["data"]["statement"] = {"source": "upload", "filename": filename, "txns": len(txns["transaction"]),
                                 "from": txns["startDate"], "to": txns["endDate"], "simulated": False}
    case["analysis"] = None
    note(case, "fallback", f"Statement uploaded by entrepreneur ({len(txns['transaction'])} rows), analysed under 'statement_upload' consent")
    if (case.get("pending") or {}).get("type") == "fallback_statement":
        case["pending"] = None
    return run(case)


def _answer(case: dict, fact: str, value: Any, who: str) -> None:
    try:
        set_fact(case, fact, value, who)
    except (ValueError, KeyError) as e:
        say(case, f"Sorry, I didn't get that ({e}). Please pick one of the options.",
            "माफ़ कीजिए, समझ नहीं पाया। कृपया कोई विकल्प चुनें।", role="system")
        return
    if fact == "informal_outstanding" and case["analysis"]:
        st = _statement(case)
        a = analyse(st, case["facts"].get("informal_outstanding"), case["facts"].get("activity"))
        a.pop("txn_categories", None)
        case["analysis"] = a
    lab = FACTS[fact].label
    shown = next((o.label for o in FACTS[fact].options if o.value == case["facts"][fact]), None)
    disp = shown or {"en": inr(case["facts"][fact]) if FACTS[fact].type == "money" else str(case["facts"][fact]),
                     "hi": inr(case["facts"][fact]) if FACTS[fact].type == "money" else str(case["facts"][fact])}
    case["messages"].append({"id": uuid.uuid4().hex[:10], "role": "user", "ts": store.now(),
                             "text": {"en": f"{lab['en']}: {disp['en']}", "hi": f"{lab['hi']}: {disp['hi']}"}, "card": None})
    if (case.get("pending") or {}).get("fact") == fact:
        case["pending"] = None
    if case.get("offers"):  # facts changed after offers → recompute downstream
        case["offers"], case["selected_offer"], case["documents"], case["not_now"] = [], None, None, False


VERIFIED_SOURCES = {"ekyc", "bureau", "udyam", "udyam_portal", "aa", "aa-inferred", "statement_upload", "statement_upload-inferred"}


def _correct(case: dict, fact: str | None, value: Any, reason: str | None, actor: str) -> None:
    """Correct a fact. The entrepreneur's own earlier answers are replaced (with provenance kept).
    A value that came from a verified source (e-KYC, bureau, Udyam, bank statement) is NOT overwritten:
    the correction is recorded as an open dispute that the lender sees, and the sourced value stays
    operative until it is corrected at the source or the lender accepts the correction."""
    if fact not in FACTS or FACTS[fact].source == "derived":
        raise ValueError(f"'{fact}' cannot be corrected (unknown or computed from other facts)")
    prev, prev_meta = case["facts"].get(fact), case["fact_meta"].get(fact) or {}
    claimed = coerce(fact, value)
    if prev_meta.get("source") in VERIFIED_SOURCES:
        prev_meta["dispute"] = {"claimed": claimed, "reason": reason, "by": actor, "ts": store.now(), "status": "open"}
        store.audit(case["id"], actor, "fact.disputed", {"fact": fact, "source": prev_meta["source"],
                                                         "sensitive": FACTS[fact].sensitive})
        note(case, "human", f"{fact}: dispute recorded against the {prev_meta['source']} value, sourced value stays in use")
        lab = FACTS[fact].label
        say(case, f"I recorded your dispute about \u201c{lab['en']}\u201d. I keep using the value from {prev_meta['source']} until "
                  "it is corrected there (or the bank accepts your correction); the bank will see your dispute in the file.",
            f"मैंने \u201c{lab['hi']}\u201d पर आपकी आपत्ति दर्ज की। स्रोत ({prev_meta['source']}) में सुधार होने तक (या बैंक के मानने तक) "
            "मैं वहीं का मान इस्तेमाल करूँगा; बैंक फ़ाइल में आपकी आपत्ति देखेगा।", role="system")
        _invalidate_application(case, f"a dispute was recorded on {fact}")
        return
    set_fact(case, fact, claimed, f"{actor} (correction)", reason)
    case["fact_meta"][fact].update(corrected_from={"value": prev, "source": prev_meta.get("source")}, reason=reason)
    store.audit(case["id"], actor, "fact.corrected", {"fact": fact, "from_source": prev_meta.get("source"),
                                                      "sensitive": FACTS[fact].sensitive})
    note(case, "human", f"{fact} corrected by {actor} (was from {prev_meta.get('source') or 'unknown'}), dependent results recomputed")
    case["offers"], case["selected_offer"], case["documents"], case["not_now"], case["dpr"] = [], None, None, False, None
    _invalidate_application(case, "a fact was corrected")
    if (case.get("pending") or {}).get("fact") == fact:
        case["pending"] = None


def _invalidate_application(case: dict, why: str) -> None:
    """Any change to what was approved voids the approval; a submitted file must be re-approved and re-sent.
    The lender copy is flagged as superseded so the branch never acts on a file the entrepreneur has changed."""
    if not case.get("application") or case["application"].get("status") == "withdrawn":
        return
    case["application"]["stale"] = True
    if (case.get("pending") or {}).get("type") == "approval":
        case["pending"] = None  # the card on screen shows the old file: re-assemble and ask again
    if case.get("approval"):
        note(case, "guard", f"Approval voided: {why}", status="blocked")
        case["approval"] = None
    if case.get("submission"):
        stored = store.get_application(case["application"]["id"])
        if stored and stored.get("status") != "withdrawn":
            stored.update(superseded=True, superseded_reason=why, superseded_ts=store.now())
            store.put_application(stored)
        note(case, "plan", f"Submitted file changed ({why}), needs your re-approval before it is re-sent")
        case["submission"] = None


def _approve(case: dict, ev: dict, actor: str = "entrepreneur") -> None:
    app = case.get("application")
    if not app or ev.get("hash") != app["hash"]:
        say(case, "The file changed since you opened it, please review the latest version before approving.",
            "फ़ाइल बदल गई है, मंज़ूरी से पहले नया संस्करण देखें।", role="system")
        case["pending"] = None
        return
    if not ev.get("confirm"):
        say(case, "Okay; I won't send anything. You can approve whenever you are ready.",
            "ठीक है, मैं कुछ नहीं भेजूँगा। जब तैयार हों तब मंज़ूरी दें।", role="system")
        case["pending"] = {"type": "approval", "hash": app["hash"]}
        return
    verdict = check_otp(case, ev.get("otp"), "approval")
    if verdict != "ok":
        if verdict == "wrong":
            say(case, "OTP did not match. Approval not recorded.", "OTP मेल नहीं खाया। मंज़ूरी दर्ज नहीं हुई।", role="system")
        elif verdict == "expired":
            say(case, "That code has expired or was already used. Ask for a new code.",
                "वह कोड समाप्त हो गया या पहले इस्तेमाल हो चुका है। नया कोड माँगें।", role="system")
        return
    art = consent.request(case["id"], "share_with_lender", f"{case['persona']}@saakh-aa", {"lender": app["lender"]["id"]})
    consent.set_status(art["consentId"], "ACTIVE", actor=actor)
    case["approval"] = {"hash": app["hash"], "ts": store.now(), "by": actor,
                        "method": "OTP via entrepreneur's phone (assisted)" if case["mode"] == "assisted" else "in-app confirmation",
                        "consent": art["consentId"]}
    store.audit(case["id"], actor, "application.approved", {"hash": app["hash"], "lender": app["lender"]["id"]})
    case["pending"] = None
    say(case, "I approve this application.", "मैं इस आवेदन को मंज़ूरी देता/देती हूँ।", role="user")


def _on_message(case: dict, text: str) -> None:
    text = (text or "").strip()
    if not text:
        return
    case["messages"].append({"id": uuid.uuid4().hex[:10], "role": "user", "ts": store.now(), "text": {"en": text, "hi": text}, "card": None})
    pend = case.get("pending") or {}
    if pend.get("type") == "intake":
        got = nlu.intake(text)
        for k, v in got.items():
            set_fact(case, k, v, "entrepreneur (said)", text)
        case["intake_done"] = True
        case["pending"] = None
        amt = case["facts"].get("loan_amount_sought")
        say(case, ("Understood" + (f", about {inr(amt)}" if amt else "") + ". My plan: ① verify your identity, ② read your bank "
                   "statement (with your consent), ③ check government schemes against their official rules, ④ size a loan you can "
                   "comfortably repay, ⑤ prepare your file and show what is still pending; you approve before anything is sent."),
            ("समझ गया" + (f", लगभग {inr(amt)}" if amt else "") + "। मेरी योजना: ① आपकी पहचान सत्यापित करना, ② (आपकी अनुमति से) बैंक विवरण पढ़ना, "
             "③ सरकारी योजनाओं को आधिकारिक नियमों से जाँचना, ④ आराम से चुकाने योग्य ऋण तय करना, ⑤ फ़ाइल बनाना और बताना कि क्या बाकी है, भेजने से पहले आप मंज़ूरी देंगे।"),
            card={"type": "plan", "extracted": got})
        note(case, "plan", f"Intake parsed: {got}")
        return
    if pend.get("type") == "question":
        fact = pend["fact"]
        try:
            val = nlu.answer(fact, text)
        except ValueError:
            val = None
        if val is not None:
            _answer(case, fact, val, "entrepreneur (said)")
            return
    if nlu.is_question(text):
        _qa(case, text)
        return
    say(case, "I noted that. Please use the options on the card, or ask me 'why' about any scheme.",
        "मैंने नोट कर लिया। कृपया कार्ड के विकल्प चुनें, या किसी योजना के बारे में 'क्यों' पूछें।", role="system")


ALIASES = {"pmegp": ["pmegp", "रोज़गार", "subsidy", "सब्सिडी"], "pmmy": ["mudra", "मुद्रा"], "cgtmse": ["cgtmse", "गारंटी", "guarantee", "collateral", "गिरवी"],
           "pm_vishwakarma": ["vishwakarma", "विश्वकर्मा"], "standup_india": ["stand", "स्टैंड"], "pm_svanidhi": ["svanidhi", "स्वनिधि"],
           "kcc_ah": ["kcc", "किसान"], "day_nrlm": ["nrlm", "shg loan", "समूह ऋण"], "msmed_delayed_payment": ["45", "delayed", "देरी"]}


def _qa(case: dict, text: str) -> None:
    low = text.lower()
    target = next((sid for sid, al in ALIASES.items() if any(a in low for a in al)), None)
    res = next((r for r in case["schemes"] if r["id"] == target), None) if target else None
    if res:
        sents_en = explain(res, "en")
        sents_hi = explain(res, "hi")
        say(case, " ".join(s["text"] for s in sents_en) or res["summary"]["en"],
            " ".join(s["text"] for s in sents_hi) or res["summary"]["hi"],
            card={"type": "explanation", "scheme": res["id"], "sentences": sents_en, "sentences_hi": sents_hi,
                  "status_note": res.get("status_note"), "status_cites": res.get("status_cites")})
        return
    if case.get("score") and any(w in low for w in ("score", "risk", "जोखिम", "स्कोर", "reject", "कम")):
        rc = case["score"]["reason_codes"]
        say(case, "Main factors holding your score back: " + "; ".join(f"{r['label']['en']} ({r['display']})" for r in rc[:3]),
            "आपका स्कोर कम करने वाले मुख्य कारण: " + "; ".join(f"{r['label']['hi']} ({r['display']})" for r in rc[:3]),
            card={"type": "reasons", "reasons": rc})
        return
    say(case, "You can ask me why you do or don't qualify for any scheme, e.g. 'Why not PMEGP?'",
        "आप किसी भी योजना के बारे में पूछ सकते हैं कि आप पात्र क्यों हैं या नहीं, जैसे 'PMEGP क्यों नहीं?'", role="system")


# --------------------------------------------------------------------------- #
# consent revocation & lender events
# --------------------------------------------------------------------------- #
RETAINED_ON_WITHDRAWAL = ("id", "case_id", "lender", "status", "created", "hash", "approval", "los_ref", "decision",
                         "decision_receipts")  # receipts are hashes only; the frozen "view" is erased


def _withdraw_application(case: dict, reason: str) -> None:
    """Withdraw the submitted file and erase its financial content from the lender
    copy. Retained (for audit only): ids, hashes, timestamps, approval & decision metadata."""
    app = store.get_application(case["application"]["id"]) if case.get("application") else None
    if not app:  # only a local draft existed: discard it; it is re-assembled if the flow continues
        case["application"], case["approval"] = None, None
        return
    if app:
        kept = {k: app.get(k) for k in RETAINED_ON_WITHDRAWAL}
        kept.update(status="withdrawn", package=None, consents=[], redacted=True, redaction_reason=reason,
                    applicant_name=None, persona=app.get("persona"),
                    decision={"decision": "withdrawn", "ts": store.now(), "by": "entrepreneur", "reason": reason})
        store.put_application(kept)
    if case.get("application"):
        case["application"]["package"] = None
        case["application"]["status"] = "withdrawn"
    case["approval"] = None
    from ..uploads import delete_case_files
    delete_case_files(case["id"])  # uploaded documents were only ever for this application
    case["uploads"] = {}
    # the lender's decisions on this file (amounts, notes, reasons) go too; only that a decision happened stays
    case["lender_events"] = [{"id": e.get("id"), "decision": e.get("decision"), "ts": e.get("ts"), "redacted": True}
                             for e in case.get("lender_events", [])]
    for m in case["messages"]:
        if (m.get("card") or {}).get("type") == "lender":
            m.update(text=REDACTED, card={"type": "redacted"}, redacted="withdrawn")
    case["closed"] = True  # a withdrawn file is never silently re-approved or re-sent; a new application starts afresh


SOURCE_OF_KIND = {"ekyc": "ekyc", "bureau": "bureau", "udyam": "udyam"}
GROUP_OF_KIND = {"ekyc": "ekyc", "bureau": "bureau", "udyam": "udyam", "bank_statement": "statement", "statement_upload": "statement"}
FACT_SOURCES = {"ekyc": {"ekyc"}, "bureau": {"bureau"}, "udyam": {"udyam"}, "statement": {"aa", "aa-inferred", "statement_upload", "statement_upload-inferred"}}
TOOL_GROUPS = {"fetch_ekyc": {"ekyc"}, "fetch_bank_statement": {"statement"}, "analyze_cashflow": {"statement"},
               "score_and_structure": {"statement", "bureau"}, "fetch_bureau": {"bureau"}, "lookup_udyam": {"udyam"}}
# cards that embed values derived from a data group (explanations and the approval card can quote any fact)
CARD_GROUPS = {"insights": {"statement"}, "offers": {"statement", "bureau"}, "not_now": {"statement", "bureau"},
               "reasons": {"statement", "bureau"}, "approval": {"statement", "bureau", "ekyc", "udyam"},
               "explanation": {"statement", "bureau", "ekyc", "udyam"}}
REDACTED = tr("[Removed: this message used data whose consent was withdrawn or has expired.]",
              "[हटाया गया: यह संदेश उस जानकारी पर आधारित था जिसकी सहमति वापस ली गई या समाप्त हो गई।]")


def _scrub_history(case: dict, group: str, how: str) -> int:
    """Redact chat messages, cards and trace summaries built from a data group, and drop facts and
    correction records that came from it. Returns the number of messages redacted."""
    n = 0
    for m in case["messages"]:
        card_t = (m.get("card") or {}).get("type")
        if group in CARD_GROUPS.get(card_t, set()) or group in (m.get("src") or []):
            m.update(text=REDACTED, card={"type": "redacted"}, redacted=how)
            n += 1
    for t in case["trace"]:
        if t.get("kind") == "tool" and group in TOOL_GROUPS.get(t.get("name"), set()) and t.get("summary"):
            t["summary"] = f"[removed, consent {how}]"
    srcs = FACT_SOURCES[group]
    for k in [k for k, m in case["fact_meta"].items() if m.get("source") in srcs]:
        case["facts"].pop(k, None)
        case["fact_meta"].pop(k, None)
    for m in case["fact_meta"].values():
        if (m.get("corrected_from") or {}).get("source") in srcs:
            m["corrected_from"] = {"value": None, "source": m["corrected_from"]["source"], "redacted": True}
    case["facts_version"] += 1
    return n


def _purge_source(case: dict, kind: str) -> None:
    """Delete the data that came in under an identity/bureau/Udyam consent, then recompute downstream."""
    if not (kind == "udyam" and (case["data"].get("udyam") or {}).get("registered_by_saakh")):
        case["data"].pop(kind, None)
    if kind == "ekyc":
        case["data"]["ekyc"] = {"manual": True, "purged": True}
    case["facts_version"] += 1
    case["offers"], case["selected_offer"], case["documents"], case["score"], case["dpr"] = [], None, None, None, None


def enforce_expiry(case: dict) -> dict:
    """Consents past their expiry are marked EXPIRED and their data is cleaned up exactly as on revocation."""
    expired = consent.expire_due(case["id"])
    for art in expired:
        _apply_withdrawal(case, art, "expired")
    if expired:
        store.save_case(case)
    return case


def revoke(case: dict, consent_id: str) -> dict:
    art = store.get_consent(consent_id)
    if not art or art["caseId"] != case["id"]:
        raise ValueError("consent does not belong to this case")
    art = consent.set_status(consent_id, "REVOKED")
    _apply_withdrawal(case, art, "revoked")
    store.save_case(case)
    return case


def _apply_withdrawal(case: dict, art: dict, how: str) -> None:
    kind = art["kind"]
    if kind in GROUP_OF_KIND:
        _scrub_history(case, GROUP_OF_KIND[kind], how)
        if (case.get("pending") or {}).get("type") in ("approval", "choose_offer", "documents", "question"):
            case["pending"] = None  # the card it pointed at may be gone; the planner re-derives the next step
    if kind in ("bank_statement", "statement_upload"):
        if kind == "statement_upload":
            store.delete_statement(case["id"])
        case["data"].pop("statement", None)
        case["analysis"] = None
        case["offers"], case["selected_offer"], case["documents"], case["score"], case["dpr"] = [], None, None, None, None
        submitted = bool(case.get("submission")) and (case.get("application") or {}).get("status") != "withdrawn"
        if case.get("application"):
            _withdraw_application(case, f"{kind} consent {how}")
        note(case, "privacy", f"{kind} consent {how}, derived cash-flow data deleted" +
             ("; submitted file withdrawn and erased from the lender copy" if submitted else "; downstream steps reset"))
        say(case, "Done. I deleted the analysis made from your statement" + (", withdrew your application and erased its "
                  "financial details from the bank's copy." if submitted else " and stopped all processing that depended on it."),
            "हो गया। मैंने आपके विवरण से बना विश्लेषण मिटा दिया" + ("; आवेदन वापस लिया और बैंक की प्रति से उसकी वित्तीय "
                                                              "जानकारी मिटा दी।" if submitted else " और उस पर निर्भर सारी प्रक्रिया रोक दी।"),
            role="system")
    elif kind == "share_with_lender":
        _withdraw_application(case, f"sharing consent {how}")
        note(case, "privacy", "Lender-sharing consent revoked, application withdrawn and its contents erased from the lender copy")
        say(case, "Your application has been withdrawn and its contents erased from the bank's copy "
                  "(only reference numbers and timestamps are kept for the audit trail).",
            "आपका आवेदन वापस ले लिया गया है और बैंक की प्रति से उसकी सामग्री मिटा दी गई है "
            "(ऑडिट के लिए केवल संदर्भ संख्या और समय रखे गए हैं)।", role="system")
    elif kind in SOURCE_OF_KIND:
        submitted = bool(case.get("submission")) and (case.get("application") or {}).get("status") != "withdrawn"
        _purge_source(case, kind)
        if case.get("application"):
            _withdraw_application(case, f"{kind} consent {how}")
        note(case, "privacy", f"{kind} consent {how}, data obtained under it deleted; results recomputed" +
             ("; submitted file withdrawn" if submitted else ""))
        say(case, f"Consent {how}: {consent.KINDS[kind]['title']['en']}. I deleted the data obtained under it"
                  + (" and withdrew your application." if submitted else "; I'll ask you directly if it's needed again."),
            f"सहमति {'वापस ली गई' if how == 'revoked' else 'समाप्त'}: {consent.KINDS[kind]['title']['hi']}। उससे मिली जानकारी मिटा दी"
            + (" और आवेदन वापस ले लिया।" if submitted else "; ज़रूरत पड़ी तो सीधे पूछूँगा।"), role="system")


# The BRANCH's own reasons. Saakh's scorecard factors are never offered as the bank's reasons:
# a simulated model's factors must not be presented as the lender's rationale for an adverse decision.
LENDER_REASONS = {
    "repayment_capacity": {"en": "repayment capacity", "hi": "चुकाने की क्षमता"},
    "credit_history": {"en": "credit history", "hi": "ऋण इतिहास"},
    "documents_incomplete": {"en": "documents incomplete", "hi": "दस्तावेज़ अधूरे"},
    "scheme_conditions": {"en": "scheme conditions not met", "hi": "योजना की शर्तें पूरी नहीं"},
    "business_viability": {"en": "business viability", "hi": "व्यवसाय की व्यवहार्यता"},
    "collateral_or_guarantee": {"en": "collateral or guarantee", "hi": "गिरवी या गारंटी"},
    "policy_limit": {"en": "bank policy limit", "hi": "बैंक नीति सीमा"},
    "other": {"en": "other", "hi": "अन्य"},
}
ReasonCode = Literal[tuple(LENDER_REASONS)]  # type: ignore[valid-type]


def _reason_label(code: str, lang: str) -> str:
    return (LENDER_REASONS.get(code) or {"en": code, "hi": code})[lang]


def deliver_lender_decisions(case_id: str, lock_for=None, attempts: int = 3) -> None:
    """Apply recorded lender decisions to the case, idempotently (by decision id), retrying on concurrent saves."""
    for _ in range(attempts):
        try:
            if lock_for:
                with lock_for():
                    c = store.load_case(case_id)
                    if c:
                        sync_lender_events(c)
            else:
                c = store.load_case(case_id)
                if c:
                    sync_lender_events(c)
            return
        except store.StaleCaseError:
            continue  # someone saved in between: reload and re-apply; sync is idempotent


def sync_lender_events(case: dict) -> dict:
    """Outbox delivery: the lender copy is the source of truth; any decision not yet in the case is applied once."""
    app = case.get("application") or {}
    rec = store.get_application(app["id"]) if app.get("id") else None
    dec = (rec or {}).get("decision") or {}
    seen = {e.get("id") for e in case.get("lender_events", [])}
    if dec.get("id") and dec["id"] not in seen and dec.get("decision") in ("sanction", "query", "decline"):
        lender_event(case, dec)
    return case


def lender_event(case: dict, decision: dict) -> dict:
    case["lender_events"].append(decision)
    d = decision["decision"]
    if d == "sanction":
        say(case, f"Good news! {case['application']['lender']['name']} sanctioned {inr(decision.get('amount'))}. "
                  "Visit the branch with your Aadhaar to sign; the KFS will show the final rate.",
            f"खुशख़बरी! {case['application']['lender']['name']} ने {inr(decision.get('amount'))} स्वीकृत किए। "
            "हस्ताक्षर के लिए आधार के साथ शाखा जाएँ; अंतिम दर KFS में होगी।", card={"type": "lender", "decision": decision})
    elif d == "query":
        say(case, f"The branch needs one more thing: {decision.get('note')}. I'll update your file once you add it.",
            f"शाखा को एक और चीज़ चाहिए: {decision.get('note')}। आप जोड़ेंगे तो मैं फ़ाइल अपडेट कर दूँगा।",
            card={"type": "lender", "decision": decision})
    else:
        reasons = ", ".join(_reason_label(r, "en") for r in decision.get("reasons") or [])
        reasons_hi = ", ".join(_reason_label(r, "hi") for r in decision.get("reasons") or [])
        say(case, f"The branch declined this time (the branch's reasons: {reasons}). I've built a plan to get you loan-ready, and you can try another lender.",
            f"शाखा ने इस बार मना किया (शाखा के कारण: {reasons_hi})। मैंने ऋण-योग्य बनने की योजना बनाई है, आप दूसरे बैंक में भी कोशिश कर सकते हैं।",
            card={"type": "lender", "decision": decision})
    store.save_case(case)
    return case


PRIVATE_KEYS = ("token_hash", "otp_challenge", "demo_sms", "otp_fails", "otp_lifetime_fails", "otp_issued",
                "processed_events", "go_ahead")


def public_case(case: dict, demo: bool = False) -> dict:
    c = {k: v for k, v in case.items() if k not in PRIVATE_KEYS}
    if demo and case.get("demo_sms"):  # demo only: stands in for the SMS on the entrepreneur's phone
        c["demo_sms_otp"] = case["demo_sms"]["code"]
        c["demo_sms_purpose"] = case["demo_sms"]["purpose"]
    c["consents"] = [consent.public(a) for a in store.case_consents(case["id"])]
    c["askable_remaining"] = [q["fact"] for q in rank_questions(case["facts"], _askable(case),
                                                                set(case["asked"]) | set(case["skipped"]))][:5] if case["schemes"] else []
    return c


def sweep_due(load_and_lock=None) -> list[str]:
    """Background expiry: expire and clean up every case with a lapsed consent, without waiting for access."""
    done = []
    for cid in sorted(consent.due_case_ids()):
        for _ in range(3):  # a concurrent request may save first; reload and retry
            try:
                if load_and_lock:
                    c = load_and_lock(cid)
                else:
                    loaded = store.load_case(cid)
                    c = enforce_expiry(loaded) if loaded else None
                break
            except store.StaleCaseError:
                c = "retry"
        if c is None:
            consent.expire_due(cid)  # orphaned artefacts: still mark them expired
        done.append(cid)
    return done
