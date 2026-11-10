"""Agent tools + the guard that enforces Saakh's boundaries in code.

Every tool declares what it needs. The guard runs *before* the tool:
  * data tools need an ACTIVE, signature-valid consent of the right kind;
  * submit needs an approval token whose hash equals the current application
    package hash (approve one thing, submit exactly that thing);
  * outward actions (registrations, submissions) need the entrepreneur's
    explicit go-ahead recorded in the case.
A planner, deterministic or LLM, cannot talk its way past these checks.
Every call, allowed or blocked, lands in the hash-chained audit log.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import hashlib

from .. import consent, store

# Summaries of these tools contain personal or financial data. The case trace (deletable on
# revocation) keeps them; the hash-chained audit log, which cannot be edited, stores only a digest.
PRIVATE_SUMMARY = {"fetch_ekyc", "fetch_bank_statement", "fetch_bureau", "lookup_udyam", "analyze_cashflow",
                   "score_and_structure", "register_udyam", "apply_lor"}


class GuardError(Exception):
    pass


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable[..., Any]
    needs_consent: list[str] = field(default_factory=list)
    needs_any_consent: list[str] = field(default_factory=list)  # at least one of these must be ACTIVE
    needs_approval: bool = False
    needs_go_ahead: str | None = None  # case["go_ahead"][key] must be True
    external: bool = False
    simulated: bool = False
    input_schema: dict = field(default_factory=lambda: {"type": "object", "properties": {}})


REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, **kw):
    def deco(fn):
        REGISTRY[name] = Tool(name=name, description=description, fn=fn, **kw)
        return fn
    return deco


def guard(case: dict, t: Tool) -> list[str]:
    checks = []
    for k in t.needs_consent:
        art = consent.active(case["id"], k)
        if not art:
            raise GuardError(f"{t.name}: no ACTIVE '{k}' consent")
        checks.append(f"consent:{k}:{art['consentId'][:8]}")
    if t.needs_any_consent:
        found = next(((k, a) for k in t.needs_any_consent if (a := consent.active(case["id"], k))), None)
        if not found:
            raise GuardError(f"{t.name}: no ACTIVE consent of any of {t.needs_any_consent}")
        checks.append(f"consent:{found[0]}:{found[1]['consentId'][:8]}")
    if t.needs_go_ahead:
        if not case.get("go_ahead", {}).get(t.needs_go_ahead):
            raise GuardError(f"{t.name}: entrepreneur has not approved '{t.needs_go_ahead}'")
        checks.append(f"go_ahead:{t.needs_go_ahead}")
    if t.needs_approval:
        app = case.get("application") or {}
        appr = case.get("approval") or {}
        if not appr or appr.get("hash") != app.get("hash"):
            raise GuardError(f"{t.name}: approval missing or does not match the current application (hash changed)")
        lender = (app.get("lender") or {}).get("id")
        if not consent.active(case["id"], "share_with_lender", {"lender": lender}):
            raise GuardError(f"{t.name}: no ACTIVE consent to share with lender {lender}")
        checks.append(f"approval:{appr['hash'][:12]}")
    return checks


def call(case: dict, name: str, trace: list, **args) -> Any:
    t = REGISTRY[name]
    t0 = time.perf_counter()
    entry = {"ts": store.now(), "kind": "tool", "name": name, "args": _safe(args), "simulated": t.simulated,
             "external": t.external}
    try:
        entry["guard"] = guard(case, t)
    except GuardError as e:
        entry.update(status="blocked", error=str(e), ms=round((time.perf_counter() - t0) * 1000, 1))
        trace.append(entry)
        store.audit(case["id"], "guard", "tool.blocked", {"tool": name, "reason": str(e)})
        raise
    try:
        res = t.fn(case, **args)
    except Exception as e:  # noqa: BLE001, recorded, then re-raised for the planner to handle
        entry.update(status="error", error=f"{type(e).__name__}: {e}", ms=round((time.perf_counter() - t0) * 1000, 1))
        trace.append(entry)
        # the message may quote data; the trace (deletable) keeps it, the audit chain keeps type + digest only
        store.audit(case["id"], "agent", "tool.error", {"tool": name, "error_type": type(e).__name__,
                                                        "error_sha256": hashlib.sha256(str(e).encode()).hexdigest()})
        raise
    entry.update(status="ok", ms=round((time.perf_counter() - t0) * 1000, 1), summary=_summary(name, res))
    trace.append(entry)
    summ = ({"summary_sha256": hashlib.sha256(entry["summary"].encode()).hexdigest()} if name in PRIVATE_SUMMARY
            else {"summary": entry["summary"]})
    store.audit(case["id"], "agent", f"tool.{name}", {"args": _safe(args), **summ, "guard": entry["guard"]})
    return res


def _safe(args: dict) -> dict:
    return {k: (v if isinstance(v, (str, int, float, bool)) or v is None else type(v).__name__) for k, v in args.items()}


def _summary(name: str, res: Any) -> str:
    if isinstance(res, dict) and "summary" in res:
        return str(res["summary"])[:200]
    return ""
