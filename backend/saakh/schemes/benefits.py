"""Benefit calculators, every number carries a citation.

`estimate_value` gives a rough annual ₹ value used only to *rank* schemes and to
weight the value-of-information question planner. Its assumptions are explicit
constants below and are shown to users as "estimate".
"""
from __future__ import annotations

from typing import Any

from ..util import inr

# Assumptions used only for ranking / savings estimates (documented in docs/DECISIONS.md)
INFORMAL_RATE = 0.30  # mid-point of the 24–36% moneylender range in the problem brief
FORMAL_RATE = 0.11  # indicative MSME lending rate; actual rate comes from the lender's KFS
DEFAULT_LOAN = 200_000


def _c(source: str, loc: str) -> dict:
    from .engine import resolve_cite
    return resolve_cite({"source": source, "loc": loc})


def _b(en: str, hi: str, display: str | None, source: str, loc: str, amount: float | None = None,
       kind: str = "info") -> dict:
    return {"label": {"en": en, "hi": hi}, "display": display, "amount": amount, "kind": kind, "cite": _c(source, loc)}


def mudra_category(amount: float | None) -> tuple[str, str] | None:
    if amount is None:
        return None
    if amount <= 50_000:
        return ("Shishu", "शिशु")
    if amount <= 5_00_000:
        return ("Kishore", "किशोर")
    if amount <= 10_00_000:
        return ("Tarun", "तरुण")
    if amount <= 20_00_000:
        return ("Tarun Plus", "तरुण प्लस")
    return None


def pmegp_rates(f: dict) -> tuple[float, float] | None:
    """(subsidy rate, own contribution) per PMEGP margin-money table."""
    special, area = f.get("pmegp_special_category"), f.get("area_type")
    if special is None or area is None:
        return None
    if special:
        return (0.35 if area == "rural" else 0.25, 0.05)
    return (0.25 if area == "rural" else 0.15, 0.10)


CGTMSE_FEE_SLABS = [  # (upper bound ₹, standard annual guarantee fee % p.a.), Circular 251/2024-25
    (10_00_000, 0.37), (50_00_000, 0.55), (1_00_00_000, 0.60), (2_00_00_000, 0.85),
    (5_00_00_000, 1.00), (8_00_00_000, 1.10), (10_00_00_000, 1.20),
]


def cgtmse_fee_rate(amount: float, woman: bool) -> float:
    rate = next(r for ub, r in CGTMSE_FEE_SLABS if amount <= ub) if amount <= 10_00_00_000 else 1.20
    return round(rate * (0.9 if woman else 1.0), 4)


def benefits(scheme_id: str, f: dict) -> list[dict]:
    amt = f.get("loan_amount_sought")
    pc = f.get("project_cost")
    out: list[dict] = []
    if scheme_id == "pmmy":
        cat = mudra_category(amt)
        if cat:
            out.append(_b("MUDRA category", "मुद्रा श्रेणी", f"{cat[0]} ({inr(amt)})", "pib_mudra_tarun_plus",
                          "Shishu / Kishore / Tarun / Tarun Plus limits", amt, "category"))
        out.append(_b("No collateral required; loans are covered by the Credit Guarantee Fund for Micro Units (CGFMU)",
                      "कोई गिरवी नहीं; ऋण सूक्ष्म इकाई ऋण गारंटी कोष (CGFMU) से सुरक्षित", None, "mudra_portal",
                      "Collateral-free; CGFMU cover"))
        out.append(_b("Interest is set by the lender and must be disclosed as an APR in a Key Facts Statement",
                      "ब्याज दर बैंक तय करता है और मुख्य तथ्य विवरण (KFS) में वार्षिक दर (APR) बतानी होगी", None,
                      "rbi_kfs_2024", "APR & KFS disclosure for MSME term loans"))
    elif scheme_id == "pmegp":
        rates = pmegp_rates(f)
        if rates:
            sub, own = rates
            out.append(_b("Margin-money subsidy rate", "मार्जिन मनी सब्सिडी दर", f"{int(sub * 100)}% of project cost",
                          "pib_pmegp_2025", "Subsidy table, category × rural/urban", None, "rate"))
            out.append(_b("Your own contribution", "आपका अपना अंशदान", f"{int(own * 100)}% of project cost",
                          "pib_pmegp_2025", "Beneficiary contribution, general 10%, special 5%", None, "rate"))
            if pc:
                out.append(_b("Estimated subsidy", "अनुमानित सब्सिडी", inr(sub * pc), "pib_pmegp_2025",
                              "Subsidy = rate × project cost", sub * pc, "grant"))
                out.append(_b("Bank loan (project cost minus own contribution)", "बैंक ऋण (लागत घटा अपना अंशदान)",
                              inr(pc * (1 - own)), "kvic_pmegp", "Means of finance", pc * (1 - own), "loan"))
        out.append(_b("Entrepreneurship Development Programme (EDP) training before final disbursement",
                      "अंतिम वितरण से पहले उद्यमिता विकास प्रशिक्षण (EDP)", None, "kvic_pmegp", "EDP training"))
    elif scheme_id == "pmegp_upgrade":
        hill = bool(f.get("is_special_region"))
        sub = 0.20 if hill else 0.15
        out.append(_b("Subsidy on the upgrade project", "उन्नयन परियोजना पर सब्सिडी", f"{int(sub * 100)}% of project cost"
                      + (" (NER/hill)" if hill else ""), "pmegp_upgrade", "Subsidy, 15% (20% NER & hill states)", None, "rate"))
        out.append(_b("Your own contribution", "आपका अपना अंशदान", "10% of project cost", "pmegp_upgrade",
                      "Beneficiary contribution", None, "rate"))
        if pc:
            out.append(_b("Estimated subsidy", "अनुमानित सब्सिडी", inr(sub * pc), "pmegp_upgrade", "Subsidy × project cost",
                          sub * pc, "grant"))
    elif scheme_id == "cgtmse":
        a = amt or DEFAULT_LOAN
        out.append(_b("IF your lender is a CGTMSE member and chooses to obtain cover: no collateral or third-party guarantee",
                      "यदि आपका बैंक CGTMSE सदस्य है और गारंटी लेना चुनता है: कोई गिरवी या तीसरे पक्ष की गारंटी नहीं", None,
                      "cgtmse_scheme_doc", "Collateral-free facilities covered by the guarantee", None, "conditional"))
        out.append(_b("Share of the loan covered depends on borrower category, loan size and facility under the current CGTMSE table, "
                      "your lender determines it", "कवर का हिस्सा उधारकर्ता श्रेणी, ऋण राशि और सुविधा पर मौजूदा CGTMSE तालिका से तय होता है, "
                      "आपका बैंक तय करता है", None, "cgtmse_scheme_doc", "Extent of guarantee cover", None, "conditional"))
        rate = cgtmse_fee_rate(a, f.get("gender") == "female")
        out.append(_b("Annual guarantee fee if cover is obtained (often passed on by the lender)",
                      "गारंटी लेने पर वार्षिक शुल्क (अक्सर बैंक आप पर डालता है)",
                      f"{rate}% p.a. ≈ {inr(a * rate / 100)} in year 1", "cgtmse_fee",
                      "Q20 fee slabs; Q17 10% concession for women", a * rate / 100, "fee"))
    elif scheme_id == "pm_vishwakarma":
        out.append(_b("Collateral-free credit, 1st tranche (18 months)", "बिना गिरवी ऋण, पहली किस्त (18 महीने)", "₹1,00,000",
                      "pmv_faq", "FAQ 9; Scheme Benefits 4(a)", 100_000, "loan"))
        out.append(_b("2nd tranche (30 months) after a standard loan account + digital transactions or advanced training",
                      "दूसरी किस्त (30 महीने), मानक ऋण खाता + डिजिटल लेनदेन या उन्नत प्रशिक्षण के बाद", "₹2,00,000",
                      "pmv_faq", "FAQ 10", 200_000, "loan"))
        out.append(_b("Concessional interest to you (Government pays subvention up to 8%)",
                      "आपके लिए रियायती ब्याज (सरकार 8% तक अनुदान देती है)", "5% p.a.", "pmv_faq", "FAQ 12", None, "rate"))
        out.append(_b("No guarantee fee for the artisan", "कारीगर से कोई गारंटी शुल्क नहीं", None, "pmv_faq", "FAQ 13"))
        out.append(_b("Toolkit incentive", "टूलकिट प्रोत्साहन", "up to ₹15,000", "pmv_faq", "FAQ 17", 15_000, "grant"))
    elif scheme_id == "standup_india":
        out.append(_b("Composite loan (term + working capital)", "संयुक्त ऋण (सावधि + कार्यशील पूंजी)", "up to 85% of project cost",
                      "sui_guidelines", "Para 9", None, "rate"))
        out.append(_b("Minimum own contribution", "न्यूनतम अपना अंशदान", "10% of project cost", "sui_guidelines", "Para 11",
                      None, "rate"))
        out.append(_b("Repayment", "पुनर्भुगतान", "up to 7 years with up to 18 months moratorium", "sui_guidelines", "Para 9"))
        out.append(_b("Interest ceiling", "ब्याज सीमा", "bank's MCLR + 3% + tenor premium", "sui_guidelines", "Para 9"))
    elif scheme_id == "pm_svanidhi":
        rep = f.get("svanidhi_tranche_repaid")
        if rep is None:  # never turn unknown history into first-tranche eligibility
            out.append(_b("Loan tranches: ₹15,000, then ₹25,000, then ₹50,000, each after repaying the previous one "
                          "(your repayment history is not yet known)",
                          "किस्तें: ₹15,000, फिर ₹25,000, फिर ₹50,000, हर किस्त पिछली चुकाने के बाद (आपका भुगतान इतिहास अभी ज्ञात नहीं)",
                          None, "svanidhi_portal", "Apply for 15k / 25k / 50k", None, "loan"))
        elif not 0 <= int(rep) <= 3:  # defensive: coerce() already rejects this
            out.append(_b("Repayment history could not be read; the lender checks your SVANidhi record",
                          "भुगतान इतिहास पढ़ा नहीं जा सका, बैंक आपका स्वनिधि रिकॉर्ड देखेगा", None, "svanidhi_portal",
                          "Apply for 15k / 25k / 50k", None, "loan"))
        elif int(rep) == 3:
            out.append(_b("All three loan tranches repaid; there is no further SVANidhi loan tranche",
                          "तीनों किस्तें चुका दी गईं, स्वनिधि की कोई और ऋण किस्त नहीं है", None, "svanidhi_portal",
                          "Apply for 15k / 25k / 50k", None, "loan"))
        else:
            tranche = [15_000, 25_000, 50_000][int(rep)]
            out.append(_b("Your next loan tranche (after " + str(int(rep)) + " fully repaid)", "आपकी अगली ऋण किस्त", inr(tranche),
                          "svanidhi_portal", "Apply for 15k / 25k / 50k", tranche, "loan"))
        out.append(_b("UPI-linked credit card after repaying the 2nd tranche", "दूसरी किस्त चुकाने के बाद UPI-जुड़ा क्रेडिट कार्ड",
                      None, "svanidhi_portal", "Credit card for 2nd-tranche-repaid vendors"))
        out.append(_b("Interest subsidy and digital-payment cashback", "ब्याज सब्सिडी और डिजिटल भुगतान कैशबैक",
                      "7% interest subsidy · cashback up to ₹1,600", "svanidhi_cabinet_2025", "Restructured scheme benefits",
                      1_600, "grant"))
    elif scheme_id == "kcc_ah":
        out.append(_b("No collateral on the first ₹2 lakh (your total KCC limit is assessed by the bank)",
                      "पहले ₹2 लाख पर कोई गिरवी नहीं (कुल KCC सीमा बैंक तय करता है)", "₹2,00,000 collateral-free",
                      "rbi_collateral_free_agri", "Collateral-free agri loans ₹2 lakh from 1 Jan 2025", None, "rate"))
        out.append(_b("Interest subvention on animal-husbandry loans up to ₹2 lakh (with a prompt-repayment incentive)",
                      "₹2 लाख तक के पशुपालन ऋण पर ब्याज अनुदान (समय पर चुकाने पर अतिरिक्त प्रोत्साहन)",
                      "7% headline rate; lower with prompt repayment", "rbi_miss_2026",
                      "MISS, AH-only loans up to ₹2 lakh", None, "rate"))
    elif scheme_id == "day_nrlm":
        out.append(_b("No collateral on group loans up to ₹20 lakh (the limit itself is assessed by the bank)",
                      "₹20 लाख तक के समूह ऋण पर कोई गिरवी नहीं (सीमा बैंक तय करता है)", "₹20,00,000",
                      "rbi_nrlm_mc", "Para 7.3.6(ii)", None, "rate"))
        out.append(_b("No margin up to ₹10 lakh; above that, margin of at most 10% on the excess",
                      "₹10 लाख तक कोई मार्जिन नहीं; उससे ऊपर अधिकतम 10% मार्जिन", None, "rbi_nrlm_mc", "Para 7.3.6(i), (iii)"))
        out.append(_b("Interest for women's SHGs (FY 2025-26 terms; the FY 2026-27 schedule is not yet verified)",
                      "महिला समूहों के लिए ब्याज (वित्त वर्ष 2025-26 की शर्तें, 2026-27 की अनुसूची अभी सत्यापित नहीं)",
                      "7% p.a. up to ₹3 lakh; ₹3–5 lakh at 1-yr MCLR/EBLR or 10%, whichever is lower",
                      "rbi_nrlm_mc", "Annex II Part I (ii)–(iii)", None, "rate"))
    elif scheme_id == "msmed_delayed_payment":
        out.append(_b("Buyers must pay within the agreed period, at most 45 days from acceptance",
                      "खरीदार को तय अवधि में, स्वीकृति से अधिकतम 45 दिन में भुगतान करना होगा", None, "msmed_act", "Section 15"))
        out.append(_b("If a buyer pays late, compound interest at three times the RBI bank rate is due on that invoice",
                      "खरीदार देर से भुगतान करे तो उस बिल पर RBI बैंक दर के तीन गुना चक्रवृद्धि ब्याज देय", None, "msmed_act", "Section 16"))
        if f.get("has_overdue_invoices"):
            out.append(_b("You said an invoice is overdue: keep the invoice, acceptance proof and dates, and file with the Facilitation Council",
                          "आपने बताया कि बिल बकाया है: बिल, स्वीकृति प्रमाण और तिथियाँ रखें और सुविधा परिषद में शिकायत करें",
                          None, "samadhaan_portal", "Online filing"))
        else:
            out.append(_b("No overdue invoice reported; nothing to claim now; keep invoices and acceptance dates",
                          "कोई बकाया बिल नहीं बताया, अभी दावा नहीं; बिल और स्वीकृति तिथियाँ संभालकर रखें",
                          None, "msmed_act", "Sections 15–17"))
    return out


def estimate_value(scheme_id: str, f: dict) -> float:
    """Rough annual ₹ advantage vs. borrowing informally, for ranking only."""
    amt = f.get("loan_amount_sought") or DEFAULT_LOAN
    pc = f.get("project_cost") or amt
    gap = INFORMAL_RATE - FORMAL_RATE
    if scheme_id == "pmmy":
        return min(amt, 20_00_000) * gap
    if scheme_id == "pmegp":
        r = pmegp_rates(f) or (0.25, 0.1)
        return r[0] * pc / 3 + amt * gap  # subsidy amortised over the 3-year lock-in
    if scheme_id == "cgtmse":
        return amt * 0.02  # conditional: only if the lender obtains cover
    if scheme_id == "pmegp_upgrade":
        return (0.20 if f.get("is_special_region") else 0.15) * pc / 3 + amt * gap
    if scheme_id == "pm_vishwakarma":
        return min(amt, 1_00_000) * (INFORMAL_RATE - 0.05) + 15_000
    if scheme_id == "standup_india":
        return max(amt, 10_00_000) * gap
    if scheme_id == "pm_svanidhi":
        return 15_000 * (INFORMAL_RATE - 0.04) + 1_600
    if scheme_id == "kcc_ah":
        return min(amt, 2_00_000) * (INFORMAL_RATE - 0.04)
    if scheme_id == "day_nrlm":
        banded = min(amt, 3_00_000) * (INFORMAL_RATE - 0.07) + max(0, min(amt, 5_00_000) - 3_00_000) * (INFORMAL_RATE - 0.10)
        return banded + max(0, amt - 5_00_000) * gap
    if scheme_id == "msmed_delayed_payment":
        return 5_000.0
    return 0.0


def best_financing_plan(results: list[dict], f: dict) -> dict[str, Any] | None:
    """Pick the primary loan route + stackable add-ons among eligible schemes.

    Loan routes are mutually exclusive for one need; guarantees (CGTMSE) and
    entitlements stack on top of a bank loan.
    """
    loans = [r for r in results if r["eligibility"] == "eligible" and r["kind"] in
             ("loan", "subsidy_loan", "subsidised_loan", "credit_line", "group_loan")
             and r.get("availability", "available") == "available"]
    if not loans:
        return None
    primary = max(loans, key=lambda r: r["est_value"])
    addons = [r["id"] for r in results if r["eligibility"] == "eligible" and r["kind"] in ("guarantee", "entitlement")
              and r["id"] != primary["id"]]
    # CGTMSE only stacks on loans a bank books to an MSE (not SHG / KCC / Vishwakarma's own guarantee)
    if primary["id"] in ("pm_vishwakarma", "kcc_ah", "day_nrlm", "pm_svanidhi"):
        addons = [a for a in addons if a != "cgtmse"]
    alternatives = [r["id"] for r in sorted(loans, key=lambda r: -r["est_value"]) if r["id"] != primary["id"]]
    return {"primary": primary["id"], "addons": addons, "alternatives": alternatives}
