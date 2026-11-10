"""Runtime configuration, validated once, fail closed.

SAAKH_ENV must be exactly "demo" or "production" (a typo such as "prod" stops
the server instead of silently enabling demo behaviour). In production every
secret must be provisioned, must not be a demo value, and must pass a strength
check (>= 32 chars, >= 128 bits of estimated entropy, no obvious repetition).
A heuristic cannot prove a key is random: generate keys with a CSPRNG, e.g.
    python -c "import secrets; print(secrets.token_urlsafe(32))"

Rotation: SAAKH_SIGNING_KEYS_PREVIOUS (comma-separated) keeps older signing
keys valid for *verifying* existing consent artefacts until they expire; new
artefacts use SAAKH_SIGNING_KEY. A lender may hold two keys in
SAAKH_LENDER_KEYS during a rotation; removing a key revokes it.

Lender identity: SAAKH_LENDER_KEYS="lender-id:key,lender-id:key" maps each
key to one lender principal. A lender can only see and act on applications
addressed to it. Demo builds use the published keys "demo-<lender-id>".
"""
from __future__ import annotations

import math
import os
from collections import Counter

ENV = os.environ.get("SAAKH_ENV", "demo").strip().lower()
if ENV not in ("demo", "production"):
    raise RuntimeError(f"SAAKH_ENV must be 'demo' or 'production', got {ENV!r}")
DEMO = ENV == "demo"
PRODUCTION = ENV == "production"

DEMO_SIGNING_KEY = "saakh-demo-signing-key"
DEMO_LENDER_PREFIX = "demo-"
MIN_SECRET_LEN = 32


MIN_ENTROPY_BITS = 128


def entropy_bits(value: str) -> float:
    """Shannon estimate of total entropy from the character distribution (an upper bound, not proof)."""
    n = len(value)
    if not n:
        return 0.0
    return -n * sum((c / n) * math.log2(c / n) for c in Counter(value).values())


def _repetitive(value: str) -> bool:
    for size in range(1, len(value) // 2 + 1):  # a short block repeated, e.g. "abcabcabc…"
        if len(value) % size == 0 and value[:size] * (len(value) // size) == value:
            return True
    return False


def _require_secret(name: str, value: str | None) -> str:
    if not value:
        raise RuntimeError(f"{name} must be set when SAAKH_ENV=production")
    if value == DEMO_SIGNING_KEY or value.startswith(DEMO_LENDER_PREFIX):
        raise RuntimeError(f"{name} is a demo value")
    if len(value) < MIN_SECRET_LEN or entropy_bits(value) < MIN_ENTROPY_BITS or _repetitive(value):
        raise RuntimeError(f"{name} is too weak (need >= {MIN_SECRET_LEN} chars and ~{MIN_ENTROPY_BITS} bits; "
                           "generate one with secrets.token_urlsafe(32))")
    return value


SIGNING_KEY = (_require_secret("SAAKH_SIGNING_KEY", os.environ.get("SAAKH_SIGNING_KEY")) if PRODUCTION
               else os.environ.get("SAAKH_SIGNING_KEY", DEMO_SIGNING_KEY))
PREVIOUS_SIGNING_KEYS = [(_require_secret("SAAKH_SIGNING_KEYS_PREVIOUS", k) if PRODUCTION else k)
                         for k in filter(None, (p.strip() for p in os.environ.get("SAAKH_SIGNING_KEYS_PREVIOUS", "").split(",")))]


def _lender_keys() -> dict[str, str]:
    """key -> lender id"""
    raw = os.environ.get("SAAKH_LENDER_KEYS", "")
    out: dict[str, str] = {}
    for part in filter(None, (p.strip() for p in raw.split(","))):
        lid, _, key = part.partition(":")
        if not lid or not key:
            raise RuntimeError("SAAKH_LENDER_KEYS must look like 'lender-id:key,lender-id:key'")
        out[_require_secret(f"lender key for {lid}", key) if PRODUCTION else key] = lid
    if PRODUCTION and not out:
        raise RuntimeError("SAAKH_LENDER_KEYS must be set when SAAKH_ENV=production")
    if DEMO and not out:
        from .integrations import LENDERS
        out = {f"{DEMO_LENDER_PREFIX}{l['id']}": l["id"] for l in LENDERS}
    return out


LENDER_KEYS = _lender_keys()
