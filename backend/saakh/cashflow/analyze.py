"""Bank-statement intelligence: categorise transactions, detect informal debt,
aggregate to months, derive facts and plain-language insights.

Categorisation is rule-based and transparent on purpose: every category the
lender sees can be traced to the narration that produced it, and the
entrepreneur can correct it (corrections are logged).
"""
from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any

import numpy as np

from ..util import inr
from .features import Monthly, compute_features
from .seasonality import index_for

B2B_HINT = re.compile(r"PVT|LTD|WORKS|PROJECTS|CONSTRUCTIONS|TRADERS|CATERERS|DISPOSABLES|STRUCTURALS|WAREHOUSING|TENT HOUSE|HAAT|INDUSTRIES|ENTERPRISES")
GRANT = re.compile(r"REVOLVING FUND|COMMUNITY INVESTMENT|\bCIF\b|\bDBT\b|PM ?KISAN|SUBSIDY|SCHOLARSHIP|SRLM|JSLPS|NRLM")
INPUT_HINT = re.compile(r"TEXTILE|CLOTH|THREAD|STEEL|GAS AGENCY|HARDWARE|FEED|AGRO|SAMITI|PACKAGING|DISTRIBUTOR|TRADERS|WHOLESALE|DAIRY SANGH|LACE")
HOUSEHOLD_HINT = re.compile(r"KIRANA|PHARMACY|SCHOOL|SMART|VEGETABLE|DMART|MEDICAL|RECHARGE")

CAT_LABEL = {
    "sales_upi": {"en": "Sales, UPI from customers", "hi": "बिक्री, ग्राहकों से UPI"},
    "sales_b2b": {"en": "Sales, business buyers", "hi": "बिक्री, व्यावसायिक खरीदार"},
    "sales_coop": {"en": "Sales, milk union", "hi": "बिक्री, दूध संघ"},
    "sales_cash": {"en": "Sales, cash deposited", "hi": "बिक्री, जमा नकद"},
    "grant": {"en": "Government / mission funds", "hi": "सरकारी / मिशन निधि"},
    "other_in": {"en": "Other credits", "hi": "अन्य जमा"},
    "inputs": {"en": "Raw material & stock", "hi": "कच्चा माल और स्टॉक"},
    "rent": {"en": "Rent", "hi": "किराया"},
    "utilities": {"en": "Electricity & utilities", "hi": "बिजली और उपयोगिताएँ"},
    "wages": {"en": "Wages", "hi": "मज़दूरी"},
    "charges": {"en": "Bank charges", "hi": "बैंक शुल्क"},
    "emi": {"en": "Loan EMIs (formal)", "hi": "ऋण EMI (औपचारिक)"},
    "informal": {"en": "Informal loan repayments (detected)", "hi": "अनौपचारिक ऋण भुगतान (पहचाना गया)"},
    "household": {"en": "Household & personal", "hi": "घरेलू और निजी"},
    "transfer_out": {"en": "Owner drawings / self transfers", "hi": "मालिक की निकासी / स्वयं को स्थानांतरण"},
    "cash_withdrawal": {"en": "Cash withdrawals", "hi": "नकद निकासी"},
    "savings": {"en": "Group savings", "hi": "समूह बचत"},
    "bounce": {"en": "Returned EMI / mandate", "hi": "लौटाई गई EMI"},
}
BIZ_IN = {"sales_upi", "sales_b2b", "sales_coop", "sales_cash"}
BIZ_OUT = {"inputs", "rent", "utilities", "wages", "charges"}
HH_OUT = {"household", "cash_withdrawal", "savings", "transfer_out"}


def _parts(n: str) -> list[str]:
    return n.split("/")


def counterparty(t: dict) -> str:
    p = _parts(t["narration"])
    if p[0] == "UPI" and len(p) >= 4:
        return p[3]
    if p[0] in ("NEFT", "IMPS", "RTGS") and len(p) >= 4:
        return p[3]
    if p[0] == "ACH" and len(p) >= 3:
        return p[2]
    if p[0] == "BBPS" and len(p) >= 4:
        return p[3].replace(" ELECTRICITY BILL", "")
    return p[0]


def categorise(t: dict) -> str:
    n = t["narration"].upper()
    p = _parts(n)
    note = p[-1] if p else ""
    if t["type"] == "CREDIT":
        if GRANT.search(n):
            return "grant"
        if "LOAN DISB" in n or "INT.PD" in n:
            return "other_in"
        if "MILK" in n:
            return "sales_coop"
        if n.startswith("CASH DEP"):
            return "sales_cash"
        if p[0] in ("NEFT", "IMPS", "RTGS"):
            return "sales_b2b" if B2B_HINT.search(n) else "sales_upi"
        return "sales_upi"
    if t.get("returned") or "DR RTN" in n:
        return "bounce"
    if "RTN CHGS" in n or "CHGS" in n:
        return "charges"
    if n.startswith("ACH/DR") or "NACH" in n or "/EMI" in n:
        return "emi"
    if n.startswith("BBPS"):
        return "utilities"
    if "DRAWINGS" in note or "SELF TRANSFER" in n or "FAMILY EXPENSES" in n:
        return "transfer_out"
    if n.startswith("ATM WDL"):
        return "cash_withdrawal"
    if "RECHARGE" in n:
        return "household"
    if "RENT" in note:
        return "rent"
    if "WAGES" in note or "SALARY" in note:
        return "wages"
    if "SHG SAVING" in note:
        return "savings"
    if "PURCHASE" in note or INPUT_HINT.search(n):
        return "inputs"
    return "household"


def detect_informal(txns: list[dict], cats: list[str]) -> list[dict]:
    """Recurring, near-identical debits to one individual at a weekly/monthly
    cadence that no other rule explains ⇒ likely informal loan repayment."""
    groups: dict[str, list[tuple[datetime, float, int]]] = defaultdict(list)
    for i, (t, c) in enumerate(zip(txns, cats)):
        if (t["type"] == "DEBIT" and c == "household" and t["mode"] == "UPI" and t["amount"] >= 500
                and not HOUSEHOLD_HINT.search(t["narration"].upper())):
            groups[counterparty(t)].append((datetime.fromisoformat(t["transactionTimestamp"][:19]), t["amount"], i))
    found = []
    for cp, rows in groups.items():
        if len(rows) < 8 or B2B_HINT.search(cp) or HOUSEHOLD_HINT.search(cp):
            continue
        amts = [a for _, a, _ in rows]
        if statistics.pstdev(amts) / max(statistics.mean(amts), 1) > 0.03:
            continue
        rows.sort()
        gaps = [(rows[i + 1][0] - rows[i][0]).days for i in range(len(rows) - 1)]
        med = statistics.median(gaps)
        cadence = "weekly" if 6 <= med <= 8 else ("monthly" if 27 <= med <= 33 else None)
        if not cadence:
            continue
        found.append({"counterparty": cp, "amount": statistics.mean(amts), "count": len(rows), "cadence": cadence,
                      "annual_outflow": statistics.mean(amts) * (52 if cadence == "weekly" else 12),
                      "first": rows[0][0].date().isoformat(), "last": rows[-1][0].date().isoformat(),
                      "txn_idx": [i for _, _, i in rows]})
    return found


def implied_rate(principal: float, payment: float, periods_per_year: int, n_payments: int) -> float | None:
    """Annualised IRR of an informal loan (principal in, fixed payments out)."""
    if principal <= 0 or payment * n_payments <= principal:
        return None
    lo, hi = 0.0, 5.0 / periods_per_year
    for _ in range(100):
        r = (lo + hi) / 2
        pv = payment * (1 - (1 + r) ** -n_payments) / r if r > 0 else payment * n_payments
        if pv > principal:
            lo = r
        else:
            hi = r
    return ((1 + lo) ** periods_per_year) - 1


def analyse(statement: dict, informal_principal: float | None = None, activity: str | None = None) -> dict[str, Any]:
    acct = statement["account"]
    txns = acct["transactions"]["transaction"]
    cats = [categorise(t) for t in txns]
    informal = detect_informal(txns, cats)
    for inf in informal:
        for i in inf["txn_idx"]:
            cats[i] = "informal"

    start = date.fromisoformat(acct["transactions"]["startDate"])
    months: list[str] = []
    y, m = start.year, start.month
    end = date.fromisoformat(acct["transactions"]["endDate"])
    while (y, m) <= (end.year, end.month):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    idx = {k: i for i, k in enumerate(months)}
    n = len(months)
    agg = {k: np.zeros(n) for k in ("biz_in", "other_in", "biz_out", "hh_out", "emi_out", "informal_out", "digital_in", "transfer_out")}
    payers: list[set] = [set() for _ in range(n)]
    payer_tot: Counter = Counter()
    bounces = 0
    weeks_with_sales: set = set()
    cat_tot: Counter = Counter()
    bal_days: dict[str, list[float]] = defaultdict(list)
    end_bal = np.zeros(n)
    for t, c in zip(txns, cats):
        mk = t["valueDate"][:7]
        if mk not in idx:
            continue
        i = idx[mk]
        a = t["amount"]
        bal_days[t["valueDate"]].append(t["currentBalance"])
        end_bal[i] = t["currentBalance"]
        if c == "bounce":
            bounces += 1
            cat_tot[c] += 1
            continue
        cat_tot[c] += a
        if c in BIZ_IN:
            agg["biz_in"][i] += a
            if c != "sales_cash":
                agg["digital_in"][i] += a
                cp = counterparty(t)
                payers[i].add(cp)
                if c != "sales_coop":  # institutional anchor buyers are not concentration risk
                    payer_tot[cp] += a
            d = date.fromisoformat(t["valueDate"])
            weeks_with_sales.add(d.isocalendar()[:2])
        elif c in ("grant", "other_in"):
            agg["other_in"][i] += a
        elif c in BIZ_OUT:
            agg["biz_out"][i] += a
        elif c == "emi":
            agg["emi_out"][i] += a
        elif c == "informal":
            agg["informal_out"][i] += a
        else:
            agg["hh_out"][i] += a
            if c == "transfer_out":
                agg["transfer_out"][i] += a

    # average daily closing balance per month (carry forward)
    avg_bal = np.zeros(n)
    opening = txns[0]["currentBalance"] - (txns[0]["amount"] if txns[0]["type"] == "CREDIT" else -txns[0]["amount"]) if txns else 0
    last = opening
    for i, mk in enumerate(months):
        yy, mm = map(int, mk.split("-"))
        import calendar
        nd = calendar.monthrange(yy, mm)[1]
        vals = []
        for dd in range(1, nd + 1):
            k = f"{mk}-{dd:02d}"
            if k in bal_days:
                last = bal_days[k][-1]
            vals.append(last)
        avg_bal[i] = float(np.mean(vals))
    total_weeks = max(1, round(n * 52 / 12))
    biz_total = max(agg["biz_in"].sum(), 1)
    top_share = (payer_tot.most_common(1)[0][1] / biz_total) if payer_tot else 0.0
    monthly = Monthly(
        months=months, biz_in=agg["biz_in"].round(0).tolist(), biz_out=agg["biz_out"].round(0).tolist(),
        hh_out=agg["hh_out"].round(0).tolist(), emi_out=agg["emi_out"].round(0).tolist(),
        informal_out=agg["informal_out"].round(0).tolist(), avg_bal=avg_bal.round(0).tolist(),
        payers=[len(s) for s in payers], other_in=agg["other_in"].round(0).tolist(), end_bal=end_bal.round(0).tolist(),
        top_payer_share=float(top_share), bounces=bounces, transfers_out=agg["transfer_out"].round(0).tolist(),
        active_week_share=min(1.0, len(weeks_with_sales) / total_weeks),
        digital_share=float(agg["digital_in"].sum() / biz_total),
    )
    feats = compute_features(monthly, index_for(activity))

    # ---- seasonality profile by calendar month ----
    bi = np.asarray(monthly.biz_in)
    prof = (bi / max(bi.mean(), 1)).round(2).tolist()
    order = np.argsort(bi)
    lean = [months[i] for i in order[:3]]
    peak = [months[i] for i in order[-3:][::-1]]

    # ---- top customers ----
    top = [{"name": k, "amount": round(v), "share": round(float(v / biz_total), 3)} for k, v in payer_tot.most_common(5)]

    # ---- derived facts with evidence (fed to the scheme engine) ----
    derived: dict[str, Any] = {"annual_turnover": int(bi.sum() * 12 / max(n, 1))}
    evidence: dict[str, str] = {"annual_turnover": (f"12-month business inflows {inr(bi.sum())}" if n == 12 else
                                                    f"{n}-month business inflows {inr(bi.sum())}, annualised")}
    b2b = [t for t, c in zip(txns, cats) if c == "sales_b2b"]
    if b2b:
        derived["has_b2b_buyers"] = True
        evidence["has_b2b_buyers"] = f"{len(b2b)} payments from business buyers (e.g. {counterparty(b2b[0])})"
    coop = [t for t, c in zip(txns, cats) if c == "sales_coop"]
    if coop:
        evidence["owns_milch_animals"] = f"{len(coop)} milk-union payments (e.g. {counterparty(coop[0])})"
    grants = [t for t, c in zip(txns, cats) if c == "grant"]
    flags = []
    if grants:
        flags.append({"fact": "availed_other_govt_subsidy",
                      "note": {"en": "Statement shows mission/government funds: " + ", ".join(f"{counterparty(g)} {inr(g['amount'])}" for g in grants)
                               + ". Revolving/community funds are usually not a capital subsidy, but the DIC must confirm.",
                               "hi": "विवरण में मिशन/सरकारी निधि दिखी: " + ", ".join(f"{counterparty(g)} {inr(g['amount'])}" for g in grants)
                               + "। परिक्रामी/सामुदायिक निधि आमतौर पर पूंजी सब्सिडी नहीं होती, पर DIC को पुष्टि करनी होगी।"}})

    # ---- insights (plain language, bilingual) ----
    insights = []
    avg_in = bi.mean()
    insights.append({"id": "income", "tone": "good",
                     "title": {"en": f"Average business income {inr(avg_in)}/month", "hi": f"औसत व्यावसायिक आय {inr(avg_in)}/माह"},
                     "detail": {"en": f"{int(round(monthly.digital_share * 100))}% received digitally from {int(np.mean(monthly.payers))} paying customers a month.",
                                "hi": f"{int(round(monthly.digital_share * 100))}% डिजिटल रूप से, हर महीने {int(np.mean(monthly.payers))} भुगतान करने वाले ग्राहक।"}})
    insights.append({"id": "season", "tone": "info",
                     "title": {"en": "Seasonal business", "hi": "मौसमी व्यवसाय"},
                     "detail": {"en": f"Peak: {', '.join(_mname(x) for x in peak)}. Lean: {', '.join(_mname(x) for x in lean)} "
                                      f"(lean month ≈ {int(round(feats['min_to_median'] * 100))}% of a normal month).",
                                "hi": f"व्यस्त: {', '.join(_mname(x) for x in peak)}। कमज़ोर: {', '.join(_mname(x) for x in lean)} "
                                      f"(कमज़ोर महीना ≈ सामान्य का {int(round(feats['min_to_median'] * 100))}%)।"}})
    for inf in informal:
        rate = None
        if informal_principal:
            rate = implied_rate(informal_principal, inf["amount"], 52 if inf["cadence"] == "weekly" else 12, inf["count"])
        inf["implied_annual_rate"] = rate
        det_en = (f"{inf['count']} {inf['cadence']} payments of {inr(inf['amount'])} to {inf['counterparty']} "
                  f"(≈ {inr(inf['annual_outflow'])}/year).")
        det_hi = (f"{inf['counterparty']} को {inr(inf['amount'])} के {inf['count']} {'साप्ताहिक' if inf['cadence'] == 'weekly' else 'मासिक'} भुगतान "
                  f"(≈ {inr(inf['annual_outflow'])}/वर्ष)।")
        if rate:
            det_en += f" On a ₹{int(informal_principal):,} loan that is ≈{int(rate * 100)}% a year."
            det_hi += f" ₹{int(informal_principal):,} के ऋण पर यह ≈{int(rate * 100)}% सालाना है।"
        insights.append({"id": "informal", "tone": "warn",
                         "title": {"en": "Likely moneylender repayments", "hi": "संभावित साहूकार भुगतान"},
                         "detail": {"en": det_en + " Refinancing this is part of the plan.",
                                    "hi": det_hi + " इसे औपचारिक ऋण में बदलना योजना का हिस्सा है।"}})
    if bounces:
        insights.append({"id": "bounce", "tone": "bad",
                         "title": {"en": f"{bounces} EMI bounce(s) in {n} months", "hi": f"{n} महीनों में {bounces} EMI बाउंस"},
                         "detail": {"en": "Lenders weigh these heavily; we align the new EMI to your strong months to avoid repeats.",
                                    "hi": "बैंक इन्हें गंभीरता से देखते हैं; हम नई EMI को आपके अच्छे महीनों से जोड़ते हैं।"}})
    if feats["inflow_trend"] < -0.15:  # de-seasonalised
        insights.append({"id": "decline", "tone": "bad",
                         "title": {"en": "Sales have been falling", "hi": "बिक्री घट रही है"},
                         "detail": {"en": f"About {int(round(-feats['inflow_trend'] * 100))}% lower over the year.",
                                    "hi": f"साल भर में लगभग {int(round(-feats['inflow_trend'] * 100))}% कम।"}})
    if top and top[0]["share"] > 0.3:
        insights.append({"id": "concentration", "tone": "warn",
                         "title": {"en": "One buyer dominates", "hi": "एक खरीदार पर अधिक निर्भरता"},
                         "detail": {"en": f"{top[0]['name']} is {int(top[0]['share'] * 100)}% of sales.",
                                    "hi": f"{top[0]['name']} बिक्री का {int(top[0]['share'] * 100)}% है।"}})

    return {
        "simulated": statement.get("simulated", False),
        "monthly": monthly.to_dict(),
        "features": feats,
        "categories": [{"id": k, "label": CAT_LABEL.get(k, {"en": k, "hi": k}), "amount": round(v)} for k, v in cat_tot.most_common()],
        "informal_loans": [{k: v for k, v in i.items() if k != "txn_idx"} for i in informal],
        "top_customers": top,
        "seasonality": {"profile": prof, "peak": peak, "lean": lean, "index_used": activity or "flat"},
        "derived_facts": derived,
        "evidence": evidence,
        "flags": flags,
        "insights": insights,
        "data_quality": {"months": n, "transactions": len(txns), "first": months[0] if months else None,
                         "last": months[-1] if months else None},
        "txn_categories": cats,
    }


_MN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _mname(mk: str) -> str:
    return _MN[int(mk[5:7]) - 1]
