# Field research plan

The organisers' six questions are turned into hypotheses, each tied to a product decision it would change and a way the product itself measures it.

| # | Organisers' question | Our hypothesis | If wrong, we change… | Instrumentation in Saakh |
|---|---|---|---|---|
| 1 | Which schemes has the business heard of, and from whom? | Most know MUDRA by name only; few know PMV, CGTMSE or the MSMED 45-day right | Order of scheme cards; how much to explain | Ask "heard of it?" before showing each eligible scheme (planned); federation screening shows the eligible-vs-claimed gap |
| 2 | What did the last loan attempt require, and where did it stall? | Stalls at ITR, collateral, project report and repeat visits | Document planner weights; which documents Saakh must generate | Document costs are explicit (`docs/planner.py`); compare the 17-paper checklist with branch checklists collected in the field |
| 3 | What does the agent charge, and what does he actually do? | 10–15%, mostly document chasing and branch access | The fee calculator; the JanAI Café service design | "Agent fee avoided" input in the economics view |
| 4 | What informal records exist, and would the owner share them? | UPI history yes (with a clear purpose and expiry); notebooks and khata partly | Whether to add khata/photo ingestion | Consent decline rates per artefact (audit log: `consent.rejected`) |
| 5 | What does a branch manager need to see before saying yes? | Repayment capacity, existing debt, a complete KYC set, scheme/CGTMSE mapping, a DPR | Credit-memo layout; which reason codes come first | Credit memo PDF + branch console; query reasons logged (`lender.query`) |
| 6 | Why do eligible applicants drop out midway? | Long forms, repeat visits, fear of rejection, no feedback | Question budget (now ≤ 10), offline queue, assisted path, "not now" plan | Funnel = the case's `pending` stages; drop-off per stage |

**Sample.** 15 to 20 owners across the six persona types (tailoring, fabrication, dairy, SHG enterprise, street food, kirana), 3 to 5 bank branch managers, 2 to 3 loan agents, and one SHG federation or JanAI Café operator.

**Following the money.** Interview 3–5 branch managers and log, per file, the touches, hours, visits and rework cycles. Feed the averages into the calculator to replace our assumptions, and price the per-file fee below the measured rework cost.

**Interview kit (per persona type):** 20-minute interview, with consent to view UPI history on the owner's phone (no data leaves the device during research), plus a paper or khata photo check and the last loan's document list.
