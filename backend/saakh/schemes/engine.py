"""Cited, three-valued scheme eligibility engine.

Design
------
* Rules are data (YAML in ``kb/``), not prompts. An LLM never decides
  eligibility; it can only *explain* a proof produced here.
* Every leaf criterion must carry a citation (directly or inherited from its
  parent). The loader refuses to start if one is missing, "every eligibility
  claim must cite its source" is enforced at build time, not hoped for.
* Evaluation uses Kleene three-valued logic (TRUE / FALSE / UNKNOWN), so a
  missing fact never silently turns into a rejection. UNKNOWN propagates up and
  yields the exact set of facts that would settle the question, which is what
  the value-of-information question planner consumes.
* The output is a *proof tree*: each node carries its status, the applicant's
  actual value, the rule's threshold and the resolved citation.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..facts import DERIVED_DEPS, FACTS, derive
from . import benefits as benefit_rules

KB_DIR = Path(__file__).parent / "kb"
SOURCES_FILE = Path(__file__).parent / "sources.yaml"

T, F, U = "T", "F", "U"
VERIFICATION_LEVELS = ("verified", "official_unverified", "secondary")


class KBError(ValueError):
    pass


# --------------------------------------------------------------------------- #
# Loading & validation
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def load_sources() -> dict[str, dict]:
    with open(SOURCES_FILE, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    for sid, s in data.items():
        if s.get("verification") not in VERIFICATION_LEVELS:
            raise KBError(f"source {sid}: bad verification {s.get('verification')!r}")
        s["id"] = sid
        s["checked"] = str(s.get("checked"))
    return data


def resolve_cite(c: dict) -> dict:
    src = load_sources().get(c["source"])
    if src is None:
        raise KBError(f"unknown source {c['source']!r}")
    return {
        "source": c["source"], "loc": c.get("loc", ""), "title": src["title"], "publisher": src["publisher"],
        "url": src["url"], "checked": src["checked"],
        "verification": c.get("verification", src["verification"]),
        "note": src.get("note"),
    }


_LEAF_OPS = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "between"}


def _validate(node: dict, scheme_id: str, inherited_cite: dict | None, path: str, ids: set) -> None:
    cite = node.get("cite") or inherited_cite
    nid = node.get("id")
    if nid:
        if nid in ids:
            raise KBError(f"{scheme_id}: duplicate node id {nid}")
        ids.add(nid)
    if "fact" in node:
        if node["fact"] not in FACTS:
            raise KBError(f"{scheme_id}:{path}: unknown fact {node['fact']!r}")
        if node.get("op") not in _LEAF_OPS:
            raise KBError(f"{scheme_id}:{path}: bad op {node.get('op')!r}")
        if not cite:
            raise KBError(f"{scheme_id}:{path}: criterion without citation, every eligibility claim must cite its source")
        resolve_cite(cite)
        return
    kinds = [k for k in ("all", "any", "not", "implies") if k in node]
    if len(kinds) != 1:
        raise KBError(f"{scheme_id}:{path}: node must have exactly one of all/any/not/implies or be a leaf")
    k = kinds[0]
    if node.get("cite"):
        resolve_cite(node["cite"])
    if k in ("all", "any"):
        for i, ch in enumerate(node[k]):
            _validate(ch, scheme_id, cite, f"{path}.{k}[{i}]", ids)
    elif k == "not":
        _validate(node["not"], scheme_id, cite, f"{path}.not", ids)
    else:
        _validate(node["implies"]["if"], scheme_id, cite, f"{path}.if", ids)
        _validate(node["implies"]["then"], scheme_id, cite, f"{path}.then", ids)


@lru_cache(maxsize=1)
def load_kb() -> dict[str, dict]:
    kb: dict[str, dict] = {}
    for p in sorted(KB_DIR.glob("*.yaml")):
        with open(p, encoding="utf-8") as fh:
            s = yaml.safe_load(fh)
        sid = s["id"]
        for c in s.get("status_cite", []) or []:
            resolve_cite(c)
        _validate(s["criteria"], sid, None, "criteria", set())
        if s.get("status") not in ("active", "uncertain", "lapsed"):
            raise KBError(f"{sid}: bad status")
        # lender checks and caveats are claims too; they must cite a source
        for i, lc in enumerate(s.get("lender_checks", []) or []):
            if not lc.get("cite") or not lc.get("text"):
                raise KBError(f"{sid}: lender_checks[{i}] needs text and a citation")
            resolve_cite(lc["cite"])
            if "fact" in lc:
                _validate(lc, sid, lc["cite"], f"lender_checks[{i}]", set())
        for i, cv in enumerate(s.get("caveats", []) or []):
            if not cv.get("cite") or not cv.get("text") or "when" not in cv:
                raise KBError(f"{sid}: caveats[{i}] needs when, text and a citation")
            _validate(cv["when"], sid, cv["cite"], f"caveats[{i}].when", set())
        kb[sid] = s
    return kb


AVAILABILITY = {"active": "available", "uncertain": "unconfirmed", "lapsed": "unavailable"}


def kb_summary() -> list[dict]:
    """Public catalogue for the governance / KB browser screen."""
    out = []
    for s in load_kb().values():
        leaves: list[dict] = []
        _collect_leaves(s["criteria"], None, leaves)
        counts = {v: 0 for v in VERIFICATION_LEVELS}
        for lf in leaves:
            counts[lf["cite"]["verification"]] += 1
        out.append({
            "id": s["id"], "short": s["short"], "short_hi": s.get("short_hi", s["short"]), "name": s["name"], "kind": s["kind"], "status": s["status"],
            "status_note": s.get("status_note"), "summary": s["summary"], "agency": s["agency"],
            "apply_via": s.get("apply_via"), "n_criteria": len(leaves), "verification": counts,
            "criteria": leaves, "availability": AVAILABILITY[s["status"]],
            "lender_checks": [{"text": lc["text"], "cite": resolve_cite(lc["cite"])} for lc in s.get("lender_checks", []) or []],
            "status_cites": [resolve_cite(c) for c in s.get("status_cite", []) or []],
        })
    return out


def _collect_leaves(node: dict, inherited: dict | None, out: list) -> None:
    cite = node.get("cite") or inherited
    if "fact" in node:
        out.append({"id": node.get("id"), "fact": node["fact"], "op": node["op"], "value": node.get("value"),
                    "text": node.get("text") or _auto_text(node), "cite": resolve_cite(cite)})
        return
    for k in ("all", "any"):
        if k in node:
            for ch in node[k]:
                _collect_leaves(ch, cite, out)
    if "not" in node:
        _collect_leaves(node["not"], cite, out)
    if "implies" in node:
        # an implication is one *claim*; report it at its own level if it has text
        if node.get("text"):
            facts = []
            _facts_in(node, facts)
            out.append({"id": node.get("id"), "fact": ",".join(dict.fromkeys(facts)), "op": "implies", "value": None,
                        "text": node["text"], "cite": resolve_cite(cite)})
        else:
            _collect_leaves(node["implies"]["if"], cite, out)
            _collect_leaves(node["implies"]["then"], cite, out)


def _facts_in(node: dict, out: list) -> None:
    if "fact" in node:
        out.append(node["fact"])
        return
    for k in ("all", "any"):
        for ch in node.get(k, []):
            _facts_in(ch, out)
    if "not" in node:
        _facts_in(node["not"], out)
    if "implies" in node:
        _facts_in(node["implies"]["if"], out)
        _facts_in(node["implies"]["then"], out)


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def _cmp(op: str, actual: Any, value: Any) -> bool:
    if op == "eq":
        return actual == value
    if op == "ne":
        return actual != value
    if op == "gt":
        return actual > value
    if op == "gte":
        return actual >= value
    if op == "lt":
        return actual < value
    if op == "lte":
        return actual <= value
    if op == "in":
        return actual in value
    if op == "not_in":
        return actual not in value
    if op == "between":
        lo, hi = value
        return lo <= actual <= hi
    raise KBError(op)


def _auto_text(node: dict) -> dict:
    lab = FACTS[node["fact"]].label
    return {"en": f"{lab['en']} {node['op']} {node.get('value')}", "hi": f"{lab['hi']} {node['op']} {node.get('value')}"}


def _and(xs: list[str]) -> str:
    return F if F in xs else (U if U in xs else T)


def _or(xs: list[str]) -> str:
    return T if T in xs else (U if U in xs else F)


def _not(x: str) -> str:
    return {T: F, F: T, U: U}[x]


def _eval(node: dict, facts: dict, inherited: dict | None, auto_id: str) -> dict:
    cite = node.get("cite") or inherited
    nid = node.get("id") or auto_id
    base = {"id": nid, "text": node.get("text"), "cite": resolve_cite(cite) if cite else None}
    if "fact" in node:
        key = node["fact"]
        actual = facts.get(key)
        if actual is None:
            status, missing = U, {key}
        else:
            try:
                status = T if _cmp(node["op"], actual, node.get("value")) else F
            except TypeError:
                status = U
            missing = set()
        return {**base, "kind": "leaf", "fact": key, "op": node["op"], "value": node.get("value"),
                "actual": actual, "status": status, "missing": missing,
                "text": node.get("text") or _auto_text(node)}
    if "all" in node or "any" in node:
        k = "all" if "all" in node else "any"
        ch = [_eval(c, facts, cite, f"{nid}.{i}") for i, c in enumerate(node[k])]
        st = _and([c["status"] for c in ch]) if k == "all" else _or([c["status"] for c in ch])
        missing = set().union(*[c["missing"] for c in ch if c["status"] == U]) if st == U else set()
        return {**base, "kind": k, "children": ch, "status": st, "missing": missing}
    if "not" in node:
        c = _eval(node["not"], facts, cite, f"{nid}.0")
        return {**base, "kind": "not", "children": [c], "status": _not(c["status"]), "missing": c["missing"]}
    imp = node["implies"]
    a = _eval(imp["if"], facts, cite, f"{nid}.if")
    b = _eval(imp["then"], facts, cite, f"{nid}.then")
    st = _or([_not(a["status"]), b["status"]])
    missing: set = set()
    if st == U:
        if a["status"] == U:
            missing |= a["missing"]
        if b["status"] == U:
            missing |= b["missing"]
    return {**base, "kind": "implies", "children": [a, b], "status": st, "missing": missing}


def _expand_derived(missing: set[str], facts: dict) -> list[str]:
    out: list[str] = []
    for m in sorted(missing):
        if m in DERIVED_DEPS:
            for d in DERIVED_DEPS[m]:
                if facts.get(d) is None and d not in out:
                    out.append(d)
        elif m not in out:
            out.append(m)
    return out


def _strip(tree: dict) -> dict:
    t = {k: v for k, v in tree.items() if k != "missing"}
    if "children" in t:
        t["children"] = [_strip(c) for c in t["children"]]
    return t


def _leaf_list(tree: dict, out: list) -> None:
    if tree["kind"] == "leaf" or (tree["kind"] == "implies" and tree.get("text")):
        out.append(tree)
        return
    for c in tree.get("children", []):
        _leaf_list(c, out)


ELIG = {T: "eligible", F: "not_eligible", U: "needs_info"}


def _verified_by(node: dict, out: dict | None = None) -> dict:
    out = {} if out is None else out
    if node.get("verified_by"):
        out[node["id"]] = node["verified_by"]
    for k in ("all", "any"):
        for ch in node.get(k, []) or []:
            _verified_by(ch, out)
    return out


@dataclass
class SchemeResult:
    data: dict

    @property
    def status(self) -> str:
        return self.data["eligibility"]


def evaluate_scheme(scheme_id: str, facts: dict, as_of: date | None = None) -> dict:
    s = load_kb()[scheme_id]
    df = derive(facts)
    tree = _eval(s["criteria"], df, None, s["id"])
    elig = ELIG[tree["status"]]
    as_of = as_of or date.today()
    if s.get("valid_to") and as_of > date.fromisoformat(str(s["valid_to"])):
        elig = "lapsed"
    if s["status"] == "lapsed":
        elig = "lapsed"
    claims: list[dict] = []
    _leaf_list(tree, claims)
    failing = [{"id": c["id"], "text": c["text"], "cite": c["cite"], "actual": c.get("actual"), "fact": c.get("fact")}
               for c in claims if c["status"] == F]
    # Criteria marked `verified_by` rest on the applicant's word (or Saakh's coarse classification) until an
    # agency checks them. A scheme that is eligible only because such criteria passed is PROVISIONAL.
    vb = _verified_by(s["criteria"])
    provisional = ([{"id": c["id"], "text": c["text"], "by": vb[c["id"]], "cite": c["cite"]}
                    for c in claims if c["status"] == T and c["id"] in vb] if elig == "eligible" else [])
    cites = {}
    for c in claims:
        if c["cite"]:
            cites[(c["cite"]["source"], c["cite"]["loc"])] = c["cite"]
    ver = {v: 0 for v in VERIFICATION_LEVELS}
    for c in cites.values():
        ver[c["verification"]] += 1
    availability = "unavailable" if elig == "lapsed" else AVAILABILITY[s["status"]]
    bens = benefit_rules.benefits(scheme_id, df) if elig in ("eligible", "needs_info") else []
    unknown_cites = {}
    for c in claims:
        if c["status"] == U and c["cite"]:
            unknown_cites[(c["cite"]["source"], c["cite"]["loc"])] = c["cite"]
    # Lender checks: shown separately; they never make a scheme "eligible" or not
    # they are what the lender (not the scheme) will decide.
    lchecks = []
    for lc in s.get("lender_checks", []) or []:
        st = _eval(lc, df, lc["cite"], lc.get("id", "lc"))["status"] if "fact" in lc else None
        lchecks.append({"text": lc["text"], "cite": resolve_cite(lc["cite"]), "status": st})
    cav = []
    for cv in s.get("caveats", []) or []:
        if _eval(cv["when"], df, cv["cite"], cv.get("id", "cv"))["status"] == T:
            cav.append({"text": cv["text"], "cite": resolve_cite(cv["cite"])})
    return {
        "id": s["id"], "short": s["short"], "short_hi": s.get("short_hi", s["short"]), "name": s["name"], "kind": s["kind"], "agency": s["agency"],
        "summary": s["summary"], "apply_via": s.get("apply_via"),
        "scheme_status": s["status"], "status_note": s.get("status_note"),
        "status_cites": [resolve_cite(c) for c in s.get("status_cite", []) or []],
        "availability": availability,
        "eligibility": elig,
        "provisional": provisional,
        "proof": _strip(tree),
        "failing": failing,
        "missing_facts": _expand_derived(tree["missing"], df) if tree["status"] == U else [],
        "unknown_cites": list(unknown_cites.values()),
        "lender_checks": lchecks,
        "caveats": cav,
        "benefits": bens,
        "est_value": benefit_rules.estimate_value(scheme_id, df),
        "citations": list(cites.values()),
        "verification": ver,
    }


def evaluate_all(facts: dict, as_of: date | None = None) -> list[dict]:
    res = [evaluate_scheme(sid, facts, as_of) for sid in load_kb()]
    order = {"eligible": 0, "needs_info": 1, "not_eligible": 2, "lapsed": 3}
    res.sort(key=lambda r: (order[r["eligibility"]], -r["est_value"]))
    return res


def _live(s: dict) -> bool:
    """Schemes that are lapsed are never worth a question or an unlock action."""
    if s["status"] == "lapsed":
        return False
    return not (s.get("valid_to") and date.today() > date.fromisoformat(str(s["valid_to"])))


def quick_status(facts: dict) -> dict[str, str]:
    """Cheap status-only evaluation used inside the question planner."""
    df = derive(facts)
    return {sid: (_eval(s["criteria"], df, None, sid)["status"] if _live(s) else F) for sid, s in load_kb().items()}


def status_and_missing(facts: dict) -> dict[str, tuple[str, list[str]]]:
    df = derive(facts)
    out = {}
    for sid, s in load_kb().items():
        if not _live(s):
            out[sid] = (F, [])
            continue
        r = _eval(s["criteria"], df, None, sid)
        out[sid] = (r["status"], _expand_derived(r["missing"], df) if r["status"] == U else [])
    return out


def unlock_actions(facts: dict) -> list[dict]:
    """Counterfactuals: which *actions* (not attributes) would turn a scheme on.

    Only facts that declare an Action (e.g. Udyam registration, LoR) are
    considered; we never suggest changing who someone is.
    """
    base = quick_status(facts)
    out = []
    for key, f in FACTS.items():
        if not f.action or facts.get(key) is None or facts.get(key) == f.action.target:
            continue
        alt = dict(facts)
        alt[key] = f.action.target
        after = quick_status(alt)
        # only claim an unlock when the scheme's own conditions would then be fully met
        gained = [sid for sid in base if base[sid] == F and after[sid] == T]
        if gained:
            kb = load_kb()
            out.append({
                "action": f.action.id, "fact": key, "label": f.action.label, "effort": f.action.effort,
                "url": f.action.url,
                "unlocks": [{"id": sid, "short": kb[sid]["short"], "short_hi": kb[sid].get("short_hi", kb[sid]["short"]),
                             "becomes": ELIG[after[sid]]} for sid in gained],
            })
    return out


def unlock_prerequisites(facts: dict) -> list[tuple[str, str, list[str]]]:
    """(action, scheme, missing facts) for schemes an action *might* unlock if a few
    more facts were known, lets the agent ask those facts before offering the action."""
    base = quick_status(facts)
    out = []
    for key, f in FACTS.items():
        if not f.action or facts.get(key) is None or facts.get(key) == f.action.target:
            continue
        alt = dict(facts)
        alt[key] = f.action.target
        after = status_and_missing(alt)
        for sid in base:
            if base[sid] == F and after[sid][0] == U:
                out.append((f.action.id, sid, after[sid][1]))
    return out


def explain(result: dict, lang: str = "en") -> list[dict]:
    """Deterministic, citation-bearing sentences for a scheme result.

    Returned as structured sentences so the UI can
    verify that each sentence carries a citation id.
    """
    out = []
    name = result.get("short_hi", result["short"]) if lang == "hi" else result["short"]
    if result.get("availability") == "unavailable":
        out.append({"text": t_(result["status_note"], lang) if result.get("status_note") else
                    {"en": f"{name} is not currently available.", "hi": f"{name} अभी उपलब्ध नहीं है।"}[lang],
                    "cites": result.get("status_cites") or []})
    elif result.get("availability") == "unconfirmed":
        out.append({"text": {"en": f"Whether {name} is currently running is not confirmed, check with the agency.",
                             "hi": f"{name} अभी चालू है या नहीं, इसकी पुष्टि नहीं, एजेंसी से पता करें।"}[lang],
                    "cites": result.get("status_cites") or []})
    if result["eligibility"] == "eligible":
        if result["kind"] == "guarantee":
            text = {"en": f"You meet the borrower-side conditions for {name}; whether cover is obtained is your lender's decision.",
                    "hi": f"आप {name} की उधारकर्ता-पक्ष शर्तें पूरी करते हैं; गारंटी लेना आपके बैंक का निर्णय है।"}[lang]
        elif result["kind"] == "entitlement":
            text = {"en": f"The {name} protection applies to your sales, a claim needs a specific overdue invoice.",
                    "hi": f"{name} सुरक्षा आपकी बिक्री पर लागू है, दावे के लिए विशिष्ट बकाया बिल चाहिए।"}[lang]
        else:
            text = {"en": f"You meet every listed scheme condition for {name}; the lender still appraises the loan.",
                    "hi": f"आप {name} की सभी सूचीबद्ध शर्तें पूरी करते हैं; ऋण का आकलन बैंक करेगा।"}[lang]
        out.append({"text": text, "cites": result["citations"]})
    elif result["eligibility"] == "not_eligible":
        for fl in result["failing"]:
            out.append({"text": {"en": f"Not met: {fl['text']['en']}.", "hi": f"शर्त पूरी नहीं: {fl['text']['hi']}।"}[lang],
                        "cites": [fl["cite"]]})
    elif result["eligibility"] == "needs_info":
        labels = ", ".join(FACTS[m].label[lang] for m in result["missing_facts"] if m in FACTS)
        out.append({"text": {"en": f"To decide {name} we still need: {labels}.",
                             "hi": f"{name} तय करने के लिए अभी चाहिए: {labels}।"}[lang],
                    "cites": result.get("unknown_cites") or []})
    for cv in result.get("caveats", []):
        out.append({"text": cv["text"][lang], "cites": [cv["cite"]]})
    for b in result["benefits"]:
        out.append({"text": b["label"][lang] + (f": {b['display']}" if b.get("display") else ""), "cites": [b["cite"]]})
    for lc in result.get("lender_checks", []):
        out.append({"text": {"en": "Lender decides: ", "hi": "बैंक तय करेगा: "}[lang] + lc["text"][lang], "cites": [lc["cite"]]})
    return out


def t_(x: dict, lang: str) -> str:
    return x.get(lang) or x.get("en", "")


def deep_copy_facts(facts: dict) -> dict:
    return copy.deepcopy(facts)
