# Difference-in-Differences — build plan

Estimated as the most impactful next method to build after Causal Impact.

**Why:** Causal Impact only covers "no control group, single series" scenarios.
Difference-in-Differences (DiD) covers the other common CRO setup — geo holdouts,
staged/percentage rollouts, feature flags shipped to one segment but not another.
It reuses the existing `ValidationResult` / `AssumptionResult` / `assumption_panel.render()`
patterns as-is, with no new infrastructure required — only a new ingestion shape
(panel data: unit, time, group, outcome) and a new assumption check (parallel trends).

---

## Files to build, in order

- [ ] 1 - `core/ingestion/wrangler.py` (extend)

  Add `shape_for_did()`: pivots/validates panel data into long format with columns
  `unit`, `time`, `group` (treated/control), `outcome`, plus a `post` flag derived
  from the intervention date. Reuses existing `resample`.

- [ ] 2 - `core/ingestion/validator.py` (extend)

  Add `validate_did()`: checks both groups are present and non-empty, both groups
  have pre- and post-period observations, the group column is binary, and there's
  sufficient pre-period length per group.

- [ ] 3 - `core/assumptions/parallel_trends.py` (new)

  Two checks:

  * Pre-trend test: regress outcome on `time × group` interaction restricted to
    the pre-period; flag if the interaction term is significant (trends diverged
    before treatment).
  * A plot helper returning data for the UI to render treated-vs-control
    pre-period trends side by side.

- [ ] 4 - `core/methods/diff_in_diff.py` (new)

  Thin wrapper around `statsmodels` OLS: `outcome ~ group + post + group:post`,
  with the `group:post` coefficient as the effect estimate, robust (cluster-by-unit)
  standard errors, and a confidence interval.

- [ ] 5 - `core/results/models.py` (extend)

  `DiDResult` dataclass: effect estimate, CI, p-value, group means by period
  (the 2×2 table: treated/control × pre/post), regression summary, plain-language
  report string.

- [ ] 6 - `components/results_panel.py` (extend or new method-specific render fn)

  Visualize: parallel-trends pre-period chart, the classic DiD 2×2 diagram (four
  points connected by lines, counterfactual dashed), effect estimate with CI.

- [ ] 7 - `pages/02_diff_in_diff.py` (new)

  Orchestrate: upload → map columns (unit, time, group, outcome) → intervention
  date → assumption checks (parallel trends) → run → results. Mirrors
  `01_causal_impact.py`'s flow.

- [ ] 8 - `app.py`

  Flip "Difference-in-Differences (ROADMAPPED)" to a live entry once shipped.
