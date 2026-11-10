# Design decisions

**D-01 · An agent around deterministic engines, not an LLM deciding things.**
The brief requires cited eligibility, calibrated and fair risk, consent, and human approval. An LLM that decides eligibility can't guarantee any of those. So the decisions live in auditable engines (rules, scorecard, set cover, sizing), and the agent's job is orchestration: what to do next, retries, fallbacks, checkpoints. Language handling (Hindi/Hinglish parsing, explanations) is deterministic too: every parsed value is validated against the fact registry, and every explanation sentence comes from the cited proof tree.
*Rejected:* a RAG chatbot over scheme PDFs. It hallucinates thresholds, can't prove a negative, and can't be tested.

**D-02 · Rules as cited YAML with three-valued logic.**
Kleene logic means a missing fact yields "needs info" plus the exact facts that would settle it, never a silent rejection. The loader refuses uncited criteria. Each source carries `verification` (verified / official_unverified / secondary) and a `checked` date. That status is shown to users and lenders, and secondary sources trigger "confirm at the branch".
*Why it matters:* official sites conflict and change. Stand-Up India's portal still lists the scheme, while news reports say the Finance Minister told the Lok Sabha it ended in March 2025. Saakh shows both sources rather than picking one silently.

**D-03 · Value-of-information questioning.**
Dropout midway is one of the organisers' six field questions. Instead of a 40-field form, the agent asks one question at a time: the one with the highest expected rupee value of scheme decisions it settles. Sensitive attributes carry a cost factor (data minimisation). In practice an entrepreneur answers 3–7 questions.

**D-04 · Monotone WoE scorecard over a black box.**
Branch managers, auditors and borrowers all need the same explanation, and RBI expects explainability. A points table gives exact reason codes and counterfactual advice ("move buffer days to the next bin: +X points"). A from-scratch GBM challenger measures what interpretability costs. Here the cost was zero: the GBM's AUC was 0.733 vs. 0.737.

**D-05 · Fairness enforced at training time, with an explicit proxy gate.**
Protected attributes are never inputs; they are used only to audit. Candidate features (business size, digital share) must clear an accuracy-gain gate *and* must not worsen the opportunity gap. Weak features that predict gender or rural location (AUC > 0.6, IV < 0.05) are removed. Every decision is logged in `model_report.json` and shown on the Governance page.

**D-06 · Synthetic population with a stated causal story.**
No public data links Indian micro-enterprise statements to repayment outcomes and protected attributes. The simulator makes true risk group-neutral but measurement group-dependent (smaller, more cash-based businesses; fewer ITRs and collateral titles in women's names). That lets us show how a document checklist inherits bias while a calibrated cash-flow model doesn't. It also lets us evaluate both policies on everyone, with no reject-inference problem. Swapping in lender data changes only `risk/synth.py`.

**D-07 · De-seasonalise with a sector index.**
With 12 months of data, trend and seasonality can't be separated. Without a sector prior, a tailor whose peak is November looks like a business in decline. We divide by a sector seasonal index (in production, re-estimated from pooled consented data).

**D-08 · Season-matched repayment.**
The schedule has the same present value as a flat EMI, but each instalment is proportional to that calendar month's expected spare income (floored). Stress months (instalment > 60% of spare income) fall sharply: dairy 12 → 0, SHG 18 → 9, fabricator 3 → 0. RBI permits repayment structures aligned to cash flows; the KFS shows the APR for both options.

**D-09 · Size from affordability and risk, not from the ask.**
The recommended amount is the minimum of: the request, the scheme cap, seasonal affordability (with only 50% of the projected uplift from the financed asset), and the largest amount whose PD stays inside policy. The binding constraint is explained to the user. When nothing fits, the answer is an honest "not now" with a concrete path, and the entrepreneur can still apply.

**D-10 · Approval bound to a content hash.**
"Approve" is meaningless if the file can change afterwards. The approval token is the SHA-256 of the package; the submit guard compares hashes, and any edit voids the approval (tested).

**D-11 · Raw AA transactions are never persisted; uploaded statements are, briefly.**
AA data is re-fetched under consent when needed and only aggregates persist, so revoking consent removes everything derived. A CSV statement the entrepreneur uploads cannot be re-fetched, so its rows are stored for as long as its own consent is active and deleted on revocation or expiry. (The first version of this README said "never persisted" for both; the second review caught it.)

**D-12 · Numpy/scipy ML instead of scikit-learn.**
Smart App Control blocked sklearn's unsigned DLLs on the build machine, and a lender's hardened environment may too. Logistic regression (L-BFGS), PAV isotonic regression, AUC and a histogram GBM come to about 200 auditable lines.

**D-13 · Offline-first PWA, Hindi first, voice everywhere, plus a café pathway.**
Targets entry-level Android phones, low literacy, and patchy connectivity. Physical steps (CSC biometric registration, vet certificate) route to a JanAI Café without blocking the rest of the file.

**D-14 · Scheme conditions vs lender decisions vs availability.**
Following the external review, every scheme separates three things: the scheme's own conditions (the proof tree), what the *lender* decides (`lender_checks`: membership, appraisal, credit norms), and whether the scheme is running at all (`availability`). A guarantee like CGTMSE is never presented as something the borrower "gets". Conflicting official sources are shown as cited `caveats` (e.g. PM Vishwakarma's 5-year lookback vs FAQ 24).

**D-15 · Unlocks only when conditions would be fully met.**
An action is offered only if, once taken, a scheme's conditions would be met (not merely "undecided"). If facts are missing to judge that, the agent first asks the most decisive one (ranked by value of information).

**D-16 · Fail-closed fairness, with automatic replication.**
Gates cover gender, area, caste and zone and run on a validation split; the test split is used once. When a gate fails on test, training re-measures it on a fresh draw and records both results; the release decision stays BLOCKED. We do not loosen a gate after seeing a result.

**D-17 · Authentication proportional to a demo, with a production switch.**
Per-case bearer tokens and one key per lender (each mapped to a lender principal) are enough to make cases private, keep lenders apart and make decisions attributable in a demo. `SAAKH_ENV` accepts only `demo` or `production`; production removes demo routes and refuses missing, demo-valued or short keys. Case tokens live in the tab's `sessionStorage` and are cleared when the case is left, which matters on a shared café device. A real deployment still needs identity, an SMS OTP provider, encryption at rest, key rotation and a key store (documented, not built).

**D-19 · Fail closed on unknowns in scheme rules.**
A coarse fact must not turn into a pass. The PMEGP negative list is cleared only for activities known not to be on it; otherwise the applicant is asked, and the DIC confirms. Missing SVANidhi repayment history shows the tranche ladder, not "your next tranche". CGTMSE cover is not given as a percentage, because it depends on a table the lender applies.

**D-20 · The approval covers the bytes, not just the list.**
The package hash includes each attachment's SHA-256, size and type. Replacing a file voids the approval; if the file was already sent, the lender copy is marked superseded and decisions are locked until the entrepreneur re-approves. The lender downloads only bytes that still match the approved fingerprint, and each download is audited.

**D-21 · Disputes, not overrides, for sourced data.**
An entrepreneur may know that DigiLocker or the bureau is wrong, and must be able to say so. But if typing a new value changed eligibility, anyone holding the case token could turn "defaulter: yes" into "no". So a correction to a sourced value is recorded as an open dispute that goes to the lender with the file, and the sourced value stays in use until it is fixed at the source or the lender accepts it. The entrepreneur's own earlier answers can simply be corrected.

**D-22 · Anything that must be deletable stays out of the hash chain.**
The audit log is append-only by design, so it cannot honour a revocation. It therefore stores digests instead of personal or financial summaries, and, after the fourth review, no answer values, correction reasons or raw error messages at all; readable detail lives in the case, where revocation and expiry can remove it.

**D-23 · "Eligible" vs "provisional".**
Some conditions can only be confirmed by an agency (the DIC for PMEGP's negative list; the bank for a second loan's margin-money adjustment). Saakh still evaluates them so it can plan, but a match that depends on them is labelled provisional everywhere it appears, including the offer and the file the entrepreneur approves. The underlying negative list changes over time and could not be machine-read, so it is not hard-coded beyond clear cases.

**D-24 · A lender decision is a state transition on one file version.**
Decisions are only valid for the exact copy the entrepreneur approved. The lender copy carries a revision; the decision is a compare-and-set on that revision with its audit entry in the same transaction; sanction and decline are final; retries carry an idempotency key. Telling the entrepreneur is a separate, idempotent delivery step so a busy case never makes a recorded decision look failed.

**D-25 · The lender sees a frozen copy, not the live case.**
Checking "is this file superseded?" and then reading the live case are two steps, and another worker can change the case in between. Instead of locking across them, the lender's view is written once, with the approved package, in the same row. What the bank reads is therefore always the approved version by construction.

**D-26 · A code proves one thing, once.**
An operator at a café must never hold a reusable key to the entrepreneur's decisions. So each step gets its own short-lived code, consumed on use, stored only as a keyed hash. Without a real SMS provider this cannot be offered in production, and the code says so rather than pretending.

**D-18 · Real files, honestly handled.**
Uploads are validated by content, size-limited and fingerprinted, but not interpreted; the lender verifies them. A CSV statement parser gives a real manual path when the Account Aggregator is unavailable or declined.

**Assumptions to validate (labelled in the UI):** indicative scheme lending rates (11%); 50% uplift haircut; 60% stress threshold; ₹ value of scheme benefits vs. 30% informal credit (midpoint of the brief's 24–36%); lender rework economics; the 17-paper traditional checklist.
