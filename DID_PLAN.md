# Difference-in-Differences — build plan

Estimated as the most impactful next method to build after Causal Impact.

**Why:** Causal Impact only covers "no control group, single series" scenarios.
Difference-in-Differences (DiD) covers the other common CRO setup — geo holdouts,
staged/percentage rollouts, feature flags shipped to one segment but not another.
It reuses the existing `ValidationResult` / `AssumptionResult` / `assumption_panel.render()`
patterns as-is — only a new ingestion shape (panel data: unit, time, group, outcome)
and a new assumption check (parallel trends) are added.

v1 scope is the canonical 2×2 design: one binary group (treated/control) and one
intervention date shared by the whole treated group. Staggered timing (units
treated at different dates) is out of scope for v1 — see "Package choice" below
for why that's still worth planning around now.

---

## Package choice

Estimation is built on [`diff-diff`](https://github.com/igerber/diff-diff) rather
than a hand-rolled `statsmodels` OLS formula (the original plan here). Comparison,
as of September 2026:

| | `diff-diff` | `statsmodels` | `linearmodels` |
|---|---|---|---|
| Fit for the 2×2 case | `DifferenceInDifferences(cluster=...).fit(data, outcome=, treatment=, post=)` → `.att/.se/.conf_int/.p_value` — matches `DiDResult` almost field-for-field | Hand-write the `group:post` interaction formula + `cov_type='cluster'` | Hand-write via `PanelOLS`; better FE ergonomics, same amount of glue code as statsmodels |
| Pre-trends test | Built in: `check_parallel_trends()` | Hand-write the pre-period `time × group` regression | Hand-write |
| Staggered-adoption path | Same package: `CallawaySantAnna`, `SunAbraham`, `ImputationDiD` | None — would need a second library later | None — would need a second library later |
| New dependency footprint | numpy/pandas/scipy only, prebuilt wheels (cp39–cp314, linux/mac/win) | Already a dependency | New dependency |
| License | MIT | BSD | NCSA |
| Maturity | First released 2026-01-02, already v3.12.0 (84 releases) — fast-moving, single maintainer (bus-factor risk), but 393 stars and "Production/Stable" | Long-established, boring, trusted | Long-established (1070 stars), trusted |

Decision: `diff-diff`. It removes the hand-rolled statistics (interaction formula,
cluster SE, pre-trends regression) that are easy to get subtly wrong, and it's the
same dependency the roadmap's Synthetic Control item would likely reach for later
(it ships synthetic-control estimators too). The tradeoff being accepted is
dependency risk on a young, single-maintainer package — pin the version and
smoke-test `pip install diff-diff` in CI before merging.

Also considered and rejected: `differences` (bernardodionisi) — GPL-3.0 (copyleft,
avoid for a product dependency) and no commits since 2026-04.

---

## Files to build, in order

- [x] 1 - `core/ingestion/wrangler.py` (extend)

  Add `shape_for_did()`: pivots/validates panel data into long format with columns
  `unit`, `time`, `group` (treated/control), `outcome`, plus a `post` flag derived
  from the intervention date. Reuses existing `resample`.

- [x] 2 - `core/ingestion/validator.py` (extend)

  Add `validate_did()`: checks both groups are present and non-empty, both groups
  have pre- and post-period observations, the group column is binary, and there's
  sufficient pre-period length per group.

- [x] 3 - `core/assumptions/parallel_trends.py` (new)

  Two checks:

  * Pre-trend test: thin wrapper around `diff_diff.check_parallel_trends()`,
    restricted to the pre-period; flag if treated/control trends diverged
    significantly before treatment.
  * A plot helper (hand-written — `diff-diff` doesn't expose one for the plain
    2×2 estimator) returning group-mean-by-period data for the UI to render
    treated-vs-control pre-period trends side by side.

- [x] 4 - `core/methods/diff_in_diff.py` (new)

  Thin wrapper around `diff_diff.DifferenceInDifferences(cluster='unit').fit(df,
  outcome=, treatment=, post=)`. Cluster-robust standard errors and the
  confidence interval come from the library; this module just adapts the
  ingestion output to `.fit()`'s expected columns and adapts `results` into
  `DiDResult`.

- [x] 5 - `core/results/models.py` (extend)

  `DiDResult` dataclass: effect estimate (`.att`), CI (`.conf_int`), p-value
  (`.p_value`), standard error (`.se`), group means by period (the 2×2 table:
  treated/control × pre/post, computed here — not part of the library result),
  `results.summary()` string, plain-language report string.

- [x] 6 - `components/results_panel.py` (extend or new method-specific render fn)

  Visualize: parallel-trends pre-period chart, the classic DiD 2×2 diagram (four
  points connected by lines, counterfactual dashed), effect estimate with CI.

- [x] 7 - `pages/02_diff_in_diff.py` (new)

  Orchestrate: upload → map columns (unit, time, group, outcome) → intervention
  date → assumption checks (parallel trends) → run → results. Mirrors
  `01_causal_impact.py`'s flow.

- [x] 8 - `app.py`

  Flip "Difference-in-Differences (ROADMAPPED)" to a live entry once shipped.

---

## Post-v1 addition: control-group suggestion

`wrangler.suggest_control_units()` wraps `diff_diff.rank_control_units()`: given
raw panel data with many candidate units and a chosen treated unit (or units),
ranks the rest by pre-period outcome-trend similarity so the analyst doesn't
have to eyeball a control group. Wired into the DiD page as an optional
pre-mapping step (`ingestion_ui.render_control_suggestion()`) — ranks
candidates, lets the analyst confirm which to keep, and writes a `did_group`
column the analyst then selects in the normal column-mapping step. Doesn't
require an intervention date to be finalized first — it asks for its own
approximate cutoff for ranking purposes only.

---

## Post-v1 addition: BigQuery data source

Both pages now offer BigQuery (GA4 events_* export) as an alternative to CSV
upload -- core/ingestion/bq_client.py (OAuth + query execution, no `foe`
dependency; modeled on hexkit's utility/bq_client.py, the proven pattern --
foe.data.DataEngine exists but isn't what hexkit actually uses in production)
and core/ingestion/bq_sql_builder.py (build_timeseries() for CI and
flat-column DiD segments; build_grouped_timeseries(), new, for DiD segments
defined by an event_params value -- e.g. a feature-flag/rollout split --
which no existing builder in foe or hexkit covers). UI in
components/bq_ui.py. Both return a plain DataFrame that feeds the exact same
downstream pipeline a CSV upload does -- no changes needed to
shape_for_did()/validate_did()/column mapping.

Not verified by an executed test in this environment: the live OAuth
round-trip and actual BigQuery query execution -- both need real Google
credentials, and the sandboxed test run was additionally blocked by the
safety classifier (flagged as credential-handling code) before that point
would have been reached anyway. Verified instead: the SQL builders' output
(including a caught double-prefix bug), the state base64 encode/decode
round-trip with synthetic values, and that every file compiles. Smoke-test
the real sign-in flow before relying on this in production.
