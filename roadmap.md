# Causekit roadmap

## ✅ Causal Impact
Estimate the effect of an intervention on a time series metric using a Bayesian structural time series model. Suited for situations where no control group exists and the intervention affected all units simultaneously.

**Core:** `loader`, `cleaner`, `wrangler`, `validator`, `stationarity`, `causal_impact`, `CausalImpactResult`

**Components:** `ingestion_ui`, `assumption_panel`, `results_panel`

---

## 🔲 Difference-in-Differences
Compare a treated and control group observed before and after an intervention. Suited for staged rollouts, geo experiments, and cohort-based treatments where a clean control group exists.

Key assumption check: parallel trends in the pre-period — visualized and tested before analysis runs.

---

## 🔲 Propensity Score Matching
Construct comparable groups from observational data to reduce selection bias. Suited for post-hoc analysis where users self-selected into a condition rather than being randomly assigned.

Key output: balance diagnostics (standardized mean differences before and after matching) alongside the effect estimate.

---

## 🔲 Regression Discontinuity
Estimate effects at a hard assignment threshold — loyalty tiers, score cutoffs, spend limits. Suited for situations where treatment was determined by crossing a known boundary.

Key output: scatter plot with fitted lines either side of the cutoff, effect estimate at the threshold.

---

## 🔲 Synthetic Control
Build a weighted counterfactual from a pool of donor units when a single unit is treated. Suited for cases where one market, product, or region received an intervention and others did not.

---

## 🔲 Mediation Analysis
Decompose a total effect into direct and indirect paths through a mediator variable. Suited for understanding *why* an intervention worked, not just *that* it worked.
