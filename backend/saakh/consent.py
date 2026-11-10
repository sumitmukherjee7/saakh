"""Consent manager modelled on the ReBIT Account Aggregator consent artefact.

Every data pull the agent makes must be covered by an ACTIVE artefact whose
kind, FI types, purpose and data range match, checked in code by the tool
guard, not by prompt. Artefacts are HMAC-signed (stand-in for the AA's JWS),
revocable at any time, and every state change is written to the audit chain.
"""
from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone

from . import store
from .util import canonical_json

from .config import PREVIOUS_SIGNING_KEYS, SIGNING_KEY  # validated: production refuses demo/weak keys

SECRET = SIGNING_KEY.encode()
# Rotation: new artefacts are signed with the current key; artefacts signed before a rotation
# still verify against the previous keys until they expire.
_VERIFY_SECRETS = [SECRET] + [k.encode() for k in PREVIOUS_SIGNING_KEYS]

KINDS = {
    "ekyc": {
        "title": {"en": "Identity via DigiLocker (Aadhaar e-KYC)", "hi": "डिजिलॉकर से पहचान (आधार ई-केवाईसी)"},
        "data": {"en": "Name, age, gender, address (PIN code)", "hi": "नाम, आयु, लिंग, पता (पिन कोड)"},
        "purpose": {"code": "IDV", "text": {"en": "Verify identity and check scheme eligibility (age, location)",
                                           "hi": "पहचान सत्यापन और योजना पात्रता (आयु, स्थान) जाँच"}},
        "fiTypes": ["EKYC"], "provider": "DigiLocker (simulated)", "dataLifeMonths": 6, "required": True,
    },
    "bank_statement": {
        "title": {"en": "Bank statement via Account Aggregator", "hi": "अकाउंट एग्रीगेटर से बैंक विवरण"},
        "data": {"en": "12 months of transactions from your linked account", "hi": "आपके जुड़े खाते के 12 महीने के लेनदेन"},
        "purpose": {"code": "105", "text": {"en": "One-time access to assess cash flow for a business loan",
                                            "hi": "व्यवसाय ऋण के लिए नकदी प्रवाह आकलन हेतु एक-बार पहुँच"}},
        "fiTypes": ["DEPOSIT"], "provider": "Account Aggregator → your bank (simulated)", "dataLifeMonths": 3,
        "required": True, "rangeMonths": 12,
    },
    "bureau": {
        "title": {"en": "Credit bureau check (soft pull)", "hi": "क्रेडिट ब्यूरो जाँच (सॉफ्ट पुल)"},
        "data": {"en": "Existing loans and repayment history. Does not lower your score.",
                 "hi": "मौजूदा ऋण और भुगतान इतिहास। इससे स्कोर कम नहीं होता।"},
        "purpose": {"code": "CIR", "text": {"en": "Check existing loans and defaults for scheme rules",
                                            "hi": "योजना नियमों हेतु मौजूदा ऋण और चूक जाँच"}},
        "fiTypes": ["CREDIT_REPORT"], "provider": "Credit bureau (simulated)", "dataLifeMonths": 1, "required": False,
    },
    "udyam": {
        "title": {"en": "Udyam registration lookup", "hi": "उद्यम पंजीकरण खोज"},
        "data": {"en": "Udyam number and enterprise class, if registered", "hi": "उद्यम संख्या और उद्यम श्रेणी, यदि पंजीकृत"},
        "purpose": {"code": "UDY", "text": {"en": "Check MSME registration needed for CGTMSE and delayed-payment rights",
                                            "hi": "CGTMSE और देरी-भुगतान अधिकार हेतु MSME पंजीकरण जाँच"}},
        "fiTypes": ["UDYAM"], "provider": "Udyam portal (simulated)", "dataLifeMonths": 6, "required": False,
    },
    "statement_upload": {
        "title": {"en": "Analyse the statement I uploaded", "hi": "मेरे अपलोड किए विवरण का विश्लेषण करें"},
        "data": {"en": "The transactions in the CSV file you uploaded", "hi": "आपकी अपलोड की गई CSV फ़ाइल के लेनदेन"},
        "purpose": {"code": "UPL", "text": {"en": "Assess cash flow for this loan application only; deleted when you withdraw consent",
                                            "hi": "केवल इस ऋण आवेदन हेतु नकदी प्रवाह आकलन; सहमति वापस लेने पर मिटा दिया जाएगा"}},
        "fiTypes": ["DEPOSIT"], "provider": "Uploaded by you", "dataLifeMonths": 3, "required": False,
    },
    "share_with_lender": {
        "title": {"en": "Share my loan file with the selected lender", "hi": "मेरी ऋण फ़ाइल चुने गए बैंक के साथ साझा करें"},
        "data": {"en": "Application, cash-flow summary, risk assessment, documents", "hi": "आवेदन, नकदी प्रवाह सारांश, जोखिम आकलन, दस्तावेज़"},
        "purpose": {"code": "LND", "text": {"en": "Lender to appraise and sanction this application only",
                                            "hi": "केवल इस आवेदन के मूल्यांकन और स्वीकृति हेतु"}},
        "fiTypes": ["LOAN_FILE"], "provider": "Saakh → lender", "dataLifeMonths": 6, "required": True,
    },
}


def _sign(art: dict, secret: bytes = SECRET) -> str:
    body = {k: v for k, v in art.items() if k not in ("signature", "status", "statusHistory")}
    return hmac.new(secret, canonical_json(body).encode(), hashlib.sha256).hexdigest()


def request(case_id: str, kind: str, customer: str, extra: dict | None = None) -> dict:
    spec = KINDS[kind]
    t = datetime.now(timezone.utc)
    art = {
        "ver": "2.0.0", "consentId": str(uuid.uuid4()), "kind": kind, "caseId": case_id,
        "createTimestamp": t.isoformat(timespec="seconds"),
        "consentStart": t.isoformat(timespec="seconds"),
        "consentExpiry": (t + timedelta(days=30 * spec["dataLifeMonths"])).isoformat(timespec="seconds"),
        "consentMode": "STORE", "fetchType": "ONETIME",
        "consentTypes": ["PROFILE", "SUMMARY", "TRANSACTIONS"] if kind == "bank_statement" else ["PROFILE"],
        "fiTypes": spec["fiTypes"],
        "DataConsumer": {"id": "SAAKH-FIU", "type": "FIU"},
        "Customer": {"id": customer},
        "Purpose": {"code": spec["purpose"]["code"], "text": spec["purpose"]["text"]},
        "DataLife": {"unit": "MONTH", "value": spec["dataLifeMonths"]},
        "provider": spec["provider"], "simulated": kind != "statement_upload",
        **(extra or {}),
    }
    if kind == "bank_statement":
        art["FIDataRange"] = {"from": (t - timedelta(days=365)).date().isoformat(), "to": t.date().isoformat()}
    art["signature"] = _sign(art)
    art["status"] = "PENDING"
    art["statusHistory"] = [{"status": "PENDING", "ts": art["createTimestamp"]}]
    store.put_consent(art["consentId"], case_id, kind, "PENDING", art)
    store.audit(case_id, "agent", "consent.requested", {"consentId": art["consentId"], "kind": kind, "purpose": art["Purpose"]})
    return art


def set_status(consent_id: str, status: str, actor: str = "entrepreneur") -> dict:
    art = store.get_consent(consent_id)
    if art is None:
        raise KeyError(consent_id)
    art["status"] = status
    art["statusHistory"].append({"status": status, "ts": store.now(), "by": actor})
    store.put_consent(consent_id, art["caseId"], art["kind"], status, art)
    store.audit(art["caseId"], actor, f"consent.{status.lower()}", {"consentId": consent_id, "kind": art["kind"]})
    return art


def verify(consent_id: str) -> bool:
    art = store.get_consent(consent_id)
    return bool(art) and any(hmac.compare_digest(art["signature"], _sign(art, s)) for s in _VERIFY_SECRETS)


def active(case_id: str, kind: str, extra_match: dict | None = None) -> dict | None:
    """Return the ACTIVE, unexpired, signature-valid artefact for `kind`."""
    t = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for art in store.case_consents(case_id):
        if art["kind"] != kind or art["status"] != "ACTIVE" or art["consentExpiry"] < t:
            continue
        if extra_match and any(art.get(k) != v for k, v in extra_match.items()):
            continue
        if verify(art["consentId"]):
            return art
    return None


def public(art: dict, lang: str = "en") -> dict:
    spec = KINDS[art["kind"]]
    return {"consentId": art["consentId"], "kind": art["kind"], "status": art["status"], "title": spec["title"],
            "data": spec["data"], "purpose": art["Purpose"], "provider": art["provider"], "expiry": art["consentExpiry"],
            "dataLife": art["DataLife"], "range": art.get("FIDataRange"), "required": spec["required"],
            "simulated": art.get("simulated", True), "lender": art.get("lender"), "signature": art["signature"][:16] + "…"}


def expire_due(case_id: str) -> list[dict]:
    """Mark ACTIVE/PENDING artefacts past their expiry as EXPIRED; returns the ones that changed (caller cleans up data)."""
    t = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = []
    for art in store.case_consents(case_id):
        if art["status"] in ("ACTIVE", "PENDING") and art["consentExpiry"] < t:
            out.append(set_status(art["consentId"], "EXPIRED", actor="system"))
    return out


def due_case_ids() -> set[str]:
    """Cases holding an ACTIVE/PENDING artefact past its expiry (for the background sweep)."""
    t = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {a["caseId"] for a in store.consents_with_status("ACTIVE", "PENDING") if a["consentExpiry"] < t}
