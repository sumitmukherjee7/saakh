"""Registry of applicant facts.

Every fact the scheme engine, the risk model or the document planner reads is
declared here once, with:
  * its type and allowed values,
  * where it can come from (eKYC, Account Aggregator, Udyam, bureau, the user),
  * the question we ask when it is unknown (English + Hindi),
  * why we ask it (DPDP purpose limitation: we only ask what changes an outcome),
  * a prior distribution used by the value-of-information question planner,
  * an optional *action* that can change the fact (e.g. "register on Udyam").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

L = dict[str, str]  # {"en": ..., "hi": ...}


@dataclass
class Option:
    value: Any
    label: L


@dataclass
class Action:
    id: str
    label: L
    target: Any  # value the fact takes once the action is done
    effort: L  # human description of effort / cost
    url: str | None = None


@dataclass
class Fact:
    key: str
    type: str  # bool | int | money | enum | str
    label: L
    question: L | None = None
    why: L | None = None
    options: list[Option] = field(default_factory=list)
    source: str = "user"  # user | ekyc | aa | udyam | bureau | derived
    sensitive: bool = False
    prior: dict[Any, float] | None = None
    action: Action | None = None
    unit: str | None = None
    bounds: tuple[int, int] | None = None  # inclusive range for int facts


def yes_no() -> list[Option]:
    return [Option(True, {"en": "Yes", "hi": "हाँ"}), Option(False, {"en": "No", "hi": "नहीं"})]


SECTORS = [
    Option("manufacturing", {"en": "Making / manufacturing", "hi": "उत्पादन / निर्माण"}),
    Option("services", {"en": "Services", "hi": "सेवा"}),
    Option("trading", {"en": "Trading / shop", "hi": "व्यापार / दुकान"}),
    Option("allied_agri", {"en": "Dairy / poultry / fishery", "hi": "डेयरी / पशुपालन / मत्स्य"}),
    Option("crop_farming", {"en": "Crop farming", "hi": "खेती"}),
]

ACTIVITIES = [
    Option("tailoring", {"en": "Tailoring / boutique", "hi": "सिलाई / बुटीक"}),
    Option("fabrication", {"en": "Welding / fabrication", "hi": "वेल्डिंग / फैब्रिकेशन"}),
    Option("dairy", {"en": "Dairy (milch animals)", "hi": "डेयरी (दुधारू पशु)"}),
    Option("leaf_plates", {"en": "Leaf plates / food processing", "hi": "पत्तल-दोना / खाद्य प्रसंस्करण"}),
    Option("food_processing", {"en": "Food processing", "hi": "खाद्य प्रसंस्करण"}),
    Option("street_food", {"en": "Street food / vending", "hi": "ठेला / फेरी"}),
    Option("retail", {"en": "Kirana / retail shop", "hi": "किराना / दुकान"}),
    Option("repair_services", {"en": "Repair services", "hi": "मरम्मत सेवा"}),
    Option("liquor_tobacco", {"en": "Liquor / tobacco", "hi": "शराब / तंबाकू"}),
    Option("other", {"en": "Other", "hi": "अन्य"}),
]

VISHWAKARMA_TRADES = [
    "carpenter", "boat_maker", "armourer", "blacksmith", "hammer_toolkit_maker", "locksmith",
    "goldsmith", "potter", "sculptor_stone_breaker", "cobbler", "mason", "basket_mat_broom_maker",
    "doll_toy_maker", "barber", "garland_maker", "washerman", "tailor", "fishing_net_maker",
]
VISHWAKARMA_LABELS = {
    "carpenter": ("Carpenter (Suthar)", "बढ़ई (सुथार)"),
    "boat_maker": ("Boat maker", "नाव निर्माता"),
    "armourer": ("Armourer", "अस्त्रकार"),
    "blacksmith": ("Blacksmith (Lohar)", "लोहार"),
    "hammer_toolkit_maker": ("Hammer & tool kit maker", "हथौड़ा और टूलकिट निर्माता"),
    "locksmith": ("Locksmith", "ताला बनाने वाला"),
    "goldsmith": ("Goldsmith (Sonar)", "सुनार"),
    "potter": ("Potter (Kumhaar)", "कुम्हार"),
    "sculptor_stone_breaker": ("Sculptor / stone breaker", "मूर्तिकार / पत्थर तोड़ने वाला"),
    "cobbler": ("Cobbler (Charmkar)", "मोची (चर्मकार)"),
    "mason": ("Mason (Rajmistri)", "राजमिस्त्री"),
    "basket_mat_broom_maker": ("Basket / mat / broom maker", "टोकरी / चटाई / झाड़ू निर्माता"),
    "doll_toy_maker": ("Doll & toy maker", "गुड़िया और खिलौना निर्माता"),
    "barber": ("Barber (Naai)", "नाई"),
    "garland_maker": ("Garland maker (Malakaar)", "माला बनाने वाला (मालाकार)"),
    "washerman": ("Washerman (Dhobi)", "धोबी"),
    "tailor": ("Tailor (Darzi)", "दर्ज़ी"),
    "fishing_net_maker": ("Fishing net maker", "मछली का जाल बनाने वाला"),
}

EDUCATION = [
    Option("none", {"en": "No schooling", "hi": "स्कूल नहीं गए"}),
    Option("below_8", {"en": "Below 8th", "hi": "8वीं से कम"}),
    Option("8th", {"en": "8th pass", "hi": "8वीं पास"}),
    Option("10th", {"en": "10th pass", "hi": "10वीं पास"}),
    Option("12th", {"en": "12th pass", "hi": "12वीं पास"}),
    Option("graduate", {"en": "Graduate or above", "hi": "स्नातक या अधिक"}),
]
EDU_RANK = {o.value: i for i, o in enumerate(EDUCATION)}

FACTS: dict[str, Fact] = {}


def _f(f: Fact) -> Fact:
    FACTS[f.key] = f
    return f


# ---- identity (eKYC via DigiLocker / Aadhaar, simulated) -------------------
_f(Fact("name", "str", {"en": "Name", "hi": "नाम"}, source="ekyc"))
_f(Fact("age", "int", {"en": "Age", "hi": "आयु"}, source="ekyc",
        question={"en": "How old are you?", "hi": "आपकी उम्र कितनी है?"},
        why={"en": "Most schemes have a minimum age of 18.", "hi": "ज़्यादातर योजनाओं में न्यूनतम आयु 18 वर्ष है।"},
        prior={30: 0.4, 45: 0.45, 62: 0.15}, unit="years"))
_f(Fact("gender", "enum", {"en": "Gender", "hi": "लिंग"}, source="ekyc",
        options=[Option("female", {"en": "Woman", "hi": "महिला"}), Option("male", {"en": "Man", "hi": "पुरुष"}),
                 Option("transgender", {"en": "Transgender", "hi": "ट्रांसजेंडर"})],
        question={"en": "Are you a woman, a man, or transgender?", "hi": "आप महिला हैं, पुरुष हैं या ट्रांसजेंडर?"},
        why={"en": "Women entrepreneurs get higher subsidy and guarantee cover in several schemes.",
             "hi": "कई योजनाओं में महिला उद्यमियों को अधिक सब्सिडी और गारंटी मिलती है।"},
        prior={"female": 0.45, "male": 0.53, "transgender": 0.02}))
_f(Fact("social_category", "enum", {"en": "Social category", "hi": "सामाजिक वर्ग"}, sensitive=True,
        options=[Option("general", {"en": "General", "hi": "सामान्य"}), Option("obc", {"en": "OBC", "hi": "अन्य पिछड़ा वर्ग"}),
                 Option("sc", {"en": "SC", "hi": "अनुसूचित जाति"}), Option("st", {"en": "ST", "hi": "अनुसूचित जनजाति"})],
        question={"en": "Which social category do you belong to? (optional; only used for scheme benefits)",
                  "hi": "आप किस सामाजिक वर्ग से हैं? (वैकल्पिक, केवल योजना लाभ के लिए)"},
        why={"en": "SC/ST/OBC applicants get higher PMEGP subsidy; this is never used in credit scoring.",
             "hi": "SC/ST/OBC आवेदकों को PMEGP में अधिक सब्सिडी मिलती है; इसका उपयोग क्रेडिट स्कोर में कभी नहीं होता।"},
        prior={"general": 0.3, "obc": 0.42, "sc": 0.18, "st": 0.10}))
_f(Fact("is_minority", "bool", {"en": "Minority community", "hi": "अल्पसंख्यक समुदाय"}, sensitive=True, options=yes_no(),
        question={"en": "Do you belong to a notified minority community? (optional)", "hi": "क्या आप अधिसूचित अल्पसंख्यक समुदाय से हैं? (वैकल्पिक)"},
        why={"en": "Minorities are a PMEGP special category.", "hi": "अल्पसंख्यक PMEGP की विशेष श्रेणी में आते हैं।"},
        prior={True: 0.2, False: 0.8}))
_f(Fact("is_ex_serviceman", "bool", {"en": "Ex-serviceman", "hi": "पूर्व सैनिक"}, options=yes_no(), prior={True: 0.02, False: 0.98},
        question={"en": "Are you an ex-serviceman?", "hi": "क्या आप पूर्व सैनिक हैं?"}))
_f(Fact("is_pwd", "bool", {"en": "Person with disability", "hi": "दिव्यांग"}, options=yes_no(), sensitive=True,
        prior={True: 0.03, False: 0.97},
        question={"en": "Do you have a disability certificate? (optional)", "hi": "क्या आपके पास दिव्यांगता प्रमाणपत्र है? (वैकल्पिक)"}))
_f(Fact("education", "enum", {"en": "Education", "hi": "शिक्षा"}, options=EDUCATION,
        question={"en": "Up to which class have you studied?", "hi": "आपने किस कक्षा तक पढ़ाई की है?"},
        why={"en": "PMEGP needs 8th pass for larger projects.", "hi": "बड़ी PMEGP परियोजनाओं के लिए 8वीं पास ज़रूरी है।"},
        prior={"below_8": 0.3, "8th": 0.2, "10th": 0.3, "graduate": 0.2}))

# ---- location (derived from pincode, simulated lookup) ---------------------
_f(Fact("state", "str", {"en": "State", "hi": "राज्य"}, source="ekyc"))
_f(Fact("district", "str", {"en": "District", "hi": "ज़िला"}, source="ekyc"))
_f(Fact("pincode", "str", {"en": "PIN code", "hi": "पिन कोड"}, source="ekyc"))
_f(Fact("area_type", "enum", {"en": "Rural or urban", "hi": "ग्रामीण या शहरी"}, source="derived",
        options=[Option("rural", {"en": "Village / rural", "hi": "गाँव / ग्रामीण"}), Option("urban", {"en": "Town / city", "hi": "शहर / कस्बा"})],
        question={"en": "Is your business in a village or in a town/city?", "hi": "आपका व्यवसाय गाँव में है या शहर/कस्बे में?"},
        why={"en": "Rural units get a higher PMEGP subsidy.", "hi": "ग्रामीण इकाइयों को PMEGP में अधिक सब्सिडी मिलती है।"},
        prior={"rural": 0.55, "urban": 0.45}))
_f(Fact("is_special_region", "bool", {"en": "NER / hill / border area", "hi": "पूर्वोत्तर / पहाड़ी / सीमा क्षेत्र"}, source="derived",
        options=yes_no(), prior={True: 0.08, False: 0.92}))
_f(Fact("is_aspirational_district", "bool", {"en": "Aspirational district", "hi": "आकांक्षी ज़िला"}, source="derived",
        options=yes_no(), prior={True: 0.15, False: 0.85}))

# ---- business ---------------------------------------------------------------
_f(Fact("business_name", "str", {"en": "Business name", "hi": "व्यवसाय का नाम"}))
_f(Fact("sector", "enum", {"en": "Sector", "hi": "क्षेत्र"}, options=SECTORS,
        question={"en": "What kind of work does your business do?", "hi": "आपका व्यवसाय किस तरह का काम करता है?"},
        prior={"manufacturing": 0.3, "services": 0.3, "trading": 0.25, "allied_agri": 0.15}))
_f(Fact("activity", "enum", {"en": "Activity", "hi": "गतिविधि"}, options=ACTIVITIES,
        question={"en": "What exactly do you make or sell?", "hi": "आप असल में क्या बनाते या बेचते हैं?"}))
_f(Fact("is_new_unit", "bool", {"en": "New unit (greenfield)", "hi": "नई इकाई"}, options=yes_no(),
        question={"en": "Is the loan for starting a NEW unit (not expanding the existing one)?",
                  "hi": "क्या यह ऋण नई इकाई शुरू करने के लिए है (मौजूदा काम बढ़ाने के लिए नहीं)?"},
        why={"en": "PMEGP and Stand-Up India fund only new (greenfield) units.",
             "hi": "PMEGP और स्टैंड-अप इंडिया केवल नई इकाइयों को वित्त देते हैं।"},
        prior={True: 0.3, False: 0.7}))
_f(Fact("years_in_business", "int", {"en": "Years in business", "hi": "व्यवसाय के वर्ष"}, unit="years",
        question={"en": "For how many years have you run this business?", "hi": "आप यह व्यवसाय कितने वर्षों से चला रहे हैं?"},
        prior={0: 0.2, 3: 0.4, 8: 0.4}))
_f(Fact("ownership_type", "enum", {"en": "Ownership", "hi": "स्वामित्व"},
        options=[Option("individual", {"en": "Just me", "hi": "सिर्फ़ मैं"}),
                 Option("proprietorship", {"en": "Proprietorship", "hi": "प्रोपराइटरशिप"}),
                 Option("partnership", {"en": "Partnership", "hi": "साझेदारी"}),
                 Option("shg", {"en": "Self-help group", "hi": "स्वयं सहायता समूह"}),
                 Option("society", {"en": "Registered society", "hi": "पंजीकृत सोसाइटी"}),
                 Option("cooperative", {"en": "Production co-operative", "hi": "उत्पादन सहकारी समिति"}),
                 Option("trust", {"en": "Charitable trust", "hi": "धर्मार्थ ट्रस्ट"}),
                 Option("company", {"en": "Company", "hi": "कंपनी"})],
        question={"en": "Who owns the business?", "hi": "व्यवसाय का मालिक कौन है?"},
        prior={"proprietorship": 0.7, "partnership": 0.1, "shg": 0.15, "company": 0.05}))
_f(Fact("women_scst_ownership_pct", "int", {"en": "Ownership held by women/SC/ST (%)", "hi": "महिला/SC/ST की हिस्सेदारी (%)"},
        unit="%", question={"en": "What % of the business is owned by women or SC/ST partners?",
                            "hi": "व्यवसाय में महिलाओं या SC/ST साझेदारों की कितनी % हिस्सेदारी है?"},
        prior={0: 0.5, 51: 0.3, 100: 0.2}))
_f(Fact("udyam_registered", "bool", {"en": "Udyam registered", "hi": "उद्यम पंजीकृत"}, source="udyam", options=yes_no(),
        question={"en": "Does your business have an Udyam registration?", "hi": "क्या आपके व्यवसाय का उद्यम पंजीकरण है?"},
        prior={True: 0.35, False: 0.65},
        action=Action("register_udyam", {"en": "Register on Udyam (free, Aadhaar-based)", "hi": "उद्यम पर पंजीकरण करें (निःशुल्क, आधार से)"},
                      True, {"en": "Free · ~15 minutes · Aadhaar + PAN", "hi": "निःशुल्क · ~15 मिनट · आधार + पैन"},
                      "https://udyamregistration.gov.in/")))
_f(Fact("enterprise_class", "enum", {"en": "Enterprise class", "hi": "उद्यम श्रेणी"}, source="derived",
        options=[Option("micro", {"en": "Micro", "hi": "सूक्ष्म"}), Option("small", {"en": "Small", "hi": "लघु"}),
                 Option("medium", {"en": "Medium", "hi": "मध्यम"}), Option("large", {"en": "Above MSME limits", "hi": "MSME सीमा से ऊपर"})],
        prior={"micro": 0.95, "small": 0.05}))
_f(Fact("annual_turnover", "money", {"en": "Annual turnover", "hi": "वार्षिक कारोबार"}, source="aa", unit="INR"))
_f(Fact("plant_investment", "money", {"en": "Investment in machinery/equipment", "hi": "मशीनरी/उपकरण में निवेश"}, unit="INR",
        question={"en": "Roughly what is the value of the machines and equipment your business owns?",
                  "hi": "आपके व्यवसाय की मशीनों और उपकरणों की कुल कीमत लगभग कितनी है?"},
        why={"en": "MSME class (micro/small) depends on BOTH investment and turnover; CGTMSE and delayed-payment rights depend on it.",
             "hi": "MSME श्रेणी (सूक्ष्म/लघु) निवेश और कारोबार दोनों पर निर्भर है; CGTMSE और देरी-भुगतान अधिकार इसी पर निर्भर हैं।"},
        prior={100000: 0.6, 1500000: 0.35, 50000000: 0.05}))
_f(Fact("has_b2b_buyers", "bool", {"en": "Sells to businesses", "hi": "व्यवसायों को बेचते हैं"}, source="aa", options=yes_no(),
        question={"en": "Do companies or traders buy from you on credit?", "hi": "क्या कंपनियाँ या व्यापारी आपसे उधार पर खरीदते हैं?"},
        prior={True: 0.3, False: 0.7}))
_f(Fact("has_overdue_invoices", "bool", {"en": "Business buyers paying late", "hi": "व्यावसायिक खरीदार देर से भुगतान करते हैं"},
        options=yes_no(), prior={True: 0.4, False: 0.6},
        question={"en": "Is any business buyer more than 45 days late in paying an invoice you raised?",
                  "hi": "क्या कोई व्यावसायिक खरीदार आपके बिल का भुगतान 45 दिनों से अधिक देर से कर रहा है?"},
        why={"en": "Only an actually overdue invoice can be taken to the MSE Facilitation Council.",
             "hi": "केवल वास्तव में बकाया बिल को ही MSE सुविधा परिषद में ले जाया जा सकता है।"}))
_f(Fact("has_gst", "bool", {"en": "GST registered", "hi": "जीएसटी पंजीकृत"}, options=yes_no(), prior={True: 0.3, False: 0.7}))
_f(Fact("has_itr", "bool", {"en": "Files income-tax returns", "hi": "आयकर रिटर्न भरते हैं"}, options=yes_no(),
        prior={True: 0.25, False: 0.75},
        question={"en": "Have you filed an income-tax return in the last 2 years?", "hi": "क्या आपने पिछले 2 वर्षों में आयकर रिटर्न भरा है?"}))
_f(Fact("has_collateral", "bool", {"en": "Has property to pledge", "hi": "गिरवी रखने हेतु संपत्ति"}, options=yes_no(),
        prior={True: 0.3, False: 0.7}))

# ---- loan request -----------------------------------------------------------
_f(Fact("loan_amount_sought", "money", {"en": "Loan needed", "hi": "आवश्यक ऋण"}, unit="INR",
        question={"en": "How much money do you need?", "hi": "आपको कितने पैसे चाहिए?"},
        prior={50000: 0.25, 300000: 0.45, 800000: 0.2, 1500000: 0.1}))
_f(Fact("project_cost", "money", {"en": "Total project cost", "hi": "कुल परियोजना लागत"}, unit="INR",
        question={"en": "What is the total cost of what you want to buy or set up?", "hi": "आप जो खरीदना या शुरू करना चाहते हैं उसकी कुल लागत कितनी है?"},
        prior={60000: 0.25, 350000: 0.45, 900000: 0.2, 1800000: 0.1}))
_f(Fact("loan_purpose", "enum", {"en": "Purpose", "hi": "उद्देश्य"},
        options=[Option("machinery", {"en": "Machines / equipment", "hi": "मशीन / उपकरण"}),
                 Option("working_capital", {"en": "Raw material / working capital", "hi": "कच्चा माल / कार्यशील पूंजी"}),
                 Option("livestock", {"en": "Animals / livestock", "hi": "पशु"}),
                 Option("both", {"en": "Machines + working capital", "hi": "मशीन + कार्यशील पूंजी"})]))

# ---- credit history (bureau, simulated) ------------------------------------
_f(Fact("is_defaulter", "bool", {"en": "Current loan default", "hi": "वर्तमान ऋण चूक"}, source="bureau", options=yes_no(),
        prior={True: 0.05, False: 0.95}))
_f(Fact("prior_mudra_tarun_repaid", "bool", {"en": "Repaid a MUDRA Tarun loan", "hi": "मुद्रा तरुण ऋण चुकाया"}, source="bureau",
        options=yes_no(), prior={True: 0.05, False: 0.95},
        question={"en": "Have you earlier taken AND fully repaid a MUDRA Tarun loan (₹5–10 lakh)?",
                  "hi": "क्या आपने पहले मुद्रा तरुण ऋण (₹5–10 लाख) लेकर पूरा चुकाया है?"}))
_f(Fact("availed_pmegp", "bool", {"en": "Availed PMEGP earlier", "hi": "पहले PMEGP लिया"}, source="bureau", options=yes_no(),
        prior={True: 0.04, False: 0.96},
        question={"en": "Have you ever taken a PMEGP loan or subsidy?", "hi": "क्या आपने कभी PMEGP ऋण या सब्सिडी ली है?"}))
_f(Fact("other_govt_selfemp_loan_5y", "bool", {"en": "Other govt self-employment loan in last 5 years",
                                              "hi": "पिछले 5 वर्षों में अन्य सरकारी स्वरोज़गार ऋण"}, options=yes_no(),
        prior={True: 0.1, False: 0.9},
        question={"en": "In the last 5 years, have you taken a loan under any other Central or State government self-employment "
                        "or business scheme (not counting MUDRA or PM SVANidhi loans you have fully repaid)?",
                  "hi": "पिछले 5 वर्षों में क्या आपने किसी अन्य केंद्र या राज्य सरकार की स्वरोज़गार/व्यवसाय योजना में ऋण लिया है "
                        "(पूरी तरह चुकाए गए मुद्रा या पीएम स्वनिधि ऋण को छोड़कर)?"},
        why={"en": "PM Vishwakarma excludes recent borrowers of similar government credit schemes.",
             "hi": "पीएम विश्वकर्मा हाल में समान सरकारी ऋण योजना लेने वालों को शामिल नहीं करती।"}))
_f(Fact("negative_list_declared", "enum", {"en": "Activity and the PMEGP negative list", "hi": "गतिविधि और PMEGP निषेध सूची"},
        options=[Option("no", {"en": "None of these", "hi": "इनमें से कोई नहीं"}),
                 Option("yes", {"en": "Yes, clearly one of these", "hi": "हाँ, साफ़ तौर पर इनमें से एक"}),
                 Option("unsure", {"en": "Partly / not sure", "hi": "आंशिक रूप से / पक्का नहीं"})],
        prior={"no": 0.85, "yes": 0.05, "unsure": 0.10},
        question={"en": "Is your business mainly one of these? (1) slaughtering animals or a meat business (serving non-veg food "
                        "at a hotel or dhaba is allowed); (2) making or selling liquor, toddy, tobacco, pan or beedi, or a hotel or "
                        "dhaba that serves liquor; (3) making polythene carry bags under 75 microns, or recycled-plastic bags or "
                        "containers for food; (4) growing crops, plantations (tea, coffee, rubber), fruit, vegetables or flowers, or "
                        "rearing animals other than dairy, poultry, fish or silkworms (processing and value addition are allowed); "
                        "(5) something your State or local body bans. If it only partly matches or you are unsure, choose that; "
                        "the DIC checks the exact rules.",
                  "hi": "क्या आपका व्यवसाय मुख्यतः इनमें से एक है? (1) पशु-वध या मांस का व्यवसाय (होटल/ढाबे पर मांसाहारी भोजन परोसना "
                        "अनुमत है); (2) शराब, ताड़ी, तंबाकू, पान या बीड़ी बनाना/बेचना, या शराब परोसने वाला होटल/ढाबा; (3) 75 माइक्रॉन से "
                        "पतले पॉलिथीन कैरी बैग, या भोजन के लिए रिसाइकल्ड प्लास्टिक बैग/डिब्बे बनाना; (4) फसल, बागान (चाय, कॉफ़ी, रबर), "
                        "फल, सब्ज़ी या फूल उगाना, या डेयरी, मुर्गी, मछली या रेशम-कीट के अलावा पशुपालन (प्रसंस्करण और मूल्य-वर्धन अनुमत "
                        "हैं); (5) कुछ ऐसा जिसे आपका राज्य/स्थानीय निकाय प्रतिबंधित करता है। आंशिक रूप से मेल खाए या पक्का न हो तो वही "
                        "चुनें; DIC सटीक नियम जाँचता है।"},
        why={"en": "PMEGP does not fund activities on its negative list; the DIC confirms against the current list.",
             "hi": "PMEGP निषेध सूची की गतिविधियों को वित्त नहीं देता; DIC मौजूदा सूची से पुष्टि करता है।"}))
_f(Fact("pmegp_last_5y", "bool", {"en": "PMEGP loan in the last 5 years", "hi": "पिछले 5 वर्षों में PMEGP ऋण"}, options=yes_no(),
        prior={True: 0.5, False: 0.5},
        question={"en": "Was that PMEGP loan taken in the last 5 years?", "hi": "क्या वह PMEGP ऋण पिछले 5 वर्षों में लिया गया था?"}))
_f(Fact("prior_scheme_unit", "enum", {"en": "Unit originally financed under", "hi": "इकाई मूल रूप से किस योजना से बनी"},
        options=[Option("pmegp", {"en": "PMEGP", "hi": "PMEGP"}), Option("regp", {"en": "REGP", "hi": "REGP"}),
                 Option("mudra", {"en": "MUDRA", "hi": "मुद्रा"}), Option("none", {"en": "None of these", "hi": "इनमें से कोई नहीं"})],
        prior={"pmegp": 0.03, "mudra": 0.12, "none": 0.85},
        question={"en": "Was your existing unit set up with a PMEGP, REGP or MUDRA loan?",
                  "hi": "क्या आपकी मौजूदा इकाई PMEGP, REGP या मुद्रा ऋण से शुरू हुई थी?"},
        why={"en": "Existing PMEGP/REGP/MUDRA units can get a second PMEGP loan with subsidy for upgrading.",
             "hi": "मौजूदा PMEGP/REGP/मुद्रा इकाइयों को उन्नयन के लिए सब्सिडी सहित दूसरा PMEGP ऋण मिल सकता है।"}))
_f(Fact("first_loan_repaid_on_time", "bool", {"en": "First loan repaid on time", "hi": "पहला ऋण समय पर चुकाया"}, options=yes_no(),
        prior={True: 0.6, False: 0.4},
        question={"en": "Did you repay that first loan within the agreed time?", "hi": "क्या आपने वह पहला ऋण तय समय में चुकाया?"}))
_f(Fact("first_mm_adjusted", "bool", {"en": "First loan's margin money adjusted after lock-in", "hi": "पहले ऋण की मार्जिन मनी लॉक-इन के बाद समायोजित"},
        options=yes_no(), prior={True: 0.6, False: 0.4},
        question={"en": "Has the margin-money subsidy on your first PMEGP/MUDRA loan already been adjusted into the loan "
                        "(after its 3-year lock-in)? Your bank can tell you.",
                  "hi": "क्या आपके पहले PMEGP/मुद्रा ऋण की मार्जिन मनी सब्सिडी (3 साल के लॉक-इन के बाद) ऋण में समायोजित हो चुकी है? "
                        "आपका बैंक बता सकता है।"},
        why={"en": "A second PMEGP loan is possible only after the first loan's subsidy has been adjusted.",
             "hi": "दूसरा PMEGP ऋण तभी मिलता है जब पहले ऋण की सब्सिडी समायोजित हो चुकी हो।"}))
_f(Fact("profit_last_3y", "bool", {"en": "Profit in each of the last three financial years", "hi": "पिछले तीन वित्त वर्षों में हर साल लाभ"},
        options=yes_no(), prior={True: 0.55, False: 0.45},
        question={"en": "Did the unit make a profit in each of these financial years: {years}? (The COVID years 2020-21 and "
                        "2021-22 are not counted.)",
                  "hi": "क्या इकाई ने इन वित्त वर्षों में हर साल लाभ कमाया: {years}? (कोविड वर्ष 2020-21 और 2021-22 नहीं गिने जाते।)"},
        why={"en": "A second PMEGP loan needs a unit that has made a profit for the last three years; the bank checks your ITRs or accounts.",
             "hi": "दूसरे PMEGP ऋण के लिए इकाई का पिछले तीन वर्षों से लाभ में होना ज़रूरी है; बैंक आपके ITR या खाते देखता है।"}))
_f(Fact("outstanding_mudra_or_svanidhi", "bool", {"en": "Unpaid MUDRA/SVANidhi loan", "hi": "बकाया मुद्रा/स्वनिधि ऋण"},
        source="bureau", options=yes_no(), prior={True: 0.1, False: 0.9},
        question={"en": "Do you currently have an unpaid MUDRA or PM SVANidhi loan?", "hi": "क्या आपका कोई मुद्रा या पीएम स्वनिधि ऋण अभी बकाया है?"}))
_f(Fact("availed_other_govt_subsidy", "bool", {"en": "Got another govt subsidy for this unit", "hi": "इस इकाई के लिए अन्य सरकारी सब्सिडी ली"},
        options=yes_no(), prior={True: 0.08, False: 0.92},
        question={"en": "Has this unit already received a subsidy under any other government scheme?",
                  "hi": "क्या इस इकाई को किसी अन्य सरकारी योजना से पहले ही सब्सिडी मिल चुकी है?"}))
_f(Fact("family_member_availed_pmegp", "bool", {"en": "Family member availed PMEGP", "hi": "परिवार के सदस्य ने PMEGP लिया"},
        options=yes_no(), prior={True: 0.05, False: 0.95},
        question={"en": "Has your spouse already taken PMEGP?", "hi": "क्या आपके पति/पत्नी ने पहले PMEGP लिया है?"}))

# ---- PM Vishwakarma ---------------------------------------------------------
_f(Fact("vishwakarma_trade", "enum", {"en": "Traditional trade", "hi": "पारंपरिक व्यवसाय"},
        options=[Option(t, {"en": VISHWAKARMA_LABELS[t][0], "hi": VISHWAKARMA_LABELS[t][1]}) for t in VISHWAKARMA_TRADES]
        + [Option("none", {"en": "None of these", "hi": "इनमें से कोई नहीं"})],
        question={"en": "Is your work one of the 18 traditional trades (tailor, blacksmith, potter, carpenter...)?",
                  "hi": "क्या आपका काम 18 पारंपरिक व्यवसायों (दर्ज़ी, लोहार, कुम्हार, बढ़ई...) में से है?"},
        prior={"tailor": 0.12, "blacksmith": 0.05, "none": 0.83}))
_f(Fact("is_traditional_family_trade", "bool", {"en": "Family-based traditional trade", "hi": "पारिवारिक पारंपरिक व्यवसाय"},
        options=yes_no(), prior={True: 0.5, False: 0.5},
        question={"en": "Did you learn this craft in your family (guru-shishya tradition)?",
                  "hi": "क्या आपने यह हुनर अपने परिवार में (गुरु-शिष्य परंपरा से) सीखा है?"},
        why={"en": "PM Vishwakarma is for family-based traditional artisans.", "hi": "पीएम विश्वकर्मा पारिवारिक पारंपरिक कारीगरों के लिए है।"}))
_f(Fact("family_member_in_govt_service", "bool", {"en": "Family member in govt service", "hi": "परिवार में सरकारी कर्मचारी"},
        options=yes_no(), prior={True: 0.07, False: 0.93},
        question={"en": "Is anyone in your family (spouse/unmarried children) in government service?",
                  "hi": "क्या आपके परिवार (पति/पत्नी/अविवाहित बच्चे) में कोई सरकारी नौकरी में है?"}))
_f(Fact("family_member_registered_pmv", "bool", {"en": "Family member registered under PM Vishwakarma", "hi": "परिवार का सदस्य पीएम विश्वकर्मा में पंजीकृत"},
        options=yes_no(), prior={True: 0.05, False: 0.95},
        question={"en": "Has anyone else in your family already registered under PM Vishwakarma?",
                  "hi": "क्या आपके परिवार में किसी और ने पीएम विश्वकर्मा में पंजीकरण कराया है?"}))

# ---- PM SVANidhi ------------------------------------------------------------
_f(Fact("is_street_vendor", "bool", {"en": "Street vendor", "hi": "रेहड़ी-पटरी विक्रेता"}, options=yes_no(),
        prior={True: 0.1, False: 0.9},
        question={"en": "Do you sell on the street / from a cart?", "hi": "क्या आप सड़क पर / ठेले से सामान बेचते हैं?"}))
_f(Fact("has_vending_certificate_or_lor", "bool", {"en": "Vending certificate or LoR", "hi": "वेंडिंग प्रमाणपत्र या अनुशंसा पत्र"},
        options=yes_no(), prior={True: 0.5, False: 0.5},
        question={"en": "Do you have a vending certificate/ID or a Letter of Recommendation from the municipality?",
                  "hi": "क्या आपके पास नगर निकाय का वेंडिंग प्रमाणपत्र/पहचान पत्र या अनुशंसा पत्र (LoR) है?"},
        action=Action("apply_lor", {"en": "Apply for LoR on the PM SVANidhi portal", "hi": "पीएम स्वनिधि पोर्टल पर LoR के लिए आवेदन करें"},
                      True, {"en": "Free · online · municipality verifies", "hi": "निःशुल्क · ऑनलाइन · नगर निकाय सत्यापन"},
                      "https://pmsvanidhi.mohua.gov.in/")))
_f(Fact("svanidhi_tranche_repaid", "int", {"en": "PM SVANidhi loans fully repaid", "hi": "पूरी तरह चुकाए गए पीएम स्वनिधि ऋण"}, source="bureau",
        prior={0: 0.7, 1: 0.2, 2: 0.1},
        bounds=(0, 3),
        question={"en": "How many PM SVANidhi loans have you fully repaid so far? (0 if none, at most 3)",
                  "hi": "आपने अब तक कितने पीएम स्वनिधि ऋण पूरी तरह चुकाए हैं? (कोई नहीं तो 0)"},
        why={"en": "Each later tranche needs the previous one repaid.", "hi": "हर अगली किस्त के लिए पिछली चुकाना ज़रूरी है।"}))

# ---- dairy / KCC ------------------------------------------------------------
_f(Fact("owns_milch_animals", "bool", {"en": "Owns/leases milch animals", "hi": "दुधारू पशु हैं"}, options=yes_no(),
        prior={True: 0.15, False: 0.85},
        question={"en": "Do you own or lease cows/buffaloes?", "hi": "क्या आपके पास गाय/भैंस हैं (अपनी या किराए की)?"}))
_f(Fact("milch_animals", "int", {"en": "Number of milch animals", "hi": "दुधारू पशुओं की संख्या"}, prior={3: 0.6, 8: 0.4}))
_f(Fact("has_kcc", "bool", {"en": "Already has a KCC", "hi": "पहले से KCC है"}, source="bureau", options=yes_no(),
        prior={True: 0.3, False: 0.7}))

# ---- SHG --------------------------------------------------------------------
_f(Fact("shg_members", "int", {"en": "SHG members", "hi": "समूह सदस्य"},
        question={"en": "How many members are in your group?", "hi": "आपके समूह में कितने सदस्य हैं?"}, prior={8: 0.2, 12: 0.7, 22: 0.1}))
_f(Fact("shg_age_months", "int", {"en": "SHG age (months)", "hi": "समूह की आयु (महीने)"}, unit="months",
        question={"en": "Since how many months has your group been saving together?", "hi": "आपका समूह कितने महीनों से साथ बचत कर रहा है?"},
        prior={4: 0.2, 18: 0.8}))
_f(Fact("shg_women_only", "bool", {"en": "Women's SHG", "hi": "महिला समूह"}, options=yes_no(), prior={True: 0.9, False: 0.1},
        question={"en": "Are all members of your group women?", "hi": "क्या आपके समूह की सभी सदस्य महिलाएँ हैं?"},
        why={"en": "DAY-NRLM bank linkage and interest subvention are for women's SHGs.", "hi": "DAY-NRLM बैंक लिंकेज और ब्याज अनुदान महिला समूहों के लिए है।"}))
_f(Fact("shg_grading_passed", "bool", {"en": "Passed SHG grading", "hi": "समूह ग्रेडिंग उत्तीर्ण"}, options=yes_no(),
        prior={True: 0.7, False: 0.3},
        question={"en": "Has your group passed the bank/NRLM grading (Panchasutra)?", "hi": "क्या आपका समूह बैंक/NRLM ग्रेडिंग (पंचसूत्र) में पास हुआ है?"}))
# RBI DAY-NRLM master circular (1 Apr 2025) has TWO different exceptions:
#  para 2.2, minimum 5 members for groups in difficult areas, of persons with disabilities, or in remote tribal areas
#  para 2.1, men may be members only in groups of persons with disabilities and other special categories (elders, transgender persons)
_f(Fact("shg_small_special", "bool", {"en": "Group in a difficult/remote tribal area, or of persons with disabilities",
                                      "hi": "कठिन/दूरस्थ आदिवासी क्षेत्र का या दिव्यांगजनों का समूह"}, options=yes_no(),
        prior={True: 0.15, False: 0.85},
        question={"en": "Is your group in a difficult or remote tribal area, or a group of persons with disabilities?",
                  "hi": "क्या आपका समूह कठिन या दूरस्थ आदिवासी क्षेत्र में है, या दिव्यांगजनों का समूह है?"},
        why={"en": "Such groups may have as few as 5 members under DAY-NRLM.", "hi": "DAY-NRLM में ऐसे समूहों में कम से कम 5 सदस्य हो सकते हैं।"}))
_f(Fact("shg_mixed_special", "bool", {"en": "Group of persons with disabilities, elders or transgender persons",
                                      "hi": "दिव्यांगजनों, बुज़ुर्गों या ट्रांसजेंडर व्यक्तियों का समूह"}, options=yes_no(),
        prior={True: 0.05, False: 0.95},
        question={"en": "Is your group made up of persons with disabilities, elders or transgender persons?",
                  "hi": "क्या आपका समूह दिव्यांगजनों, बुज़ुर्गों या ट्रांसजेंडर व्यक्तियों का है?"},
        why={"en": "Only such special groups may include men under DAY-NRLM.", "hi": "DAY-NRLM में केवल ऐसे विशेष समूहों में पुरुष सदस्य हो सकते हैं।"}))


# MSME classification (Ministry of MSME, revised w.e.f. 1 Apr 2025): an enterprise
# is in a class only if BOTH investment and turnover are within that class's limits.
MSME_LIMITS = [("micro", 2_50_00_000, 10_00_00_000), ("small", 25_00_00_000, 100_00_00_000),
               ("medium", 125_00_00_000, 500_00_00_000)]


def classify_msme(investment: float | None, turnover: float | None) -> str | None:
    """Return micro/small/medium/large, or None when either measure is unknown."""
    if investment is None or turnover is None:
        return None
    for cls, inv_max, to_max in MSME_LIMITS:
        if investment <= inv_max and turnover <= to_max:
            return cls
    return "large"


def fact_options(key: str) -> list[dict]:
    f = FACTS[key]
    if f.options:
        return [{"value": o.value, "label": o.label} for o in f.options]
    return []


PMEGP_EXEMPT_FYS = ("2020-21", "2021-22")  # COVID years excluded from the second-loan profit test


def pmegp_profit_years(today: date | None = None) -> list[str]:
    """The three most recent COMPLETED financial years (April-March) for the PMEGP second-loan profit test,
    skipping the exempted COVID years. E.g. in June 2023 -> 2022-23, 2019-20, 2018-19."""
    today = today or date.today()
    end = today.year if today.month >= 4 else today.year - 1  # year in which the last completed FY ended
    out = []
    while len(out) < 3:
        fy = f"{end - 1}-{str(end)[2:]}"
        if fy not in PMEGP_EXEMPT_FYS:
            out.append(fy)
        end -= 1
    return out


def _question(f: "Fact") -> L | None:
    if f.question and "{years}" in f.question["en"]:
        yrs = ", ".join(pmegp_profit_years())
        return {k: v.replace("{years}", yrs) for k, v in f.question.items()}
    return f.question


def fact_public(key: str) -> dict:
    f = FACTS[key]
    return {
        "key": f.key, "type": f.type, "label": f.label, "question": _question(f), "why": f.why,
        "options": fact_options(key), "source": f.source, "sensitive": f.sensitive, "unit": f.unit,
        "action": None if not f.action else {
            "id": f.action.id, "label": f.action.label, "effort": f.action.effort, "url": f.action.url},
    }


def coerce(key: str, value: Any) -> Any:
    """Normalise a user/LLM supplied value to the fact's declared type."""
    if value is None:
        return None
    f = FACTS.get(key)
    if f is None:
        raise KeyError(f"unknown fact {key}")
    if f.type == "bool":
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in {"true", "yes", "y", "1", "haan", "ha", "हाँ", "हां"}:
            return True
        if s in {"false", "no", "n", "0", "nahi", "nahin", "नहीं"}:
            return False
        raise ValueError(f"{key}: not a yes/no value: {value!r}")
    if f.type in {"int", "money"}:
        v = int(round(float(value)))
        if f.type == "money" and v < 0:
            raise ValueError(f"{key}: amount cannot be negative")
        if f.bounds and not f.bounds[0] <= v <= f.bounds[1]:
            raise ValueError(f"{key}: {v} outside {f.bounds[0]}–{f.bounds[1]}")
        return v
    if f.type == "enum":
        allowed = {o.value for o in f.options}
        if value not in allowed:
            raise ValueError(f"{key}: {value!r} not in {sorted(map(str, allowed))}")
        return value
    return value


NEGATIVE_LIST_ACTIVITIES = {"liquor_tobacco"}
# Known not to be on the list: dairy is explicitly relaxed (Rajya Sabha reply, 5 Aug 2024, answer (d)(iii)).
CLEARED_ACTIVITIES = {"tailoring", "fabrication", "leaf_plates", "repair_services", "dairy"}


def derive(facts: dict[str, Any]) -> dict[str, Any]:
    """Facts that are pure functions of other facts."""
    out = dict(facts)
    # MSME class: a verified Udyam class wins; otherwise infer only when BOTH
    # investment and turnover are known (unknown → stays unknown, never assumed).
    if out.get("enterprise_class") is None:
        cls = classify_msme(out.get("plant_investment"), out.get("annual_turnover"))
        if cls:
            out["enterprise_class"] = cls
    if out.get("availed_pmegp") is False and out.get("pmegp_last_5y") is None:
        out["pmegp_last_5y"] = False
    # PMEGP negative list. The entrepreneur's own "yes" always wins over a broad activity label;
    # "not sure" keeps it unknown; only a clear "no" or an activity known not to be listed clears it.
    # Either way it is provisional: the DIC / task force checks the current list (a lender check).
    act, decl = out.get("activity"), out.get("negative_list_declared")
    if act in NEGATIVE_LIST_ACTIVITIES or decl == "yes":
        out["in_negative_list"] = True
    elif decl == "unsure":
        out.pop("in_negative_list", None)
    elif decl == "no" or act in CLEARED_ACTIVITIES:
        out["in_negative_list"] = False
    g, sc = out.get("gender"), out.get("social_category")
    flags = [out.get("is_minority"), out.get("is_ex_serviceman"), out.get("is_pwd"), out.get("is_special_region"),
             out.get("is_aspirational_district")]
    if g == "female" or g == "transgender" or sc in {"sc", "st", "obc"} or any(x is True for x in flags):
        out["pmegp_special_category"] = True
    elif g is not None and sc is not None and all(x is False for x in flags):
        out["pmegp_special_category"] = False
    if out.get("education") is not None:
        out["education_rank"] = EDU_RANK[out["education"]]
    return out


# ---- derived facts (no question; computed by derive()) ----------------------
_f(Fact("in_negative_list", "bool", {"en": "Activity on PMEGP negative list", "hi": "गतिविधि PMEGP निषेध सूची में"}, source="derived"))
_f(Fact("pmegp_special_category", "bool", {"en": "PMEGP special category", "hi": "PMEGP विशेष श्रेणी"}, source="derived"))
_f(Fact("education_rank", "int", {"en": "Education level", "hi": "शिक्षा स्तर"}, source="derived"))

# Which askable facts a derived fact depends on (used to turn "unknown derived
# fact" into concrete questions).
DERIVED_DEPS: dict[str, list[str]] = {
    "in_negative_list": ["activity", "negative_list_declared"],
    "pmegp_special_category": ["gender", "social_category", "is_minority", "is_ex_serviceman", "is_pwd"],
    "education_rank": ["education"],
    "enterprise_class": ["plant_investment", "annual_turnover"],
}

# ---- informal debt (asked only when the statement shows a moneylender pattern)
_f(Fact("informal_outstanding", "money", {"en": "Amount still owed to the moneylender", "hi": "साहूकार को अभी बकाया राशि"},
        unit="INR", question={"en": "We noticed regular payments that look like a private loan. How much do you still owe? (optional, lets us refinance it cheaper)",
                              "hi": "हमें नियमित भुगतान दिखे जो निजी ऋण जैसे लगते हैं। अभी कितना बकाया है? (वैकल्पिक, इससे हम इसे सस्ते ऋण में बदल सकते हैं)"},
        why={"en": "Refinancing a 50%+ moneylender loan with formal credit is often the single biggest saving.",
             "hi": "50%+ ब्याज वाले साहूकार ऋण को औपचारिक ऋण से बदलना अक्सर सबसे बड़ी बचत होती है।"},
        prior={0: 0.5, 50000: 0.5}))
