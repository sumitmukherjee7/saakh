"""Tiny SQLite persistence: cases (JSON state), a hash-chained audit log,
consent artefacts and lender applications. One file, no ORM, thread-safe."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .util import canonical_json, sha256

DB_PATH = Path(os.environ.get("SAAKH_DB", Path(__file__).resolve().parent.parent / "saakh.db"))
_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

GENESIS = "0" * 64


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.executescript("""
        CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, created TEXT, updated TEXT, state TEXT);
        CREATE TABLE IF NOT EXISTS audit(case_id TEXT, seq INTEGER, ts TEXT, actor TEXT, action TEXT,
            payload TEXT, payload_hash TEXT, prev_hash TEXT, hash TEXT, PRIMARY KEY(case_id, seq));
        CREATE TABLE IF NOT EXISTS consents(id TEXT PRIMARY KEY, case_id TEXT, kind TEXT, status TEXT, artefact TEXT);
        CREATE TABLE IF NOT EXISTS applications(id TEXT PRIMARY KEY, case_id TEXT, lender TEXT, status TEXT,
            created TEXT, package TEXT, decision TEXT);
        CREATE TABLE IF NOT EXISTS statements(case_id TEXT PRIMARY KEY, fi TEXT);
        CREATE TABLE IF NOT EXISTS los_receipts(key TEXT PRIMARY KEY, created TEXT, result TEXT);
        """)
    return _conn


class StaleCaseError(RuntimeError):
    """The case was changed by someone else (another request, worker or the expiry sweep) since it was loaded."""


def save_case(case: dict) -> None:
    """Optimistic concurrency: a save succeeds only if the stored revision is the one this copy was loaded at,
    checked inside an IMMEDIATE transaction so it also holds across processes sharing the database."""
    with _lock:
        c = conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            r = c.execute("SELECT json_extract(state, '$.rev') FROM cases WHERE id=?", (case["id"],)).fetchone()
            stored = (r[0] or 0) if r else None
            mine = case.get("rev", 0)
            if stored is not None and stored != mine:
                raise StaleCaseError(f"case {case['id']} changed concurrently (stored rev {stored}, this copy rev {mine})")
            case["rev"] = mine + 1
            case["updated"] = now()
            try:
                c.execute("INSERT OR REPLACE INTO cases VALUES(?,?,?,?)",
                          (case["id"], case["created"], case["updated"], json.dumps(case, ensure_ascii=False, default=str)))
            except BaseException:
                case["rev"] = mine
                raise
            c.commit()
        except BaseException:
            c.rollback()
            raise


def load_case(cid: str) -> dict | None:
    with _lock:
        r = conn().execute("SELECT state FROM cases WHERE id=?", (cid,)).fetchone()
    return json.loads(r[0]) if r else None


def list_cases() -> list[dict]:
    with _lock:
        rows = conn().execute("SELECT state FROM cases ORDER BY updated DESC").fetchall()
    return [json.loads(r[0]) for r in rows]


# ---------------------------------------------------------------- audit chain
def _audit_insert(c: sqlite3.Connection, case_id: str, actor: str, action: str, payload: Any) -> dict:
    r = c.execute("SELECT seq, hash FROM audit WHERE case_id=? ORDER BY seq DESC LIMIT 1", (case_id,)).fetchone()
    seq, prev = (r[0] + 1, r[1]) if r else (1, GENESIS)
    ts = now()
    ph = sha256(payload)
    h = sha256(f"{prev}|{seq}|{ts}|{actor}|{action}|{ph}".encode())
    c.execute("INSERT INTO audit VALUES(?,?,?,?,?,?,?,?,?)",
              (case_id, seq, ts, actor, action, canonical_json(payload), ph, prev, h))
    return {"seq": seq, "ts": ts, "actor": actor, "action": action, "hash": h, "prev_hash": prev}


def audit(case_id: str, actor: str, action: str, payload: Any) -> dict:
    """Append-only, hash-chained: hash_n = H(prev_hash ‖ seq ‖ ts ‖ actor ‖ action ‖ H(payload))."""
    with _lock:
        c = conn()
        out = _audit_insert(c, case_id, actor, action, payload)
        c.commit()
    return out


def audit_log(case_id: str) -> list[dict]:
    with _lock:
        rows = conn().execute("SELECT seq, ts, actor, action, payload, payload_hash, prev_hash, hash FROM audit "
                              "WHERE case_id=? ORDER BY seq", (case_id,)).fetchall()
    return [{"seq": r[0], "ts": r[1], "actor": r[2], "action": r[3], "payload": json.loads(r[4]),
             "payload_hash": r[5], "prev_hash": r[6], "hash": r[7]} for r in rows]


def verify_chain(case_id: str) -> dict:
    prev = GENESIS
    log = audit_log(case_id)
    for e in log:
        ph = sha256(e["payload"])
        h = sha256(f"{prev}|{e['seq']}|{e['ts']}|{e['actor']}|{e['action']}|{ph}".encode())
        if ph != e["payload_hash"] or e["prev_hash"] != prev or h != e["hash"]:
            return {"ok": False, "broken_at": e["seq"], "entries": len(log)}
        prev = h
    return {"ok": True, "entries": len(log), "head": prev}


# ---------------------------------------------------------------- consents
def put_consent(cid: str, case_id: str, kind: str, status: str, artefact: dict) -> None:
    with _lock:
        conn().execute("INSERT OR REPLACE INTO consents VALUES(?,?,?,?,?)",
                       (cid, case_id, kind, status, json.dumps(artefact, ensure_ascii=False)))
        conn().commit()


def get_consent(cid: str) -> dict | None:
    with _lock:
        r = conn().execute("SELECT artefact FROM consents WHERE id=?", (cid,)).fetchone()
    return json.loads(r[0]) if r else None


def case_consents(case_id: str) -> list[dict]:
    with _lock:
        rows = conn().execute("SELECT artefact FROM consents WHERE case_id=?", (case_id,)).fetchall()
    return [json.loads(r[0]) for r in rows]


# ---------------------------------------------------------------- applications
def put_application(app: dict) -> None:
    """Every write of the lender copy bumps its revision, so a decision prepared against an older
    revision (superseded, withdrawn, re-sent, by any process) can never be written over it."""
    with _lock:
        c = conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            r = c.execute("SELECT json_extract(package, '$.rev') FROM applications WHERE id=?", (app["id"],)).fetchone()
            app["rev"] = ((r[0] or 0) if r else 0) + 1
            c.execute("INSERT OR REPLACE INTO applications VALUES(?,?,?,?,?,?,?)",
                      (app["id"], app["case_id"], app["lender"]["id"], app["status"], app["created"],
                       json.dumps(app, ensure_ascii=False, default=str), json.dumps(app.get("decision"), ensure_ascii=False)))
            c.commit()
        except BaseException:
            c.rollback()
            raise


DECIDABLE_FROM = ("submitted", "query")  # sanctioned / declined / withdrawn are final for a lender


def decide_application(app: dict, expected_rev: int, audit_entry: tuple | None = None) -> bool:
    """Atomic compare-and-set for a lender decision, in ONE transaction with its audit entry.
    Succeeds only if the stored copy is still at `expected_rev`, still decidable (submitted / query),
    still has its package and is not superseded. Anything that changed it in between, withdrawal,
    supersede, re-send, another decision, in any process, makes this a no-op returning False."""
    with _lock:
        c = conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            r = c.execute("SELECT package FROM applications WHERE id=?", (app["id"],)).fetchone()
            cur = json.loads(r[0]) if r else None
            ok = (cur is not None and (cur.get("rev") or 0) == expected_rev and cur.get("status") in DECIDABLE_FROM
                  and cur.get("package") and not cur.get("superseded"))
            if not ok:
                c.rollback()
                return False
            app["rev"] = expected_rev + 1
            c.execute("UPDATE applications SET status=?, package=?, decision=? WHERE id=?",
                      (app["status"], json.dumps(app, ensure_ascii=False, default=str),
                       json.dumps(app.get("decision"), ensure_ascii=False), app["id"]))
            if audit_entry:
                _audit_insert(c, *audit_entry)
            c.commit()
            return True
        except BaseException:
            c.rollback()
            raise


def get_application(aid: str) -> dict | None:
    with _lock:
        r = conn().execute("SELECT package FROM applications WHERE id=?", (aid,)).fetchone()
    return json.loads(r[0]) if r else None


def list_applications() -> list[dict]:
    with _lock:
        rows = conn().execute("SELECT package FROM applications ORDER BY created DESC").fetchall()
    return [json.loads(r[0]) for r in rows]


# ---------------------------------------------------------------- uploaded statements
# Kept only while the 'statement_upload' consent is ACTIVE; deleted on revocation.
def put_statement(case_id: str, fi: dict) -> None:
    with _lock:
        conn().execute("INSERT OR REPLACE INTO statements VALUES(?,?)", (case_id, json.dumps(fi, ensure_ascii=False)))
        conn().commit()


def get_statement(case_id: str) -> dict | None:
    with _lock:
        r = conn().execute("SELECT fi FROM statements WHERE case_id=?", (case_id,)).fetchone()
    return json.loads(r[0]) if r else None


def delete_statement(case_id: str) -> None:
    with _lock:
        conn().execute("DELETE FROM statements WHERE case_id=?", (case_id,))
        conn().commit()


def reset() -> None:
    with _lock:
        c = conn()
        for t in ("cases", "audit", "consents", "applications", "statements", "los_receipts"):
            c.execute(f"DELETE FROM {t}")
        c.commit()


# ---------------------------------------------------------------- consent sweep support
def consents_with_status(*statuses: str) -> list[dict]:
    q = "SELECT artefact FROM consents WHERE status IN (%s)" % ",".join("?" * len(statuses))
    with _lock:
        rows = conn().execute(q, statuses).fetchall()
    return [json.loads(r[0]) for r in rows]


# ---------------------------------------------------------------- SIMULATED lender LOS receipts
# Stands in for the lender system's own idempotency store. It lives in the same SQLite file so a
# replay after a process restart finds the original receipt (a real LOS keeps this on its side).
def los_get(key: str) -> dict | None:
    with _lock:
        r = conn().execute("SELECT result FROM los_receipts WHERE key=?", (key,)).fetchone()
    return json.loads(r[0]) if r else None


def los_put(key: str, result: dict) -> None:
    with _lock:
        conn().execute("INSERT OR IGNORE INTO los_receipts VALUES(?,?,?)", (key, now(), json.dumps(result)))
        conn().commit()
