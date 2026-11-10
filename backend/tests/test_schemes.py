import pytest

from saakh.schemes import engine
from saakh.schemes.benefits import cgtmse_fee_rate, mudra_category, pmegp_rates
from saakh.schemes.questions import rank_questions
from saakh.facts import derive

SUNITA = dict(age=34, gender="female", area_type="rural", sector="manufacturing", activity="tailoring",
              ownership_type="proprietorship", loan_amount_sought=150000, project_cost=165000, is_new_unit=False,
              udyam_registered=False, annual_turnover=550000, is_defaulter=False, vishwakarma_trade="tailor")


def test_kb_loads_and_every_criterion_is_cited():
    kb = engine.load_kb()
    assert len(kb) == 10
    for s in engine.kb_summary():
        assert s["n_criteria"] > 0
        for c in s["criteria"]:
            assert c["cite"]["url"].startswith("https://")
            assert c["cite"]["verification"] in engine.VERIFICATION_LEVELS


def test_uncited_rule_is_rejected_at_load():
    with pytest.raises(engine.KBError, match="without citation"):
        engine._validate({"all": [{"fact": "age", "op": "gte", "value": 18}]}, "x", None, "criteria", set())


def test_unknown_fact_is_rejected():
    with pytest.raises(engine.KBError, match="unknown fact"):
        engine._validate({"fact": "shoe_size", "op": "eq", "value": 1, "cite": {"source": "pmv_portal"}}, "x", None, "c", set())


def test_three_valued_logic_never_turns_unknown_into_rejection():
    r = engine.evaluate_scheme("pm_vishwakarma", {"age": 30, "vishwakarma_trade": "tailor"})
    assert r["eligibility"] == "needs_info"
    assert "is_traditional_family_trade" in r["missing_facts"]
    assert r["failing"] == []


def test_failure_carries_citation():
    r = engine.evaluate_scheme("pmegp", SUNITA)
    assert r["eligibility"] == "not_eligible"
    assert any(f["id"] == "pmegp.new" and f["cite"]["source"] == "kvic_pmegp" for f in r["failing"])


def test_standup_india_is_not_offered_as_available():
    r = engine.evaluate_scheme("standup_india", {**SUNITA, "loan_amount_sought": 1500000, "is_new_unit": True})
    assert r["eligibility"] == "lapsed" and r["availability"] == "unavailable" and r["benefits"] == []
    assert {"sui_pib_extension", "sui_guidelines"} <= {c["source"] for c in r["status_cites"]}
    assert all(s["cites"] for s in engine.explain(r))


def test_derived_special_category_and_education():
    d = derive({"gender": "female", "education": "10th"})
    assert d["pmegp_special_category"] is True and d["education_rank"] == 3
    d2 = derive({"gender": "male", "social_category": "general", "is_minority": False, "is_ex_serviceman": False,
                 "is_pwd": False, "is_special_region": False, "is_aspirational_district": False})
    assert d2["pmegp_special_category"] is False


def test_benefit_math():
    assert pmegp_rates({"pmegp_special_category": True, "area_type": "rural"}) == (0.35, 0.05)
    assert pmegp_rates({"pmegp_special_category": False, "area_type": "urban"}) == (0.15, 0.10)
    assert mudra_category(50000)[0] == "Shishu" and mudra_category(800000)[0] == "Tarun" and mudra_category(1500000)[0] == "Tarun Plus"
    assert cgtmse_fee_rate(800000, False) == 0.37 and cgtmse_fee_rate(800000, True) == pytest.approx(0.333)
    assert cgtmse_fee_rate(3_00_00_000, False) == 1.00


def test_udyam_meets_a_condition_but_cgtmse_stays_a_lender_decision():
    f = {**SUNITA, "plant_investment": 85000}
    u = engine.unlock_actions(f)
    reg = next(x for x in u if x["action"] == "register_udyam")
    assert "cgtmse" in [x["id"] for x in reg["unlocks"]]
    r = engine.evaluate_scheme("cgtmse", {**f, "udyam_registered": True})
    assert r["eligibility"] == "eligible" and r["kind"] == "guarantee"
    assert len(r["lender_checks"]) >= 2 and all(lc["cite"] for lc in r["lender_checks"])
    assert all(b["kind"] in ("conditional", "fee") for b in r["benefits"])
    assert "lender" in engine.explain(r)[0]["text"]
    # without the investment figure the class is unknown, so no unlock is claimed
    assert not any(x["action"] == "register_udyam" for x in engine.unlock_actions(SUNITA))


def test_msme_class_needs_investment_and_turnover():
    from saakh.facts import classify_msme
    assert classify_msme(None, 5_00_000) is None and classify_msme(5_00_000, None) is None
    assert classify_msme(2_50_00_000, 10_00_00_000) == "micro"
    assert classify_msme(2_50_00_001, 1_00_000) == "small"
    assert classify_msme(1_00_000, 10_00_00_001) == "small"
    assert classify_msme(30_00_00_000, 50_00_00_000) == "medium"
    assert classify_msme(200_00_00_000, 10_00_00_000) == "large"
    assert derive({"annual_turnover": 5_00_000}).get("enterprise_class") is None


def test_pmegp_second_loan_pathway_for_existing_units():
    base = {**SUNITA, "udyam_registered": True, "project_cost": 3_00_000}
    assert engine.evaluate_scheme("pmegp", base)["eligibility"] == "not_eligible"
    ok = {**base, "prior_scheme_unit": "mudra", "first_loan_repaid_on_time": True, "first_mm_adjusted": True,
          "profit_last_3y": True}
    r = engine.evaluate_scheme("pmegp_upgrade", ok)
    assert r["eligibility"] == "eligible" and any("15%" in (b["display"] or "") for b in r["benefits"])
    assert sorted(p["id"] for p in r["provisional"]) == ["pmegpu.mm_adjusted", "pmegpu.profit"]  # bank verifies both
    assert any("potential for further growth" in lc["text"]["en"] for lc in r["lender_checks"])
    assert any(c["source"] == "pmegp_portal" and c["verification"] == "verified" for c in r["citations"])
    loss = engine.evaluate_scheme("pmegp_upgrade", {**ok, "profit_last_3y": False})
    assert loss["eligibility"] == "not_eligible" and any("COVID" in cv["text"]["en"] for cv in loss["caveats"])
    assert engine.evaluate_scheme("pmegp_upgrade", {k: v for k, v in ok.items() if k != "profit_last_3y"})["eligibility"] == "needs_info"

    assert engine.evaluate_scheme("pmegp_upgrade", {**ok, "first_loan_repaid_on_time": False})["eligibility"] == "not_eligible"
    assert engine.evaluate_scheme("pmegp_upgrade", {**ok, "first_mm_adjusted": False})["eligibility"] == "not_eligible"
    assert engine.evaluate_scheme("pmegp_upgrade", {k: v for k, v in ok.items() if k != "first_mm_adjusted"})["eligibility"] == "needs_info"
    assert engine.evaluate_scheme("pmegp_upgrade", {**ok, "project_cost": 2_00_00_000})["eligibility"] == "not_eligible"
    trust = {**SUNITA, "is_new_unit": True, "ownership_type": "trust", "project_cost": 3_00_000,
             "availed_other_govt_subsidy": False, "availed_pmegp": False, "family_member_availed_pmegp": False}
    assert engine.evaluate_scheme("pmegp", trust)["failing"] == []

def test_pmegp_second_loan_profit_years_skip_the_covid_years():
    from datetime import date
    from saakh.facts import fact_public, pmegp_profit_years
    assert pmegp_profit_years(date(2026, 11, 10)) == ["2025-26", "2024-25", "2023-24"]
    assert pmegp_profit_years(date(2026, 3, 31)) == ["2024-25", "2023-24", "2022-23"]  # FY 2025-26 not yet complete
    assert pmegp_profit_years(date(2024, 5, 1)) == ["2023-24", "2022-23", "2019-20"]
    assert pmegp_profit_years(date(2023, 6, 1)) == ["2022-23", "2019-20", "2018-19"]
    assert pmegp_profit_years(date(2022, 4, 1)) == ["2019-20", "2018-19", "2017-18"]
    q = fact_public("profit_last_3y")["question"]
    assert "{years}" not in q["en"] and ", ".join(pmegp_profit_years()) in q["en"] and "{years}" not in q["hi"]


def test_nrlm_special_groups_and_current_rates():
    shg = {"ownership_type": "shg", "shg_women_only": True, "shg_age_months": 12, "shg_grading_passed": True, "area_type": "rural"}
    cases = ((5, True, "eligible"), (9, True, "eligible"), (9, False, "not_eligible"), (10, False, "eligible"),
             (20, False, "eligible"), (4, True, "not_eligible"))
    for n, special, want in cases:
        got = engine.evaluate_scheme("day_nrlm", {**shg, "shg_members": n, "shg_small_special": special})["eligibility"]
        assert got == want, (n, special)
    # Para 2.1: men only in groups of persons with disabilities / elders / transgender persons, not "remote area" groups
    mixed = {**shg, "shg_members": 12, "shg_women_only": False}
    assert engine.evaluate_scheme("day_nrlm", {**mixed, "shg_mixed_special": True})["eligibility"] == "eligible"
    assert engine.evaluate_scheme("day_nrlm", {**mixed, "shg_mixed_special": False})["eligibility"] == "not_eligible"
    assert engine.evaluate_scheme("day_nrlm", {**mixed, "shg_small_special": True, "shg_mixed_special": False})["eligibility"] == "not_eligible"
    r = engine.evaluate_scheme("day_nrlm", {**shg, "shg_members": 12, "shg_small_special": False})
    txt = " ".join((b["display"] or "") + b["label"]["en"] for b in r["benefits"])
    assert "4%" not in txt and "7% p.a. up to ₹3 lakh" in txt and "FY 2025-26" in txt


def test_msmed_excludes_traders_and_needs_an_overdue_invoice_to_claim():
    f = {"enterprise_class": "micro", "udyam_registered": True, "has_b2b_buyers": True}
    assert engine.evaluate_scheme("msmed_delayed_payment", {**f, "sector": "trading"})["eligibility"] == "not_eligible"
    r = engine.evaluate_scheme("msmed_delayed_payment", {**f, "sector": "manufacturing"})
    assert r["eligibility"] == "eligible"
    assert any("No overdue invoice" in b["label"]["en"] for b in r["benefits"])
    r2 = engine.evaluate_scheme("msmed_delayed_payment", {**f, "sector": "manufacturing", "has_overdue_invoices": True})
    assert any("file with the Facilitation Council" in b["label"]["en"] for b in r2["benefits"])


def test_vishwakarma_uses_5_year_lookback_and_flags_conflicting_faq():
    f = {**SUNITA, "is_traditional_family_trade": True, "outstanding_mudra_or_svanidhi": False,
         "family_member_registered_pmv": False, "family_member_in_govt_service": False, "other_govt_selfemp_loan_5y": False}
    assert engine.evaluate_scheme("pm_vishwakarma", {**f, "availed_pmegp": False})["eligibility"] == "eligible"
    old = engine.evaluate_scheme("pm_vishwakarma", {**f, "availed_pmegp": True, "pmegp_last_5y": False})
    assert old["eligibility"] == "eligible" and old["caveats"] and old["caveats"][0]["cite"]["loc"] == "FAQ 24"
    recent = engine.evaluate_scheme("pm_vishwakarma", {**f, "availed_pmegp": True, "pmegp_last_5y": True})
    assert recent["eligibility"] == "not_eligible"


def test_every_explanation_sentence_is_cited():
    for r in engine.evaluate_all({**SUNITA, "plant_investment": 85000, "is_traditional_family_trade": True}):
        for sent in engine.explain(r):
            assert sent["cites"], (r["id"], sent["text"])


def test_tarun_plus_requires_prior_repayment():
    f = {**SUNITA, "loan_amount_sought": 1500000}
    assert engine.evaluate_scheme("pmmy", {**f, "prior_mudra_tarun_repaid": False})["eligibility"] == "not_eligible"
    assert engine.evaluate_scheme("pmmy", {**f, "prior_mudra_tarun_repaid": True})["eligibility"] == "eligible"


def test_voi_asks_decisive_question_first_and_discounts_sensitive():
    r = rank_questions({"sector": "manufacturing"})
    top = [q["fact"] for q in r[:3]]
    assert "loan_amount_sought" in top or "is_new_unit" in top
    assert r[0]["voi"] > 0
    sens = [q for q in r if q["fact"] == "social_category"]
    if sens:
        assert sens[0]["voi"] < r[0]["voi"]


def test_vishwakarma_excludes_other_govt_credit_scheme_loans_in_5_years():
    f = {**SUNITA, "is_traditional_family_trade": True, "outstanding_mudra_or_svanidhi": False, "availed_pmegp": False,
         "family_member_registered_pmv": False, "family_member_in_govt_service": False}
    unknown = engine.evaluate_scheme("pm_vishwakarma", f)
    assert unknown["eligibility"] == "needs_info" and "other_govt_selfemp_loan_5y" in unknown["missing_facts"]
    took = engine.evaluate_scheme("pm_vishwakarma", {**f, "other_govt_selfemp_loan_5y": True})
    assert took["eligibility"] == "not_eligible"
    assert any(c["id"] == "pmv.no_other_govt_loan" for c in took["failing"])


def test_pmegp_negative_list_unknown_activity_is_never_assumed_clear():
    base = {**SUNITA, "is_new_unit": True, "project_cost": 3_00_000, "availed_other_govt_subsidy": False,
            "availed_pmegp": False, "family_member_availed_pmegp": False}
    assert derive({"activity": "tailoring"})["in_negative_list"] is False  # known not to be listed
    assert derive({"activity": "liquor_tobacco"})["in_negative_list"] is True
    assert "in_negative_list" not in derive({"activity": "other"})  # unknown until declared
    r = engine.evaluate_scheme("pmegp", {**base, "activity": "other", "sector": "trading"})
    assert r["eligibility"] != "eligible"
    assert engine.evaluate_scheme("pmegp", {**base, "activity": "liquor_tobacco"})["eligibility"] == "not_eligible"
    assert derive({"activity": "other", "negative_list_declared": "no"})["in_negative_list"] is False
    assert any(c["source"] == "kvic_pmegp_2023" for c in engine.evaluate_scheme("pmegp", base)["citations"])


def test_svanidhi_unknown_history_is_not_first_tranche_and_cgtmse_shows_no_invented_cover():
    from saakh.schemes.benefits import benefits
    unknown = " ".join(b["label"]["en"] for b in benefits("pm_svanidhi", {"is_street_vendor": True}))
    assert "not yet known" in unknown and "Your next loan tranche" not in unknown
    known = benefits("pm_svanidhi", {"is_street_vendor": True, "svanidhi_tranche_repaid": 1})
    assert any(b["amount"] == 25_000 for b in known)
    cg = benefits("cgtmse", {"loan_amount_sought": 5_00_000, "gender": "female"})
    cover = next(b for b in cg if "covered" in b["label"]["en"])
    assert cover["display"] is None and "%" not in cover["label"]["en"] and "lender determines" in cover["label"]["en"]
