"""Monthly cash-flow aggregates and the credit features computed from them.

The *same* `compute_features` function is used by (a) the synthetic population
the model is trained on and (b) live applicants' bank statements, so training /
serving skew is impossible by construction.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np


@dataclass
class Monthly:
    months: list[str]
    biz_in: list[float]
    biz_out: list[float]
    hh_out: list[float]
    emi_out: list[float]
    informal_out: list[float]
    avg_bal: list[float]
    payers: list[int]
    other_in: list[float] = field(default_factory=list)
    end_bal: list[float] = field(default_factory=list)
    top_payer_share: float = 0.0
    bounces: int = 0
    active_week_share: float = 1.0
    digital_share: float = 1.0
    transfers_out: list[float] = field(default_factory=list)  # part of hh_out; discretionary, used for affordability

    def to_dict(self) -> dict:
        return asdict(self)


# name, direction (+1 = higher is better), labels, improvement advice template
FEATURE_META: dict[str, dict] = {
    "inflow_cv": {"dir": -1, "label": {"en": "Income stability (month-to-month swings)", "hi": "आय की स्थिरता (महीने-दर-महीने उतार-चढ़ाव)"},
                  "advice": {"en": "Smooth lean months, take advance orders or add a steady product line.",
                             "hi": "कमज़ोर महीनों को संभालें, एडवांस ऑर्डर लें या कोई स्थिर उत्पाद जोड़ें।"}, "fmt": "pct"},
    "inflow_trend": {"dir": 1, "label": {"en": "Sales growth over the year", "hi": "साल भर में बिक्री वृद्धि"},
                     "advice": {"en": "Growth in recent months strengthens the case.", "hi": "हाल के महीनों में वृद्धि से आवेदन मज़बूत होता है।"},
                     "fmt": "pct"},
    "min_to_median": {"dir": 1, "label": {"en": "Lean-month income vs a normal month", "hi": "कमज़ोर महीने की आय बनाम सामान्य महीना"},
                      "advice": {"en": "A repayment schedule matched to your season protects lean months.",
                                 "hi": "मौसम के अनुसार किस्तें कमज़ोर महीनों को बचाती हैं।"}, "fmt": "pct"},
    "margin_ratio": {"dir": 1, "label": {"en": "Money left after business & household costs", "hi": "व्यवसाय और घर के खर्च के बाद बची राशि"},
                     "advice": {"en": "Separate household spending from the business account where possible.",
                                "hi": "जहाँ संभव हो, घरेलू खर्च को व्यवसाय खाते से अलग रखें।"}, "fmt": "pct"},
    "debt_service_ratio": {"dir": -1, "label": {"en": "Existing repayments as share of income", "hi": "आय में मौजूदा किस्तों का हिस्सा"},
                           "advice": {"en": "Closing or refinancing a costly loan first frees repayment capacity.",
                                      "hi": "पहले महँगा ऋण बंद या पुनर्वित्त करने से क्षमता बढ़ती है।"}, "fmt": "pct"},
    "informal_share": {"dir": -1, "label": {"en": "Repayments to moneylenders", "hi": "साहूकार को भुगतान"},
                       "advice": {"en": "Moving the moneylender loan to formal credit lowers cost and improves this factor.",
                                  "hi": "साहूकार का ऋण औपचारिक ऋण में बदलने से लागत घटती है और यह कारक सुधरता है।"}, "fmt": "pct"},
    "buffer_days": {"dir": 1, "label": {"en": "Cash buffer (days of expenses in the account)", "hi": "नकद बफ़र (खाते में कितने दिनों का खर्च)"},
                    "advice": {"en": "Keep a little more balance in the account through the month.",
                               "hi": "महीने भर खाते में थोड़ा अधिक बैलेंस रखें।"}, "fmt": "days"},
    "bounces_12m": {"dir": -1, "label": {"en": "EMI / cheque bounces in 12 months", "hi": "12 महीनों में EMI / चेक बाउंस"},
                    "advice": {"en": "Six months without a bounce noticeably improves the score.",
                               "hi": "छह महीने बिना बाउंस के स्कोर में साफ़ सुधार होता है।"}, "fmt": "int"},
    "payer_diversity": {"dir": 1, "label": {"en": "Breadth of paying customers", "hi": "भुगतान करने वाले ग्राहकों की संख्या"},
                        "advice": {"en": "Ask cash customers to pay by UPI; it makes your real customer base visible.",
                                   "hi": "नकद ग्राहकों से UPI से भुगतान करवाएँ, इससे आपके असली ग्राहक दिखते हैं।"}, "fmt": "log"},
    "top_payer_share": {"dir": -1, "label": {"en": "Dependence on the largest customer", "hi": "सबसे बड़े ग्राहक पर निर्भरता"},
                        "advice": {"en": "Adding buyers reduces concentration risk.", "hi": "और खरीदार जोड़ने से जोखिम घटता है।"}, "fmt": "pct"},
    "months_active": {"dir": 1, "label": {"en": "Length of transaction history", "hi": "लेनदेन इतिहास की अवधि"},
                      "advice": {"en": "Link another account or keep transacting digitally to lengthen history.",
                                 "hi": "दूसरा खाता जोड़ें या डिजिटल लेनदेन जारी रखें।"}, "fmt": "months"},
    "neg_months_share": {"dir": -1, "label": {"en": "Months where spending exceeded income", "hi": "महीने जब खर्च आय से अधिक था"},
                         "advice": {"en": "Plan large purchases in peak months.", "hi": "बड़ी खरीदारी व्यस्त महीनों में करें।"}, "fmt": "pct"},
    "proposed_dsr": {"dir": -1, "label": {"en": "New EMI as a share of monthly income", "hi": "मासिक आय में नई EMI का हिस्सा"},
                     "advice": {"en": "A smaller first loan (or longer tenure) lowers this; you can step up after 12 months of good repayment.",
                                "hi": "छोटा पहला ऋण (या लंबी अवधि) इसे घटाता है, 12 महीने अच्छे भुगतान के बाद ऋण बढ़ा सकते हैं।"},
                     "fmt": "pct", "loan": True},
    # Candidate features that the fairness ablation evaluates (see risk/train.py):
    "log_avg_inflow": {"dir": 1, "label": {"en": "Business size (average monthly inflow)", "hi": "व्यवसाय का आकार (औसत मासिक आय)"},
                       "advice": {"en": "", "hi": ""}, "fmt": "log", "candidate": True},
    "digital_share": {"dir": 1, "label": {"en": "Share of sales received digitally", "hi": "डिजिटल माध्यम से प्राप्त बिक्री का हिस्सा"},
                      "advice": {"en": "", "hi": ""}, "fmt": "pct", "candidate": True},
}

ALL_FEATURES = list(FEATURE_META)


def _slope_log(x: np.ndarray) -> float:
    if len(x) < 3:
        return 0.0
    y = np.log(np.maximum(x, 1.0))
    t = np.arange(len(y), dtype=float)
    t -= t.mean()
    return float((t * (y - y.mean())).sum() / (t * t).sum())


def compute_features(m: Monthly, season_index: list[float] | None = None) -> dict[str, float]:
    """`season_index` (Jan..Dec) de-seasonalises income before measuring trend."""
    bi = np.asarray(m.biz_in, dtype=float)
    if season_index is not None and m.months:
        idx = np.asarray([season_index[int(mk[5:7]) - 1] for mk in m.months])
        bi_trend = bi / idx
    else:
        bi_trend = bi
    bo = np.asarray(m.biz_out, dtype=float)
    ho = np.asarray(m.hh_out, dtype=float)
    em = np.asarray(m.emi_out, dtype=float)
    inf = np.asarray(m.informal_out, dtype=float)
    ab = np.asarray(m.avg_bal, dtype=float)
    n = len(bi)
    tot_in = max(bi.sum(), 1.0)
    mean_in = max(bi.mean(), 1.0)
    total_out = bo + ho + em + inf
    daily_out = max(total_out.mean() / 30.0, 1.0)
    net = bi - total_out
    return {
        "inflow_cv": float(np.std(bi) / mean_in),
        "inflow_trend": float(np.clip(_slope_log(bi_trend) * 12, -1.5, 1.5)),
        "min_to_median": float(bi.min() / max(np.median(bi), 1.0)),
        "margin_ratio": float(np.clip((bi.sum() - bo.sum() - ho.sum()) / tot_in, -1, 1)),
        "debt_service_ratio": float(np.clip((em.sum() + inf.sum()) / tot_in, 0, 2)),
        "informal_share": float(np.clip(inf.sum() / tot_in, 0, 1)),
        "buffer_days": float(np.clip(ab.mean() / daily_out, 0, 120)),
        "bounces_12m": float(m.bounces * 12.0 / max(n, 1)),
        "payer_diversity": float(math.log1p(np.mean(m.payers) if m.payers else 0.0)),
        "top_payer_share": float(m.top_payer_share),
        "months_active": float(n),
        "neg_months_share": float((net < 0).mean()),
        "log_avg_inflow": float(math.log(mean_in)),
        "digital_share": float(m.digital_share),
    }
