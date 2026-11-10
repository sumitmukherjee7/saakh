"""Demo personas (all synthetic). Each persona's facts are split by the
SIMULATED system that would hold them in production:

  ekyc    – DigiLocker / Aadhaar e-KYC (identity, address → pincode lookup)
  udyam   – Udyam registration API
  bureau  – credit bureau pull (CIBIL / CRIF, simulated)
  answers – what the entrepreneur would say if the agent asks (used by tests
            and the "auto-answer" demo mode only; never shown to the agent)
"""
from __future__ import annotations

from functools import lru_cache

from . import ledger

TAILOR_SEASON = [1.2, 1.15, 0.9, 1.05, 1.1, 0.7, 0.65, 0.8, 0.9, 1.35, 1.4, 1.1]
FAB_SEASON = [1.05, 1.1, 1.3, 1.0, 1.0, 0.75, 0.65, 0.7, 0.85, 1.05, 1.1, 1.15]
DAIRY_SEASON = [1.15, 1.1, 1.0, 0.85, 0.8, 0.85, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2]
LEAF_SEASON = [1.2, 1.2, 1.0, 1.1, 1.15, 0.8, 0.6, 0.7, 0.9, 1.2, 1.3, 1.1]
FOOD_SEASON = [1.1, 1.05, 1.0, 0.95, 0.9, 0.8, 0.75, 0.8, 0.95, 1.1, 1.15, 1.15]
KIRANA_SEASON = [1.0, 1.0, 1.0, 1.0, 1.0, 0.95, 0.95, 0.95, 1.0, 1.1, 1.1, 1.0]

PERSONAS: dict[str, dict] = {
    "sunita": {
        "id": "sunita", "title": {"en": "Sunita, tailor", "hi": "सुनीता, दर्ज़ी"},
        "tagline": {"en": "Boutique & stitching unit, Barabanki (UP). Steady UPI income, no ITR, pays a moneylender every Monday.",
                    "hi": "बुटीक और सिलाई इकाई, बाराबंकी (उ.प्र.)। नियमित UPI आय, ITR नहीं, हर सोमवार साहूकार को भुगतान।"},
        "lang": "hi", "avatar": "🧵",
        "utterance": {"hi": "मुझे दो नई सिलाई मशीनें और एक कढ़ाई मशीन लेनी है, लगभग डेढ़ लाख रुपये चाहिए।",
                      "en": "I want to buy two new sewing machines and an embroidery machine, I need about 1.5 lakh rupees."},
        "ekyc": {"name": "Sunita Devi", "age": 34, "gender": "female", "state": "Uttar Pradesh", "district": "Barabanki",
                 "pincode": "225001", "area_type": "rural", "is_aspirational_district": False, "is_special_region": False},
        "udyam": {"udyam_registered": False},
        "bureau": {"is_defaulter": False, "prior_mudra_tarun_repaid": False, "availed_pmegp": False,
                   "outstanding_mudra_or_svanidhi": False, "has_kcc": False, "svanidhi_tranche_repaid": 0,
                   "score": None, "loans": []},
        "answers": {"business_name": "Sunita Boutique", "sector": "manufacturing", "activity": "tailoring",
                    "ownership_type": "proprietorship", "is_new_unit": False, "years_in_business": 6, "education": "10th",
                    "social_category": "obc", "is_minority": False, "is_ex_serviceman": False, "is_pwd": False,
                    "vishwakarma_trade": "tailor", "is_traditional_family_trade": True,
                    "family_member_in_govt_service": False, "family_member_registered_pmv": False,
                    "availed_other_govt_subsidy": False, "family_member_availed_pmegp": False,
                    "is_street_vendor": False, "owns_milch_animals": False, "has_gst": False, "has_itr": False,
                    "has_collateral": False, "loan_amount_sought": 150000, "project_cost": 165000, "loan_purpose": "machinery",
                    "women_scst_ownership_pct": 100},
        "project": {"items": [["2 × industrial lockstitch machines", 56000], ["Computerised embroidery machine", 64000],
                              ["Fabric & thread stock (working capital)", 45000]], "uplift": 0.25},
        "informal_principal": 50000,
        "ledger": {
            "holder": "SUNITA DEVI", "sweep_target": 14000, "region": "north", "opening": 8200, "branch": "BARABANKI MAIN", "ifsc": "PUNB0123400",
            "seasonality": TAILOR_SEASON, "trend": 0.012, "customer_pool": 260,
            "streams": [
                {"kind": "upi_retail", "per_day": 2.6, "ln_mu": 6.4, "ln_sigma": 0.55, "min": 100, "max": 6000, "tailor": True},
                {"kind": "cash_dep", "weekday": 0, "base": 1800, "p": 0.75},
            ],
            "outflow": {
                "input_ratio": 0.36, "suppliers": [{"name": "SHREE BALAJI TEXTILES", "mode": "UPI"},
                                                   {"name": "GUPTA CLOTH HOUSE", "mode": "UPI"},
                                                   {"name": "LUCKNOW THREAD AND LACE", "mode": "IMPS"}],
                "fixed": [{"kind": "rent", "payee": "RAMESH CHANDRA", "amount": 3500, "day": 5},
                          {"kind": "electricity", "payee": "UPPCL", "amount": 950, "day": 12, "jitter": (0.8, 1.3)},
                          {"kind": "mobile", "payee": "JIO", "amount": 299, "day": 20}],
                "workers": 1, "weekly_wage": 1500, "household": 9000, "atm_per_month": 2,
                "moneylender": "RAMKUMAR YADAV", "ml_amount": 1200, "ml_weekday": 0,
            },
        },
    },
    "ramesh": {
        "id": "ramesh", "title": {"en": "Ramesh, fabricator", "hi": "रमेश, फैब्रिकेटर"},
        "tagline": {"en": "Welding & fabrication workshop, Pimpri-Chinchwad (MH). B2B buyers pay late; one EMI bounced in the monsoon.",
                    "hi": "वेल्डिंग और फैब्रिकेशन वर्कशॉप, पिंपरी-चिंचवड (महाराष्ट्र)। कंपनियाँ देर से भुगतान करती हैं; मानसून में एक EMI बाउंस।"},
        "lang": "en", "avatar": "🔧",
        "utterance": {"en": "I need around 8 lakh for a CNC plasma cutting machine so I can take bigger orders.",
                      "hi": "बड़े ऑर्डर लेने के लिए CNC प्लाज़्मा कटिंग मशीन चाहिए, लगभग 8 लाख।"},
        "ekyc": {"name": "Ramesh Pawar", "age": 41, "gender": "male", "state": "Maharashtra", "district": "Pune",
                 "pincode": "411018", "area_type": "urban", "is_aspirational_district": False, "is_special_region": False},
        "udyam": {"udyam_registered": True, "udyam_number": "UDYAM-MH-26-0123456", "enterprise_class": "micro"},
        "bureau": {"is_defaulter": False, "prior_mudra_tarun_repaid": False, "availed_pmegp": False,
                   "outstanding_mudra_or_svanidhi": False, "has_kcc": False, "svanidhi_tranche_repaid": 0,
                   "score": 712, "loans": [{"lender": "BAJAJ FINANCE", "type": "Equipment loan", "emi": 9800,
                                            "outstanding": 142000, "dpd_max_12m": 30}]},
        "answers": {"business_name": "Pawar Fabrication Works", "sector": "manufacturing", "activity": "fabrication",
                    "ownership_type": "proprietorship", "is_new_unit": False, "years_in_business": 9, "education": "12th",
                    "social_category": "general", "is_minority": False, "is_ex_serviceman": False, "is_pwd": False,
                    "vishwakarma_trade": "none", "is_traditional_family_trade": False,
                    "family_member_in_govt_service": False, "family_member_registered_pmv": False,
                    "availed_other_govt_subsidy": False, "family_member_availed_pmegp": False,
                    "is_street_vendor": False, "owns_milch_animals": False, "has_gst": True, "has_itr": True,
                    "has_collateral": False, "loan_amount_sought": 800000, "project_cost": 900000, "loan_purpose": "machinery",
                    "women_scst_ownership_pct": 0, "has_b2b_buyers": True},
        "project": {"items": [["CNC plasma cutting machine (1500×3000 mm)", 750000], ["Installation & electricals", 50000],
                              ["Steel stock (working capital)", 100000]], "uplift": 0.3},
        "ledger": {
            "holder": "RAMESH PAWAR", "sweep_target": 170000, "region": "west", "opening": 64000, "branch": "PIMPRI MIDC", "ifsc": "BKID0000567",
            "acc_type": "CURRENT", "seasonality": FAB_SEASON, "trend": 0.008, "customer_pool": 60,
            "streams": [
                {"kind": "b2b", "p_per_day": 0.19, "ln_mu": 10.75, "ln_sigma": 0.6,
                 "buyers": ["KALYANI AUTO COMPONENTS PVT LTD", "SAI ENGINEERING WORKS", "PATIL INFRA PROJECTS",
                            "VISHAL CONSTRUCTIONS", "SHREE GANESH STRUCTURALS", "MAHALAXMI WAREHOUSING"]},
                {"kind": "upi_retail", "per_day": 0.7, "ln_mu": 8.3, "ln_sigma": 0.7, "min": 500, "max": 40000},
            ],
            "outflow": {
                "input_ratio": 0.50, "suppliers": [{"name": "JAI MAHARASHTRA STEEL TRADERS", "mode": "IMPS"},
                                                   {"name": "OM SAI GAS AGENCY", "mode": "UPI"},
                                                   {"name": "BHOSARI HARDWARE MART", "mode": "UPI"}],
                "fixed": [{"kind": "rent", "payee": "KISAN KALE", "amount": 15000, "day": 3},
                          {"kind": "electricity", "payee": "MSEDCL", "amount": 7200, "day": 15, "jitter": (0.8, 1.25)},
                          {"kind": "emi", "payee": "BAJAJ FINANCE", "amount": 9800, "day": 7}],
                "workers": 3, "weekly_wage": 3400, "household": 26000, "atm_per_month": 3,
            },
            "force_bounce": [["2026-07", "BAJAJ FINANCE"]],
        },
    },
    "lakshmamma": {
        "id": "lakshmamma", "title": {"en": "Lakshmamma, dairy", "hi": "लक्ष्मम्मा, डेयरी"},
        "tagline": {"en": "4-cow dairy unit, Mandya (Karnataka). Paid fortnightly by the milk union; no formal credit history.",
                    "hi": "4 गायों की डेयरी, मंड्या (कर्नाटक)। दूध संघ से पाक्षिक भुगतान; कोई औपचारिक क्रेडिट इतिहास नहीं।"},
        "lang": "hi", "avatar": "🐄",
        "utterance": {"hi": "मुझे दो और गाय और चारा काटने की मशीन लेनी है, तीन लाख रुपये चाहिए।",
                      "en": "I want two more cows and a chaff cutter, I need three lakh rupees."},
        "ekyc": {"name": "Lakshmamma", "age": 45, "gender": "female", "state": "Karnataka", "district": "Mandya",
                 "pincode": "571401", "area_type": "rural", "is_aspirational_district": False, "is_special_region": False},
        "udyam": {"udyam_registered": False},
        "bureau": {"is_defaulter": False, "prior_mudra_tarun_repaid": False, "availed_pmegp": False,
                   "outstanding_mudra_or_svanidhi": False, "has_kcc": False, "svanidhi_tranche_repaid": 0,
                   "score": None, "loans": []},
        "answers": {"business_name": "Lakshmi Dairy", "sector": "allied_agri", "activity": "dairy",
                    "ownership_type": "individual", "is_new_unit": False, "years_in_business": 12, "education": "below_8",
                    "social_category": "sc", "is_minority": False, "is_ex_serviceman": False, "is_pwd": False,
                    "vishwakarma_trade": "none", "is_traditional_family_trade": False,
                    "family_member_in_govt_service": False, "family_member_registered_pmv": False,
                    "availed_other_govt_subsidy": False, "family_member_availed_pmegp": False,
                    "is_street_vendor": False, "owns_milch_animals": True, "milch_animals": 4, "has_gst": False,
                    "has_itr": False, "has_collateral": False, "loan_amount_sought": 300000, "project_cost": 320000,
                    "loan_purpose": "livestock", "women_scst_ownership_pct": 100},
        "project": {"items": [["2 × HF crossbred cows", 260000], ["Electric chaff cutter", 22000], ["Cattle feed (2 months)", 38000]], "uplift": 0.45},
        "ledger": {
            "holder": "LAKSHMAMMA", "sweep_target": 9000, "region": "south", "opening": 5400, "branch": "MANDYA KR ROAD", "ifsc": "CNRB0001122",
            "seasonality": DAIRY_SEASON, "trend": 0.004, "customer_pool": 40,
            "streams": [
                {"kind": "coop", "days": [1, 16], "base": 17500, "payer": "MANDYA DIST CO OP MILK PRODUCERS UNION"},
                {"kind": "upi_retail", "per_day": 0.5, "ln_mu": 5.3, "ln_sigma": 0.5, "min": 50, "max": 1500},
            ],
            "outflow": {
                "input_ratio": 0.42, "suppliers": [{"name": "NANDINI CATTLE FEED DEPOT", "mode": "UPI"},
                                                   {"name": "SRI RANGA AGRO FEEDS", "mode": "UPI"}],
                "fixed": [{"kind": "electricity", "payee": "CESC MYSORE", "amount": 420, "day": 10, "jitter": (0.8, 1.3)},
                          {"kind": "shg_saving", "payee": "SRI DURGA SHG", "amount": 500, "day": 2}],
                "workers": 0, "household": 8500, "atm_per_month": 3,
            },
        },
    },
    "shg": {
        "id": "shg", "title": {"en": "Jai Maa Durga SHG, leaf plates", "hi": "जय माँ दुर्गा SHG, पत्तल-दोना"},
        "tagline": {"en": "12-member women's SHG, Khunti (Jharkhand). Makes sal-leaf plates; wants a pressing unit.",
                    "hi": "12 सदस्यीय महिला SHG, खूंटी (झारखंड)। साल पत्तों के पत्तल बनाती हैं; प्रेसिंग यूनिट चाहिए।"},
        "lang": "hi", "avatar": "🍃",
        "utterance": {"hi": "हमारे समूह को पत्तल दबाने की दो मशीनें और पत्तों का स्टॉक चाहिए, लगभग चार लाख।",
                      "en": "Our group needs two leaf-plate pressing machines and leaf stock, about four lakh."},
        "ekyc": {"name": "Jai Maa Durga Mahila SHG (President: Phulmani Munda)", "age": 38, "gender": "female",
                 "state": "Jharkhand", "district": "Khunti", "pincode": "835210", "area_type": "rural",
                 "is_aspirational_district": True, "is_special_region": False},
        "udyam": {"udyam_registered": False},
        "bureau": {"is_defaulter": False, "prior_mudra_tarun_repaid": False, "availed_pmegp": False,
                   "outstanding_mudra_or_svanidhi": False, "has_kcc": False, "svanidhi_tranche_repaid": 0,
                   "score": None, "loans": [{"lender": "BANK OF INDIA", "type": "SHG cash credit", "emi": 5200,
                                             "outstanding": 61000, "dpd_max_12m": 0}]},
        "answers": {"business_name": "Jai Maa Durga Mahila SHG", "sector": "manufacturing", "activity": "leaf_plates",
                    "ownership_type": "shg", "is_new_unit": True, "years_in_business": 2, "education": "8th",
                    "social_category": "st", "is_minority": False, "is_ex_serviceman": False, "is_pwd": False,
                    "vishwakarma_trade": "none", "is_traditional_family_trade": False,
                    "family_member_in_govt_service": False, "family_member_registered_pmv": False,
                    "availed_other_govt_subsidy": False, "family_member_availed_pmegp": False,
                    "is_street_vendor": False, "owns_milch_animals": False, "has_gst": False, "has_itr": False,
                    "has_collateral": False, "loan_amount_sought": 400000, "project_cost": 450000, "loan_purpose": "both",
                    "shg_members": 12, "shg_age_months": 30, "shg_women_only": True, "shg_grading_passed": True,
                    "women_scst_ownership_pct": 100},
        "project": {"items": [["2 × hydraulic dona-pattal pressing machines", 190000], ["Shed repair & wiring", 60000],
                              ["Sal-leaf stock & packing (working capital)", 200000]], "uplift": 0.4},
        "ledger": {
            "holder": "JAI MAA DURGA MAHILA SHG", "sweep_target": 55000, "region": "east", "opening": 21000, "branch": "KHUNTI", "ifsc": "BKID0004410",
            "seasonality": LEAF_SEASON, "trend": 0.01, "customer_pool": 35,
            "streams": [
                {"kind": "b2b", "p_per_day": 0.16, "ln_mu": 8.9, "ln_sigma": 0.45,
                 "buyers": ["RANCHI DISPOSABLES", "MAA TARINI CATERERS", "SHIV SHAKTI TENT HOUSE", "BIRSA HAAT TRADERS"]},
                {"kind": "upi_retail", "per_day": 0.9, "ln_mu": 6.2, "ln_sigma": 0.6, "min": 100, "max": 5000},
                {"kind": "cash_dep", "weekday": 2, "base": 2600, "p": 0.85},
            ],
            "one_off_in": [{"date": "2026-01-14", "amount": 15000, "payer": "JSLPS REVOLVING FUND"},
                           {"date": "2026-04-09", "amount": 50000, "payer": "JSLPS CIF COMMUNITY INVESTMENT FUND"}],
            "outflow": {
                "input_ratio": 0.38, "suppliers": [{"name": "SAL PATTA SANGRAHAK SAMITI", "mode": "UPI"},
                                                   {"name": "KHUNTI PACKAGING", "mode": "UPI"}],
                "fixed": [{"kind": "emi", "payee": "BOI SHG CC", "amount": 5200, "day": 10},
                          {"kind": "electricity", "payee": "JBVNL", "amount": 650, "day": 18, "jitter": (0.8, 1.3)}],
                "workers": 4, "weekly_wage": 900, "household": 2500, "atm_per_month": 1,
            },
        },
    },
    "imran": {
        "id": "imran", "title": {"en": "Imran, street food", "hi": "इमरान, ठेला"},
        "tagline": {"en": "Chai & snacks cart, Bhopal (MP). Hundreds of tiny UPI payments; no vending certificate yet.",
                    "hi": "चाय-नाश्ते का ठेला, भोपाल (म.प्र.)। सैकड़ों छोटे UPI भुगतान; अभी वेंडिंग प्रमाणपत्र नहीं।"},
        "lang": "hi", "avatar": "☕",
        "utterance": {"hi": "ठेले के लिए नया गैस चूल्हा और सामान चाहिए, पच्चीस हज़ार रुपये।",
                      "en": "I need a new gas stove and stock for my cart, 25 thousand rupees."},
        "ekyc": {"name": "Imran Shaikh", "age": 29, "gender": "male", "state": "Madhya Pradesh", "district": "Bhopal",
                 "pincode": "462001", "area_type": "urban", "is_aspirational_district": False, "is_special_region": False},
        "udyam": {"udyam_registered": False},
        "bureau": {"is_defaulter": False, "prior_mudra_tarun_repaid": False, "availed_pmegp": False,
                   "outstanding_mudra_or_svanidhi": False, "has_kcc": False, "svanidhi_tranche_repaid": 0,
                   "score": None, "loans": []},
        "answers": {"business_name": "Imran Chai Corner", "sector": "trading", "activity": "street_food",
                    "ownership_type": "individual", "is_new_unit": False, "years_in_business": 5, "education": "10th",
                    "social_category": "obc", "is_minority": True, "is_ex_serviceman": False, "is_pwd": False,
                    "vishwakarma_trade": "none", "is_traditional_family_trade": False,
                    "family_member_in_govt_service": False, "family_member_registered_pmv": False,
                    "availed_other_govt_subsidy": False, "family_member_availed_pmegp": False,
                    "is_street_vendor": True, "has_vending_certificate_or_lor": False, "owns_milch_animals": False,
                    "has_gst": False, "has_itr": False, "has_collateral": False, "loan_amount_sought": 25000,
                    "project_cost": 28000, "loan_purpose": "both", "women_scst_ownership_pct": 0},
        "project": {"items": [["Commercial 2-burner gas stove + cylinder", 14000], ["Cart repair & canopy", 6000],
                              ["Stock (tea, milk, snacks)", 8000]], "uplift": 0.1},
        "ledger": {
            "holder": "IMRAN SHAIKH", "sweep_target": 6000, "region": "central", "opening": 1900, "branch": "BHOPAL NEW MARKET", "ifsc": "SBIN0004321",
            "seasonality": FOOD_SEASON, "trend": 0.006, "customer_pool": 400,
            "streams": [{"kind": "upi_retail", "per_day": 21, "ln_mu": 3.9, "ln_sigma": 0.5, "min": 10, "max": 600}],
            "outflow": {
                "input_ratio": 0.55, "suppliers": [{"name": "BHOPAL DAIRY SANGH BOOTH", "mode": "UPI"},
                                                   {"name": "NEW MARKET WHOLESALE", "mode": "UPI"},
                                                   {"name": "HP GAS AGENCY", "mode": "UPI"}],
                "fixed": [{"kind": "mobile", "payee": "AIRTEL", "amount": 349, "day": 8}],
                "workers": 0, "household": 7000, "atm_per_month": 2,
            },
        },
    },
    "mohan": {
        "id": "mohan", "title": {"en": "Mohan, kirana (stressed)", "hi": "मोहन, किराना (दबाव में)"},
        "tagline": {"en": "Kirana store, Sitapur (UP). Falling sales, two moneylenders, repeated EMI bounces, shows the 'not yet' path.",
                    "hi": "किराना दुकान, सीतापुर (उ.प्र.)। घटती बिक्री, दो साहूकार, बार-बार EMI बाउंस, 'अभी नहीं' का रास्ता।"},
        "lang": "hi", "avatar": "🏪",
        "utterance": {"hi": "दुकान में माल भरने के लिए तीन लाख चाहिए।", "en": "I need three lakh to restock my shop."},
        "ekyc": {"name": "Mohan Lal", "age": 52, "gender": "male", "state": "Uttar Pradesh", "district": "Sitapur",
                 "pincode": "261001", "area_type": "urban", "is_aspirational_district": True, "is_special_region": False},
        "udyam": {"udyam_registered": True, "udyam_number": "UDYAM-UP-61-0098765", "enterprise_class": "micro"},
        "bureau": {"is_defaulter": False, "prior_mudra_tarun_repaid": False, "availed_pmegp": False,
                   "outstanding_mudra_or_svanidhi": False, "has_kcc": False, "svanidhi_tranche_repaid": 0,
                   "score": 618, "loans": [{"lender": "UJJIVAN SFB", "type": "Business loan", "emi": 8400,
                                            "outstanding": 210000, "dpd_max_12m": 60}]},
        "answers": {"business_name": "Mohan General Store", "sector": "trading", "activity": "retail",
                    "ownership_type": "proprietorship", "is_new_unit": False, "years_in_business": 15, "education": "8th",
                    "social_category": "general", "is_minority": False, "is_ex_serviceman": False, "is_pwd": False,
                    "vishwakarma_trade": "none", "is_traditional_family_trade": False,
                    "family_member_in_govt_service": False, "family_member_registered_pmv": False,
                    "availed_other_govt_subsidy": False, "family_member_availed_pmegp": False,
                    "is_street_vendor": False, "owns_milch_animals": False, "has_gst": True, "has_itr": False,
                    "has_collateral": True, "loan_amount_sought": 300000, "project_cost": 300000,
                    "loan_purpose": "working_capital", "women_scst_ownership_pct": 0, "has_b2b_buyers": False},
        "project": {"items": [["Grocery & FMCG restocking", 300000]], "uplift": 0.05},
        "ledger": {
            "holder": "MOHAN LAL", "region": "north", "opening": 3100, "branch": "SITAPUR CIVIL LINES", "ifsc": "UJVN0001234",
            "acc_type": "CURRENT", "seasonality": KIRANA_SEASON, "trend": -0.035, "customer_pool": 220,
            "streams": [{"kind": "upi_retail", "per_day": 9, "ln_mu": 5.0, "ln_sigma": 0.6, "min": 20, "max": 3000},
                        {"kind": "cash_dep", "weekday": 1, "base": 2500, "p": 0.6}],
            "outflow": {
                "input_ratio": 0.80, "suppliers": [{"name": "SITAPUR FMCG DISTRIBUTORS", "mode": "IMPS"},
                                                   {"name": "AGARWAL TRADERS", "mode": "UPI"}],
                "fixed": [{"kind": "emi", "payee": "UJJIVAN SFB", "amount": 8400, "day": 5},
                          {"kind": "electricity", "payee": "UPPCL", "amount": 1600, "day": 14, "jitter": (0.8, 1.3)}],
                "workers": 0, "household": 15000, "atm_per_month": 4,
                "moneylender": "SURESH SAHU", "ml_amount": 1500, "ml_weekday": 3,
            },
            "force_bounce": [["2026-03", "UJJIVAN SFB"], ["2026-06", "UJJIVAN SFB"], ["2026-09", "UJJIVAN SFB"]],
        },
    },
}

SEEDS = {"sunita": 11, "ramesh": 23, "lakshmamma": 37, "shg": 41, "imran": 53, "mohan": 67}


@lru_cache(maxsize=None)
def statement(pid: str) -> dict:
    return ledger.generate(PERSONAS[pid]["ledger"], SEEDS[pid])


def public_persona(pid: str) -> dict:
    p = PERSONAS[pid]
    return {"id": pid, "title": p["title"], "tagline": p["tagline"], "lang": p["lang"], "avatar": p["avatar"],
            "utterance": p["utterance"], "name": p["ekyc"]["name"],
            "district": p["ekyc"]["district"], "state": p["ekyc"]["state"]}

# Answers to questions added after the external review (MSME class needs investment AND
# turnover; PMEGP second-loan pathway; claim-ready delayed payments; special SHGs).
_EXTRA = {
    "sunita": {"plant_investment": 85000, "prior_scheme_unit": "none", "has_overdue_invoices": False},
    "ramesh": {"plant_investment": 1800000, "prior_scheme_unit": "none", "has_overdue_invoices": True},
    "lakshmamma": {"plant_investment": 250000, "prior_scheme_unit": "none", "has_overdue_invoices": False},
    "shg": {"plant_investment": 60000, "prior_scheme_unit": "none", "has_overdue_invoices": False, "shg_small_special": True, "shg_mixed_special": False},
    "imran": {"plant_investment": 25000, "prior_scheme_unit": "none", "has_overdue_invoices": False},
    "mohan": {"plant_investment": 400000, "prior_scheme_unit": "none", "has_overdue_invoices": False},
}
for _pid in PERSONAS:
    _EXTRA.setdefault(_pid, {}).setdefault("other_govt_selfemp_loan_5y", False)
    _EXTRA[_pid].setdefault("negative_list_declared", "no")
for _pid, _ex in _EXTRA.items():
    PERSONAS[_pid]["answers"].update(_ex)
