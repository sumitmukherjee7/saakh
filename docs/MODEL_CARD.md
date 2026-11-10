# Model card: Saakh cash-flow scorecard

**What it outputs.** A **simulated risk estimate**: the model's probability for a *synthetic* default label, plus a band (A–E), reason codes and a bootstrap interval. It is **not** a validated probability of default. The training labels are drawn from a hand-specified generator (`risk/synth.py`), not from observed repayment. The API marks every score with `output_kind: "simulated_risk_estimate"`, and the UI labels it the same way.

**Intended use.** Decision support and loan sizing in a demonstration, and a template pipeline for a lender to re-fit on its own outcomes. The lender decides; Saakh never auto-rejects. **Out of scope:** any real credit decision, pricing or collections until the model is re-fit and validated on lender data (out-of-time, with reject inference) and run in shadow mode.

**Model.** Monotone Weight-of-Evidence scorecard: quantile bins merged until the bad rate is monotone in the economically sensible direction, then L2 logistic regression on WoE. Scaling: 600 points ↔ 30:1 odds; +40 points doubles the odds. Calibration is chosen by 2-fold cross-fitting on the calibration split (identity vs Platt; identity selected, CV ECE 1.07% vs 1.36%). Interval: 25 bootstrap coefficient refits, plus a **heuristic** ×0.7/×1.4 widening for thin files (< 9 months). That widening is a stated rule of thumb, not an estimate.

**Inputs (10).** Income stability · de-seasonalised sales trend · lean-month ratio · margin after costs · existing debt service · moneylender-repayment share · cash-buffer days · bounces · share of months with spending above income · proposed EMI ÷ income.
**Never inputs:** gender, caste, religion, location, zone, rural/urban, age.

**Evaluation protocol.** Train 50% · validation 15% (candidate-feature and proxy gates) · calibration 15% · test 20% (computed once, after every choice was made). Random split from one generator, so no temporal or external validation is possible on synthetic data.

**Gate log (validation split).**

| Feature | Decision | Why |
|---|---|---|
| Business size (log average inflow) | rejected | AUC gain below threshold; on earlier runs it doubled the rural/urban opportunity gap; predicts gender and rural (AUC ≈ 0.65) |
| Digital share of sales | rejected | no AUC gain; strong rural proxy (AUC 0.73) |
| Payer diversity | removed | proxy for rural (AUC 0.60) with weak signal (IV 0.015) |

**Test metrics (n = 6,000; 95% bootstrap CI).** AUC 0.736 (0.714–0.759) · PR-AUC 0.199 (0.177–0.228) · Brier 0.073 (0.067–0.078) · ECE 0.61% · log loss 0.263 · KS 0.345. Gradient-boosting challenger AUC 0.735.

**Fairness gates (AIR ≥ 0.80, |EOD| ≤ 0.05, |calibration gap| ≤ 2 pp) on seven pairs.**

| Pair | AIR (95% CI) | EOD (95% CI) | Result |
|---|---|---|---|
| Women vs men | 0.985 (0.95–1.00) | −1.2 pp (−3.6 to +1.0) | pass |
| Rural vs urban | 0.999 (0.97–1.00) | −0.6 pp (−2.5 to +1.9) | pass |
| Rural women vs urban men | 0.985 (0.94–1.00) | −1.8 pp (−5.1 to +1.7) | pass |
| SC vs General | 0.994 (0.95–1.00) | +0.4 pp (−3.3 to +3.4) | pass |
| **ST vs General** | 0.919 (0.85–0.98) | **−7.3 pp (−11.9 to −3.4)** | **FAIL** |
| OBC vs General | 0.978 (0.95–1.00) | −1.3 pp (−3.7 to +0.9) | pass |
| West vs North-east (most different zones) | 0.946 (0.88–0.99) | −5.0 pp (−10.4 to −0.3) | pass (at the edge) |

**Release decision: BLOCKED.** Training automatically re-measured the failed pair on an independent fresh draw (n = 20,000, seed 1007): EOD −1.85 pp, AIR 0.981. Across the full 30,000-business population the gap is −2.0 pp. The simulator assigns caste independently of every other variable, so the test-split gap is most likely sampling noise in a ~550-person subgroup across seven comparisons. The rule fails closed regardless: on real data this model would not be deployed until the gap was explained. Here it is used for demonstration only. **This is enforced at runtime, not just documented:** `scorecard.release_status()` reads this report; with `SAAKH_ENV=production` a BLOCKED or unreadable report stops the agent before any score-based offer, and in demo builds every offer card carries the BLOCKED notice.

**Why favourable group results are partly by construction.** The generator makes latent business quality identically distributed across groups, and the label depends only on quality, leverage and sector shocks. Groups differ only in *measurement* (business size, cash share, informal-debt reliance, ITR and collateral holding). So the comparison against a document checklist shows *the mechanism*, not real-world effect sizes.

**Access comparison (test split, PD policy 10%).** Saakh approves 73.5% and reaches 76.3% of good borrowers, with a 5.0% default rate among the approved. The traditional rule approves 6.0% and reaches 6.1% of good borrowers, with 7.2% defaults.

**Explanations.** Contributions are exact for the fitted scorecard (additive points) and give counterfactual "next bin" advice. They are *not* causal explanations.

**Known limitations.** Synthetic labels; a single random split; a sector seasonal index that must be estimated from pooled real data; rule-based categorisation tuned to common Indian narration formats; moneylender detection is a pattern and is shown as "likely".
