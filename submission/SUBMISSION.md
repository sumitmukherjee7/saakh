# Tech4Bharat 2026 submission: paste-ready text

**Team:** Soliloquy · Sumit Mukherjee (Team Lead), Dual Degree, IIT Kharagpur
**Problem statement:** 3.2 Formal Credit and Schemes (Theme 3: MSME Finance & Compliance) · Track: Agentic AI

---

## Project title

**Saakh (साख): an AI agent that turns a small business's UPI trail into bank-ready credit**

Shorter alternative if the field is limited:
**Saakh: from UPI trail to bank-ready credit**

---

## Brief idea description

*(about 110 words)*

India's micro enterprises earn trust every day in UPI payments, yet banks ask for ITRs and audited accounts they do not have, so eligible owners end up borrowing from moneylenders at 24 to 36%. Saakh is a Hindi-first, voice-first AI agent that works for the entrepreneur. With purpose-bound consent, it reads the bank statement, spots moneylender repayments, matches government schemes with a cited source for every rule, sizes a loan that fits the business's lean months, and assembles a lender-ready file with a project report. Nothing is sent until the entrepreneur approves that exact file, and the bank receives a pre-appraised, consented file it can trust. A JanAI Café assisted mode serves owners who are not online.

---

## Detailed explanation

*(about 1,000 words; a 250-word version follows)*

### 1. The problem, seen from the owner's side

Sunita stitches for about 60 customers a month, mostly paid by UPI. She has no ITR, so the bank cannot see her. She qualifies for PM Vishwakarma and MUDRA, but nobody has told her. She repays a moneylender ₹1,200 every Monday on a ₹50,000 loan, about 57% a year. Her story is the problem in Theme 3.2: viable businesses with real, digital cash flows are locked out of formal credit and the schemes built for them. The barrier is not creditworthiness; it is paperwork, scheme complexity, months of branch visits, and agents who take 10 to 15%. SIDBI and Crisil estimate India's addressable MSME credit gap at about ₹30 lakh crore, and over 7.9 crore enterprises are now on the Udyam platforms, about 99% of them micro.

### 2. What Saakh does, in about two minutes per owner

1. **Talk.** The owner says what they need in Hindi, Hinglish or English, by voice or text: "मुझे दो सिलाई मशीनें चाहिए, डेढ़ लाख".
2. **Consent.** Saakh asks for four separate, purpose-bound consents (DigiLocker, bank statement through the Account Aggregator, credit bureau, Udyam), modelled on the ReBIT artefact. Each can be declined; the agent then asks instead.
3. **Understand the business.** It categorises up to 12 months of transactions and detects moneylender repayments, EMI bounces, seasonality and B2B buyers. For Sunita it finds 52 weekly payments of ₹1,200; once she confirms she owes ₹50,000, that works out to about 57% a year.
4. **Match schemes, with proof.** A three-valued rule engine checks 10 scheme pathways (MUDRA, PMEGP and its second loan, PM Vishwakarma, CGTMSE, PM SVANidhi, KCC for animal husbandry, DAY-NRLM, the MSMED 45-day payment right, and Stand-Up India, correctly shown as not currently available). Every criterion cites its official source and verification level. Results separate what the scheme requires, what the lender still decides, and what an agency must verify (shown as provisional).
5. **Ask only what matters.** Questions are ranked by value of information, so the owner answers about seven questions instead of filling a form. Sensitive questions are optional and never used for scoring.
6. **Unlock.** If a free action changes the outcome, such as a Udyam registration, Saakh offers to do it, and says plainly what it does and does not guarantee.
7. **Offer a loan that fits.** Saakh sizes the loan from disposable cash flow and builds a season-matched repayment schedule with a Key Facts Statement-style APR. For a dairy unit, a flat EMI leaves 12 of 36 months tight; the season-matched schedule leaves none.
8. **Build the file.** A minimum-effort set cover turns the usual 17 papers into 9 items, most fetched or generated (pre-filled form, cash-flow analysis, project report PDF). Uploads are checked and fingerprinted; physical steps can be routed to a JanAI Café.
9. **Approve, submit, track.** The owner sees exactly what is shared, with whom, at what APR, and what is still pending. Approval is bound to a SHA-256 fingerprint of the exact file, including every attachment; any change voids it. The branch receives a credit memo, reason codes, cited eligibility and integrity proofs. Revoking consent withdraws the file and erases its contents from the bank's copy.

### 3. Why it is a real agent, not a chatbot

Saakh is a goal-driven planner that works with persistent case memory. It re-plans after every event, so it resumes correctly after a dropped network, a declined consent, a new fact or a lender query. It calls tools (e-KYC, statement fetch, bureau, Udyam, scheme engine, sizing, document planner, report generator, submission). Every tool call passes a code-level guard that checks consent and approval before it runs. It recovers from failures on its own: the bank-data fetch times out by design, and the agent retries with backoff or falls back to a statement upload. It stops for a human at every consent, every outward action, the choice of offer and the final approval, and assisted-mode approvals need a one-time code from the owner's phone. Decisions about eligibility, risk and amounts come from auditable engines, never from free-form text generation.

### 4. Built to be trusted

- **Consent and privacy:** purpose-bound artefacts with expiry; revocation and expiry delete derived data; an append-only, hash-chained audit log that stores no personal or financial values.
- **Cited, fail-closed rules:** the knowledge base refuses any rule without a citation; unknown facts never become "eligible".
- **Fair and honest risk:** a monotone, explainable scorecard with calibration and seven fairness gates. It reaches 76% of creditworthy synthetic borrowers versus 6% for a traditional document checklist, at a lower default rate. One fairness gate fails on the test split, so the model is marked blocked and production mode refuses score-based offers. We publish that rather than hide it.
- **Lender safety:** each branch sees only its own files; decisions are versioned and idempotent; the bank's own reasons are required for a decline.
- **Engineering quality:** 126 automated tests, and six rounds of independent code review with every finding and verdict published in the repository.

### 5. The working prototype

A FastAPI backend and a React progressive web app with six synthetic personas, voice input, read-aloud, an offline queue, the JanAI Café assisted mode, a branch console with credit memo and project report PDFs, a governance view of the model and rules, and SHG federation screening of 40 members in seconds. Integrations that have no open API (Account Aggregator, DigiLocker, bureau, Udyam, lender LOS) are simulated adapters with production-shaped interfaces, and every one is labelled SIMULATED, as the rules allow.

### 6. Business model, scale and jobs

The entrepreneur pays nothing, which removes the agent's cut. Lenders pay per complete file and a success fee on disbursal, because incomplete files cost them officer time: under our editable assumptions, about 105 officer-hours and ₹79,000 per branch per month. DICs and scheme agencies use cohort screening to reach their targets; SHG federations and JanAI Cafés earn an assisted-service fee. Software cost per file is near zero, so growth is bounded by distribution: a branch pilot, then regional rollout, plus federations and cafés. Adding a scheme is a YAML file with citations. Jobs come directly through café and business-correspondent operators, and indirectly through every funded micro enterprise that hires.

### 7. Validation plan

We have not yet done field interviews. Our plan turns the organisers' six research questions into testable hypotheses, each linked to a product decision and measured by the product itself. It covers 15 to 20 owners across personas and 3 to 5 branch managers, logging the time and rework each file costs, to replace our assumptions with measured numbers.

---

## Detailed explanation: short version (about 250 words)

Viable micro enterprises with steady UPI income cannot reach formal credit or the schemes meant for them, because banks ask for ITRs and audited accounts. They end up paying moneylenders 24 to 36%. Saakh is a Hindi-first, voice-first AI agent that fixes this for the owner. With purpose-bound consent, it reads the bank statement through the Account Aggregator, detects moneylender repayments, seasonality and bounces, and matches 10 government scheme pathways with a cited official source for every rule. It asks only the questions that change an outcome, sizes a loan the business can repay in its lean months with a season-matched schedule, and turns 17 typical papers into 9 items, generating the project report itself. Nothing leaves the phone until the owner approves a fingerprint-bound copy of the exact file; revoking consent withdraws it. The bank receives a pre-appraised, consented file with a credit memo and reason codes.

It is a true agent: a goal-driven planner with persistent memory, guarded tool calls, automatic retries and fallbacks, and human checkpoints for every consent and approval. Eligibility, risk and amounts come from auditable engines, not generated text. The explainable scorecard has fairness gates that fail closed, and we publish that one currently fails. A JanAI Café mode uses one-time codes from the owner's phone. Lenders pay per complete file; owners pay nothing. The prototype runs end to end with 126 automated tests; government and bank integrations are clearly labelled simulations.

---

## Additional supporting links

**GitHub repository:** https://github.com/sumitmukherjee7/saakh

**Research references (official sources the rule base cites):**
- RBI Master Circular on DAY-NRLM (RBI/2025-26/02): https://www.rbi.org.in/Scripts/BS_ViewMasCirculardetails.aspx?id=12806
- PMEGP portal, Ministry of MSME: https://common-pmegp.msme.gov.in/Home/HomePage
- PM Vishwakarma, eligibility and FAQ: https://pmvishwakarma.gov.in/
- CGTMSE eligible borrowers and facilities: https://www.cgtmse.in/Home/VS/95
- PM SVANidhi: https://pmsvanidhi.mohua.gov.in/
- Udyam MSME classification: https://udyamregistration.gov.in/Important.aspx
- ReBIT Account Aggregator specifications (consent artefact model): https://api.rebit.org.in/
- RBI Digital Lending Directions, 2025: https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12848

**Market sizing:**
- SIDBI with Crisil, "Understanding Indian MSME Sector: Progress and Challenges" (May 2025), MSME credit gap about ₹30 lakh crore: https://www.sidbi.in/annualreport/AnnualReport202425/msme-outlook.php
- PIB backgrounder (May 2026), over 7.9 crore enterprises on Udyam platforms: https://static.pib.gov.in/WriteReadData/specificdocs/documents/2026/may/doc2026514869801.pdf

If the form takes a single link field, use the GitHub repository: its README links the architecture, model card, business model, field research plan and the full list of cited sources.
