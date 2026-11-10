# Five-minute demo script

**Setup:** `.\run.ps1` → http://127.0.0.1:8000. Hindi is the default; the toggle is top right.

**0:00 · The problem in one line.** "Sunita stitches for about 60 paying customers a month, mostly by UPI. She has no ITR and pays a moneylender ₹1,200 every Monday. The bank can't see her; the schemes can't find her."

**0:20 · Entrepreneur tab → Sunita.** Tap the example sentence (or speak it). The agent restates the plan and shows the consent screen: four separate, purpose-bound permissions, each marked SIMULATED. Grant them.

**0:50 · Recovery.** The trace shows the Account Aggregator timing out, the retry, and the recovery. Point out that every tool call carries `guard ✓ consent:…`.

**1:10 · What the bank statement says.** ₹71k per month average, the seasonal peaks, and the **likely moneylender**: 52 weekly payments, ≈57% a year once she tells us she owes ₹50,000.

**1:30 · Schemes with proof.** Open PM Vishwakarma and click a citation chip: official page, locator, *verified on 2026-11-09*. Open CGTMSE: the borrower conditions are met, and "Still decided by the lender" lists membership and appraisal. Stand-Up India shows *not available now*, with its sources.

**1:50 · Unlock.** "One free Udyam registration meets a condition for CGTMSE." Tap *Yes, do it* (simulated). It is classified from declared investment and turnover, and the agent says cover is the lender's call.

**2:05 · Smart questions.** Seven questions, no form. Each says which schemes it decides; caste is optional and never used in scoring.

**2:30 · Offers.** PM Vishwakarma ₹1 lakh at 5% plus a ₹15,000 toolkit, or MUDRA ₹2 lakh including the moneylender payoff. Toggle *Season-matched* vs *Same every month* and compare tight months. Show the APR.

**3:00 · Documents → Approve.** "17 papers → 9 items; you do two: a selfie, and the biometric step at a café." Route the CSC biometric step to a JanAI Café. On the approval card, show the file hash and what is shared with whom, then approve.

**3:30 · Branch tab** (pick Sunita's branch from the demo sign-in list; each branch has its own key and sees only its own files). Sunita's file: cash flow, scorecard points and reason codes, cited eligibility, integrity (hash ✓, approval bound ✓, audit chain ✓). Download the credit memo PDF. Open **Mohan** (band E) to show the honest "not now" and that he applied anyway (his right).

**4:10 · Governance tab.** On the synthetic population: creditworthy reach 76% vs 6% for the document checklist, and a women/men approval ratio of 0.985 vs 0.19. Then show the honest part: the ST vs General gate **failed** on the test split, an automatic re-check on a fresh draw put it within limits, and the model is still marked **BLOCKED**, because the rule fails closed.

**4:40 · Close.** In the Consents tab, revoke "share with lender": the application is withdrawn and the branch console now returns *consent not active*. (Revoking the bank-statement consent before submission deletes every derived figure.) "Consent, citation, calibration and approval are enforced in code."

**Backup:** *Demo fast-forward* runs the persona through the same checkpoints in about a second and **stops before approval**. You approve on screen. Its steps are audited as `demo-autopilot`.
