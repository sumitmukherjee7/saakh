"""SIMULATED external systems, clearly labelled as such everywhere they surface.

  DigiLocker e-KYC · Account Aggregator (FIP) · Credit bureau · Udyam API ·
  PM SVANidhi LoR · Lender LOS (loan origination) submission

Each adapter has the shape a production adapter would have (consent id in,
typed payload out) and can inject realistic failures so the agent's recovery
logic is exercised: the first Account Aggregator fetch for a case times out
(FIP latency is common), the retry succeeds.
"""
from __future__ import annotations

import random
import uuid

from .data.personas import PERSONAS, statement


class TransientError(Exception):
    """Retryable failure (timeout, 5xx)."""


class PermanentError(Exception):
    """Non-retryable failure; agent must take a fallback path."""


_attempts: dict[tuple[str, str], int] = {}

LENDERS = [
    {"id": "pnb-barabanki", "name": "Punjab National Bank, Barabanki Main", "type": "PSB branch", "state": "Uttar Pradesh"},
    {"id": "boi-pimpri", "name": "Bank of India, Pimpri MIDC", "type": "PSB branch", "state": "Maharashtra"},
    {"id": "canara-mandya", "name": "Canara Bank, Mandya KR Road", "type": "PSB branch", "state": "Karnataka"},
    {"id": "boi-khunti", "name": "Bank of India, Khunti", "type": "PSB branch", "state": "Jharkhand"},
    {"id": "sbi-bhopal", "name": "State Bank of India, Bhopal New Market", "type": "PSB branch", "state": "Madhya Pradesh"},
    {"id": "ujjivan-sitapur", "name": "Ujjivan Small Finance Bank, Sitapur", "type": "SFB branch", "state": "Uttar Pradesh"},
    {"id": "aye-finance", "name": "Aye Finance (NBFC), district office", "type": "NBFC", "state": "*"},
]


def _maybe_fail(case_id: str, system: str, fail_first: bool) -> None:
    k = (case_id, system)
    _attempts[k] = _attempts.get(k, 0) + 1
    if fail_first and _attempts[k] == 1:
        raise TransientError(f"{system}: upstream timeout (FIP did not respond in 30s)")


def ekyc(case_id: str, persona: str) -> dict:
    p = PERSONAS[persona]
    return {"simulated": True, "source": "DigiLocker (simulated)", "ref": f"DL-{uuid.uuid4().hex[:10].upper()}",
            "facts": dict(p["ekyc"])}


def aa_fetch(case_id: str, persona: str, chaos: bool = True) -> dict:
    _maybe_fail(case_id, "aa", chaos)
    st = statement(persona)
    return {"simulated": True, "source": "Account Aggregator (simulated FIP)", "sessionId": str(uuid.uuid4()),
            "fi": st}


def bureau(case_id: str, persona: str) -> dict:
    b = dict(PERSONAS[persona]["bureau"])
    return {"simulated": True, "source": "Credit bureau (simulated)", "report": b,
            "facts": {k: b[k] for k in ("is_defaulter", "prior_mudra_tarun_repaid", "availed_pmegp",
                                        "outstanding_mudra_or_svanidhi", "has_kcc", "svanidhi_tranche_repaid")}}


def udyam_lookup(case_id: str, persona: str) -> dict:
    u = dict(PERSONAS[persona]["udyam"])
    return {"simulated": True, "source": "Udyam API (simulated)", "record": u,
            "facts": {k: v for k, v in u.items() if k in ("udyam_registered", "enterprise_class")}}


def udyam_register(case_id: str, persona: str, facts: dict, enterprise_class: str) -> dict:
    """Class is computed from the declared investment AND turnover, never assumed."""
    code = STATE_CODES.get(facts.get("state") or "", "IN")
    num = f"UDYAM-{code}-{random.randint(10, 99)}-{random.randint(1000000, 9999999)}"
    return {"simulated": True, "source": "Udyam portal (simulated)", "udyam_number": num, "enterprise_class": enterprise_class}


def svanidhi_lor(case_id: str, persona: str) -> dict:
    return {"simulated": True, "source": "PM SVANidhi portal (simulated)", "lor_ref": f"LOR-{uuid.uuid4().hex[:8].upper()}",
            "status": "SUBMITTED_TO_ULB", "note": "Urban local body verifies within ~15 days (simulated: instant)"}


STATE_CODES = {"Uttar Pradesh": "UP", "Maharashtra": "MH", "Karnataka": "KR", "Jharkhand": "JH", "Madhya Pradesh": "MP",
               "Bihar": "BR", "Odisha": "OD", "Tamil Nadu": "TN", "Rajasthan": "RJ", "Gujarat": "GJ", "West Bengal": "WB"}


def sms_send(case: dict, code: str, purpose: str) -> dict:
    """SIMULATED SMS gateway. No real SMS provider is integrated, so this only works in demo builds, where the
    'message' is shown on screen as the entrepreneur's phone. Production refuses assisted mode instead."""
    from .config import DEMO
    if not DEMO:
        raise PermanentError("no SMS provider is integrated; assisted mode is unavailable in production")
    case["demo_sms"] = {"code": code, "purpose": purpose}
    return {"simulated": True, "purpose": purpose}


def lenders_for(state: str | None) -> list[dict]:
    return [l for l in LENDERS if l["state"] in (state, "*")]


def los_key(application: dict) -> str:
    """Idempotency key scoped to this application, this lender and this approved file version."""
    return f"{application['id']}:{application['lender']['id']}:{application['hash']}"


def los_submit(application: dict, idempotency_key: str | None = None) -> dict:
    """Idempotent: re-sending the same approved file, even from a new process after a crash, returns the
    original reference. Receipts persist in the (simulated) LOS store, see store.los_get/los_put."""
    from . import store
    key = idempotency_key or los_key(application)
    prior = store.los_get(key)
    if prior:
        return {**prior, "replayed": True}
    r = {"simulated": True, "los_ref": f"LOS-{uuid.uuid4().hex[:8].upper()}", "status": "RECEIVED", "idempotency_key": key}
    store.los_put(key, r)
    return store.los_get(key) or r
