"""Demo autopilot: answers the agent's checkpoints the way a synthetic persona would.

Used by the test-suite and, in demo builds only, by the UI's "fast-forward"
button, which the API always stops *before* final approval. Every step goes
through the same public paths a human uses (consent ids, validated file uploads,
hash-bound approval) and is recorded in the audit log as actor "demo-autopilot",
so a demo run is never mistaken for the entrepreneur's own action.
"""
from __future__ import annotations

from . import uploads
from .agent import runtime as R
from .data.personas import PERSONAS, statement

ACTOR = "demo-autopilot"
# A minimal, valid PDF used as the stand-in document in demo runs.
SAMPLE_PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj "
              b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 100]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")


def _sms(case: dict) -> str | None:
    """The code the (simulated) SMS delivered to the entrepreneur's phone, in demo builds."""
    return (case.get("demo_sms") or {}).get("code")


def next_event(case: dict, stop_at: set[str] | None = None) -> dict | None:
    pend = case.get("pending") or {}
    t = pend.get("type")
    p = PERSONAS[case["persona"]]
    if not t or (stop_at and t in stop_at):
        return None
    if t == "intake":
        return {"type": "message", "text": p["utterance"]["en" if case["lang"] == "en" else "hi"]}
    if t == "consent":
        return {"type": "consent", "decisions": {cid: True for cid in pend["ids"]}, "otp": _sms(case)}
    if t == "question":
        f = pend["fact"]
        if f == "informal_outstanding":
            v = p.get("informal_principal")
            return {"type": "answer", "fact": f, "value": v} if v else {"type": "skip", "fact": f}
        if f in p["answers"]:
            return {"type": "answer", "fact": f, "value": p["answers"][f]}
        for src in ("ekyc", "bureau", "udyam"):
            if f in p[src]:
                return {"type": "answer", "fact": f, "value": p[src][f]}
        return {"type": "skip", "fact": f}
    if t == "action":
        return {"type": "action", "action": pend["action"], "go": True}
    if t == "choose_offer":
        idx = next((o["index"] for o in case["offers"] if o["amount"] > 0), 0)
        return {"type": "choose_offer", "index": idx, "schedule": "seasonal"}
    if t == "documents":
        d = pend["docs"][0]
        if d in ("csc_registration", "vet_certificate"):
            return {"type": "upload", "doc": d, "assisted": True}
        return {"type": "_sample_upload", "doc": d}
    if t == "approval":
        return {"type": "approve", "hash": pend["hash"], "confirm": True, "otp": _sms(case)}
    if t == "fallback_statement":
        return {"type": "_sample_statement"}
    return None


def drive(case: dict, stop_at: set[str] | None = None, max_events: int = 60) -> dict:
    for _ in range(max_events):
        ev = next_event(case, stop_at)
        if ev is None:
            break
        if ev["type"] == "_sample_upload":
            meta = uploads.save_document(case["id"], ev["doc"], "demo-sample.pdf", SAMPLE_PDF)
            meta["demo_sample"] = True
            case = R.document_received(case, ev["doc"], meta, actor=ACTOR)
        elif ev["type"] == "_sample_statement":
            fi = uploads.parse_statement_csv(uploads.statement_to_csv(statement(case["persona"])))
            case = R.statement_uploaded(case, fi, "demo-sample-statement.csv", actor=ACTOR)
        else:
            case = R.handle(case, ev, actor=ACTOR)
    return case
