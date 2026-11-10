# Business model, market, scale and jobs

## Who feels the pain, and who pays

| Party | Pain today | What Saakh changes | Pays? |
|---|---|---|---|
| Entrepreneur | Misses schemes; 15–20 papers; months of follow-up; 10–15% agent cut; 24–36% moneylender credit *(organisers' estimates, to verify in the field)* | Cited eligibility in minutes; ~1–2 actions instead of ~17 papers; loan sized to the seasons; moneylender refinanced | **No.** Free, which removes the agent cut |
| Bank / NBFC branch | Incomplete files cost officer time (rework, visits, follow-up); thin-file borrowers are hard to assess | Complete, consented, pre-appraised file with a cash-flow assessment, reason codes, cited scheme mapping and integrity proofs | **Yes.** Per complete file + success fee on disbursal |
| DIC / scheme agencies | Targets under PMEGP, PMV etc.; eligible applicants drop out | Cohort screening; fewer dropouts; complete DPRs | Yes. Programme / outreach budgets |
| SHG federations, BCs, JanAI Cafés | Manual screening of members | Bulk screening + assisted journeys | Earn an assisted-service fee from lenders |

## Unit economics (assumptions, editable in the app's *Cost of incomplete files* calculator)

Defaults: 60 MSME files per branch per month · 45% incomplete today · 2.2 rework cycles × 1.6 officer-hours each · +25% for visits and follow-up · ₹750 loaded cost per officer-hour · 5% incomplete with Saakh.

That works out to **≈ 105 officer-hours and ≈ ₹79,000 of rework avoided per branch per month**, about ₹1,300 per file. A **₹150–400 per complete file** fee therefore saves the lender money from the first file, before counting the value of new good borrowers. The 76.3% vs 6.1% reach on the synthetic test illustrates the mechanism; real effect sizes need lender data. All inputs are hypotheses to measure in field research (see FIELD_RESEARCH.md).

## Market and scale

- Target: micro enterprises with steady digital flows but no ITR or audited statements: tailors, fabricators, dairy units, SHG enterprises, vendors. India has tens of millions of micro enterprises (Udyam alone now registers crores). The software costs almost nothing per file, so growth is bounded by distribution, not by cost.
- Distribution: (1) lender partnerships (a branch pilot, then regional rollout); (2) SHG federations and DICs via cohort screening; (3) JanAI Cafés and CSCs for assisted journeys.
- Scale-out: rules are data (adding a scheme or a state scheme means YAML plus citations); the AA, ULI and DigiLocker rails are national; the scorecard refits per lender.

## Jobs

- **Direct:** JanAI Café / BC operators paid per assisted journey; field verification for physical steps.
- **Indirect, the real lever:** each funded micro enterprise adds capacity (a second tailor, a worker at the fabricator, more milk sold to the cooperative). PMEGP's own reporting attributes lakhs of jobs to subsidised micro units. Saakh's contribution is converting eligible-but-unreached units into funded ones.

## Moat

The cited rule base with verification tracking; the consent and approval architecture lenders can audit; lender-specific calibrated scorecards with fairness gates; distribution through federations and cafés.
