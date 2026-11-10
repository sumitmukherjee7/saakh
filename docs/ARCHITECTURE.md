# Architecture

```
 Channels      Entrepreneur PWA (voice, Hindi/English, offline queue) · JanAI Café assisted mode · Branch console · Federation screening
                                │ REST (FastAPI)
 Agent         runtime.py, case memory (SQLite JSON) · goal planner · checkpoints · retry/fallback · Hindi NLU
                                │ every tool call
 Guard         tools.py, ACTIVE signed consent of the right kind · approval hash == application hash · go-ahead for outward actions
                                │                           └── every call (allowed or blocked) → hash-chained audit log
 Engines       schemes/ (cited 3-valued rules, VOI questions, benefits) · cashflow/ (categorise, informal debt, features, sizing, APR)
               risk/ (monotone WoE scorecard, calibration, bootstrap interval) · docs/ (set-cover planner, DPR, credit memo)
 Integrations  integrations.py, DigiLocker · Account Aggregator FIP · bureau · Udyam · SVANidhi LoR · lender LOS   [all SIMULATED]
```

## The agent loop

`runtime._step()` checks the case against an ordered list of goals and advances the first unmet one. Because it re-derives "what's next" from state after every event, it recovers correctly from interruptions, corrections, revocations and lender queries. Nothing is a fixed script.

1. **intake**: parse the request (amount, activity, purpose, SHG?)
2. **consent**: four separate artefacts in one screen; the optional ones can be declined
3. **fetch**: e-KYC, then the AA statement (*TransientError → exponential backoff, up to 3 tries → fallback: upload / JanAI Café*), then bureau and Udyam
4. **analyse**: categories, informal-debt pattern, seasonality, B2B evidence, derived facts *with evidence strings*
5. **schemes**: re-evaluate whenever `facts_version` changes
6. **unlock actions**: offer actions that flip a scheme from F to T/U (Udyam registration, SVANidhi LoR); the human decides
7. **questions**: the next highest-value-of-information question (max 10), plus the moneylender-outstanding question when relevant
8. **offers**: best financing plan (primary loan route + stackable guarantees and entitlements), each sized and scheduled; the entrepreneur chooses
9. **documents**: exact minimum-effort set cover; uploads, or routing to a JanAI Café
10. **DPR → assemble** the application package and its SHA-256 hash
11. **approval checkpoint**: approval binds to the hash; a sharing-consent artefact is created for the chosen lender
12. **submit** (guarded) → lender LOS → track the lender's decisions

The human always decides at: each consent, each outward action, the offer choice, the final approval, and any reply to a lender query.

## Guardrails are code, not prompts

| Boundary (from the brief) | Enforcement |
|---|---|
| Financial data only with consent | `tools.guard` requires an ACTIVE, unexpired, HMAC-valid artefact of the right kind *before* the tool runs. A manually uploaded statement has its own `statement_upload` consent and never revives a declined AA consent. Revocation deletes derived data and, after submission, erases the lender copy |
| Entrepreneur approves every application | `submit_application` requires `approval.hash == application.hash` plus an ACTIVE `share_with_lender` consent for that lender; any edit regenerates the hash and voids the approval. The API autopilot always stops before approval, and demo steps are audited as `demo-autopilot` |
| Only the right people see a case | Per-case bearer token (hash stored) on every case route; one key per lender, mapped to a lender principal that must match the file's addressee on every read, download and decision (otherwise 404), plus a per-file consent check; consent ids must belong to the case and its pending request; client events are whitelisted; answers are accepted only for the question being asked; a `correct` event replaces the entrepreneur's own earlier answer (keeping the old value), but against a value from e-KYC, bureau, Udyam or the statement it only records an **open dispute** that travels in the package to the lender; the sourced value stays operative; `SAAKH_ENV` must be `demo` or `production`, and production rejects missing, demo or weak keys (length, estimated entropy, repetition) |
| Every eligibility claim cites its source | The KB loader raises `KBError` on any criterion without a citation; every proof node carries the resolved source, locator and verification status |
| Self-declared conditions are not presented as verified | A criterion can name the agency that `verified_by` it (e.g. PMEGP negative list → DIC; second-loan margin-money adjustment → bank/KVIC). If the scheme is eligible only on such a criterion, the result is **provisional**, and that label follows it into the status pill, the summary, the offer card, the approved package and the lender view |
| A lender decision applies to exactly one approved file version | Every write of the lender copy bumps its revision. The decision route re-reads and re-checks it inside the case lock; the database write is one `IMMEDIATE` transaction that succeeds only if the copy is still at that revision, still `submitted`/`query`, still has its package and is not superseded, and it writes the audit entry in the same transaction. Sanctioned and declined are final. A client `request_id` makes retries idempotent (a reused id with different content is refused). The case is notified afterwards through an idempotent outbox step (keyed by decision id) that is retried on conflicts and completed the next time the case is opened, so a decision is never lost or applied twice |
| Decision data is bounded, and the reasons are the bank's | A decline needs at least one of the branch's own reason codes (repayment capacity, credit history, documents, scheme conditions, viability, collateral, policy, other), at most 8. Saakh's scorecard factors are never sent as the bank's reasons. A query needs its question; notes (500 chars max) live only in the erasable lender copy and case. The audit stores the decision, its reason codes, the file hash and a digest of the full record, never amount, note or officer. Every decision request carries a required `request_id`; a receipt (a hash of the whole request) is kept per application, so a retry replays and a reused id with different content is refused |
| Strict events, only at their checkpoint | Every client event is checked against a typed schema before anything runs: booleans must be real booleans (a string such as "false" is rejected, never treated as true), integers real integers, strings bounded, unknown fields refused. Answers, skips, offer choice, unlock actions, lender choice, approval and café scheduling are accepted only when that checkpoint is pending and only for what it is asking; a document upload must be one the current plan asks for. So nothing can change a sent file except an explicit correction or document, which supersede it |
| Assisted-mode codes are one-time, per step and short-lived | Each consequential step (consent, statement upload, approval) gets its own challenge; only an HMAC verifier (keyed with the signing key) is stored; a code is valid for that step only, for 10 minutes, and is consumed on first use. Five wrong codes void it and lock entry for 15 minutes; 15 wrong codes, or 12 codes issued, disable code entry for the case. New codes are limited to one a minute. With no SMS provider integrated, production refuses assisted mode |
| Lender views show exactly what was approved | At submission the file's lender view (facts shared with the bank, analysis, score, eligibility, documents, offer) is frozen into the same database row as the approved package. The detail view, credit memo and project report are built only from that frozen view, never from the live case, so no concurrent change can leak into them; withdrawal erases it |
| Calibrated, fair, explainable risk | Training-time gates (AIR ≥ 0.8, \|EOD\| ≤ 0.05, \|calibration gap\| ≤ 2 pp, proxy gate); protected attributes are never inputs; a points table explains each score exactly |
| No unsubstantiated financial claims | Benefits carry citations; rates and APRs are labelled *indicative; the lender's KFS is binding*; explanations are generated from the cited proof tree, never free-written |
| Simulations disclosed | Every simulated adapter returns `simulated: true`, and the UI badges it. Statement coverage (months, dates, AA vs upload) is shown on the insight card, lender view and DPR |
| A blocked model is not used as if validated | `scorecard.release_status()` reads the training report; in production a BLOCKED (or unreadable) report stops before any score-based offer; in demo every offer carries the BLOCKED notice |
| Failure recovery around external calls | e-KYC, bureau and Udyam calls retry transient failures with backoff; submission writes its intent first and calls the LOS with an idempotency key scoped to application, lender and approved file version. The simulated LOS keeps its receipts in the database, so a server killed after the LOS accepted the file resumes in a new process without a duplicate (tested with a real process exit) |

## Retention on revocation

| Revoked consent | Deleted | Kept (audit only) |
|---|---|---|
| Bank statement / uploaded statement | uploaded statement rows, analysis, facts derived from it (e.g. turnover), offers, score, DPR; chat cards and trace summaries built from it; if submitted: lender package, uploaded documents | consent artefact & status history; audit events (hashes and digests, no personal or financial content) |
| e-KYC / bureau / Udyam lookup | every fact obtained under that consent, the raw record, corrections that quoted it; chat cards and trace summaries built from it; downstream offers, score, documents, DPR; if submitted: lender package, uploaded documents | as above |
| Share with lender | lender package and its contents, uploaded documents, the lender's decisions in the case (amounts, notes, reasons) and their chat cards | application id, file hash, timestamps, approval metadata, LOS reference; for each decision only its id, type and time |

## Data minimisation

- AA transactions are processed in memory and never written to disk; only monthly aggregates, features and evidence strings persist. A manually uploaded statement is stored (raw rows, in SQLite) only while its consent is active.
- **Expiry is treated like revocation.** A background sweep (every 5 minutes by default, or `python -m saakh.sweep` from cron) marks lapsed consents EXPIRED and runs the same deletion; the same check also runs before any case or lender file is read.
- **The audit chain holds no personal or financial values.** Event payloads are built from a per-type allowlist: an answer or correction records the fact name, not the value or reason; messages record their length; tool errors record the exception type and a digest; lender notes record their length. Tool calls whose summaries contain personal or financial data are logged with a SHA-256 digest; the readable versions live only in the deletable case.
- **Concurrent writers.** Case saves are revision-checked inside an `IMMEDIATE` SQLite transaction, so a stale copy (another request, worker or the sweep) is rejected rather than overwriting newer state.
- Deletion is logical (SQLite rows are removed or overwritten); there is no encryption at rest, and backups are out of scope for this demo.
- Uploaded documents are fingerprinted (SHA-256) and stored for the lender. Saakh does not read them, and the UI says so.
- Audit payloads are allowlisted: no OTPs, file bytes, free text, answer values, correction reasons, filenames, decision amounts, notes or officer names.
- Not yet implemented: encryption at rest, key rotation, real SMS delivery.
- Questions are asked only when they change an outcome (VOI > 0). Sensitive ones are discounted, optional, and never used in scoring.
- The lender sees the package covered by the sharing consent, and the endpoint returns **403** once that consent is revoked.

## Integrity

`store.audit()` appends `hash_n = SHA256(prev ‖ seq ‖ ts ‖ actor ‖ action ‖ SHA256(payload))`, and `verify_chain()` recomputes the chain. The branch console shows three checks: the package hash, the approval binding, and that the chain is intact. A test tampers with one row and the check detects it.

## Offline and low-end devices

The PWA is a ~190 KB gzipped app shell, cached by a service worker. Events created offline go to a localStorage outbox and replay in order on reconnect (the phone header has a "simulate network loss" toggle). Voice input uses the browser's speech recognition (`hi-IN`, `en-IN`). Every agent message has read-aloud.

## Production path (what replaces each simulation)

| Simulated | Production |
|---|---|
| `integrations.aa_fetch` | FIU integration with a licensed AA (ReBIT FI/request + FI/fetch, JWS-signed artefacts, decrypt with the FIU key) |
| `integrations.ekyc` | DigiLocker / Aadhaar offline e-KYC (XML) |
| `integrations.bureau` | Bureau soft-pull API with a consent reference |
| `udyam_lookup / register` | Udyam APIs via a registered facilitator, or an assisted flow at a JanAI Café / CSC |
| `los_submit` | Lender LOS or the Unified Lending Interface |
| synthetic population | Lender's historical book (with reject inference), then shadow mode before go-live |
