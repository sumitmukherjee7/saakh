"""Real file handling: document uploads and CSV bank statements.

Documents: Saakh validates and fingerprints the file (type by magic bytes, size,
SHA-256) and stores it for the lender; it does NOT read or interpret it, and
says so. A document is marked "received" only after this succeeds.

Statements: a CSV export (date, narration, debit, credit, balance) is parsed
into the same structure the Account Aggregator path produces, so the same
analytics run on it. Parsing is strict and bounded; nothing is executed.
"""
from __future__ import annotations

import calendar
import csv
import hashlib
import io
import os
import re
import shutil
from datetime import date, datetime
from pathlib import Path

UPLOAD_DIR = Path(os.environ.get("SAAKH_UPLOADS", Path(__file__).resolve().parent.parent / "uploads"))
MAX_DOC_BYTES = 5 * 1024 * 1024
MAX_CSV_BYTES = 5 * 1024 * 1024
MAX_ROWS = 50_000
MAGIC = [(b"%PDF-", "application/pdf", "pdf"), (b"\xff\xd8\xff", "image/jpeg", "jpg"), (b"\x89PNG\r\n\x1a\n", "image/png", "png")]
SAFE = re.compile(r"[^A-Za-z0-9_.-]")


class UploadError(ValueError):
    pass


def save_document(case_id: str, doc: str, filename: str, data: bytes) -> dict:
    if not data:
        raise UploadError("empty file")
    if len(data) > MAX_DOC_BYTES:
        raise UploadError(f"file too large ({len(data) // 1024} KB > {MAX_DOC_BYTES // 1024} KB)")
    kind = next(((mime, ext) for sig, mime, ext in MAGIC if data.startswith(sig)), None)
    if not kind:
        raise UploadError("only PDF, JPEG or PNG files are accepted (checked by content, not by name)")
    digest = hashlib.sha256(data).hexdigest()
    folder = UPLOAD_DIR / SAFE.sub("_", case_id)
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob(f"{SAFE.sub('_', doc)}-*"):  # a replacement supersedes the previous file
        old.unlink(missing_ok=True)
    path = folder / f"{SAFE.sub('_', doc)}-{digest[:12]}.{kind[1]}"
    path.write_bytes(data)
    return {"sha256": digest, "bytes": len(data), "mime": kind[0], "filename": SAFE.sub("_", filename or "upload")[:80],
            "received": datetime.now().isoformat(timespec="seconds"), "verified_by_saakh": False,
            "note": {"en": "Received and fingerprinted. Saakh does not read this document; the lender verifies it.",
                     "hi": "प्राप्त और फ़िंगरप्रिंट किया गया। साख यह दस्तावेज़ नहीं पढ़ता, बैंक इसकी जाँच करता है।"}}


def load_document(case_id: str, doc: str, sha: str) -> bytes:
    """Return the stored bytes for `doc` only if they still hash to `sha` (the fingerprint the entrepreneur approved)."""
    folder = UPLOAD_DIR / SAFE.sub("_", case_id)
    for f in folder.glob(f"{SAFE.sub('_', doc)}-{SAFE.sub('_', sha[:12])}.*"):
        data = f.read_bytes()
        if hashlib.sha256(data).hexdigest() == sha:
            return data
        raise UploadError("stored file does not match its approved fingerprint")
    raise FileNotFoundError(doc)


def delete_case_files(case_id: str) -> None:
    folder = UPLOAD_DIR / SAFE.sub("_", case_id)
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)


# --------------------------------------------------------------------------- CSV statements
HEADERS = {
    "date": ("date", "txn date", "transaction date", "value date"),
    "narration": ("narration", "description", "particulars", "remarks", "details"),
    "debit": ("debit", "withdrawal", "withdrawal amt", "dr", "debit amount"),
    "credit": ("credit", "deposit", "deposit amt", "cr", "credit amount"),
    "balance": ("balance", "closing balance", "running balance"),
}
DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d %b %Y", "%d/%m/%y")


def _num(x: str) -> float:
    x = (x or "").replace(",", "").replace("₹", "").strip()
    if x in ("", "-"):
        return 0.0
    if not re.fullmatch(r"-?\d+(\.\d+)?", x):
        raise UploadError(f"not a number: {x[:20]!r}")
    return float(x)


def _date(x: str) -> date:
    x = (x or "").strip()
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(x, f).date()
        except ValueError:
            pass
    raise UploadError(f"unrecognised date: {x[:20]!r}")


def _mode(n: str) -> str:
    u = n.upper()
    for m in ("UPI", "NEFT", "IMPS", "RTGS", "ACH", "ATM", "BBPS"):
        if u.startswith(m):
            return "ACH" if m == "ACH" else ("OTHERS" if m == "BBPS" else m)
    return "CASH" if "CASH" in u else "OTHERS"


def parse_statement_csv(text: str, holder: str = "ACCOUNT HOLDER") -> dict:
    if len(text.encode("utf-8")) > MAX_CSV_BYTES:
        raise UploadError("statement file too large")
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        raise UploadError("the file has no transactions")
    head = [h.strip().lower() for h in rows[0]]
    col = {}
    for k, names in HEADERS.items():
        idx = next((i for i, h in enumerate(head) if h in names), None)
        if idx is None:
            raise UploadError(f"missing column for {k} (expected one of: {', '.join(names)})")
        col[k] = idx
    if len(rows) - 1 > MAX_ROWS:
        raise UploadError("too many rows")
    txns = []
    for i, r in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in r):
            continue
        try:
            d = _date(r[col["date"]])
            dr, cr = _num(r[col["debit"]]), _num(r[col["credit"]])
            bal = _num(r[col["balance"]])
        except (IndexError, UploadError) as e:
            raise UploadError(f"row {i}: {e}") from None
        if (dr > 0) == (cr > 0):
            raise UploadError(f"row {i}: exactly one of debit/credit must be filled")
        nar = r[col["narration"]].strip()[:200]
        txns.append({"txnId": f"U{i}", "type": "CREDIT" if cr > 0 else "DEBIT", "mode": _mode(nar),
                     "amount": round(cr or dr, 2), "currentBalance": bal,
                     "transactionTimestamp": f"{d.isoformat()}T12:00:00+05:30", "valueDate": d.isoformat(),
                     "narration": nar, "reference": f"U{i}"})
    if len(txns) < 30:
        raise UploadError("need at least 30 transactions to assess cash flow")
    txns.sort(key=lambda t: t["valueDate"])
    first, last = date.fromisoformat(txns[0]["valueDate"]), date.fromisoformat(txns[-1]["valueDate"])
    months = (last.year - first.year) * 12 + last.month - first.month + 1
    if months < 3:
        raise UploadError("need at least 3 months of transactions")
    start = date(first.year, first.month, 1)
    end = date(last.year, last.month, calendar.monthrange(last.year, last.month)[1])
    return {"simulated": False, "fiType": "DEPOSIT", "source": "upload",
            "account": {"type": "deposit", "maskedAccNumber": "uploaded", "profile": {"holders": {"holder": [{"name": holder}]}},
                        "summary": {"currentBalance": txns[-1]["currentBalance"], "currency": "INR", "branch": "uploaded statement"},
                        "transactions": {"startDate": start.isoformat(), "endDate": end.isoformat(), "transaction": txns}}}


def statement_to_csv(fi: dict) -> str:
    """Render a FI statement as the CSV format above (used for the demo sample download)."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["date", "narration", "debit", "credit", "balance"])
    for t in fi["account"]["transactions"]["transaction"]:
        if t.get("returned"):
            continue
        w.writerow([t["valueDate"], t["narration"], f"{t['amount']:.2f}" if t["type"] == "DEBIT" else "",
                    f"{t['amount']:.2f}" if t["type"] == "CREDIT" else "", f"{t['currentBalance']:.2f}"])
    return out.getvalue()
