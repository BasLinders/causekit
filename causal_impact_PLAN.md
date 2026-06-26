# Files to build, in order

1 - `core/ingestion/loader.py`

CSV upload only to start. Returns a clean DataFrame with a validated datetime index. BigQuery will be added later once the method is stable.

2 - `core/ingestion/cleaner.py`

Handles nulls (interpolation for small gaps, flags large gaps), type coercion, and ensures regular time intervals — irregular spacing will break the BSTS model silently.

3 - `core/ingestion/wrangler.py`

Constructs the pre/post split from the intervention date. Shapes the DataFrame into the structure `tfcausalimpact` expects: datetime-indexed, response column first, covariates after.

4 - `core/ingestion/validator.py`

Early, readable errors before anything runs. Checks:

* Response column exists and is numeric
* Intervention date falls within the series, with sufficient pre-period length
* Covariate columns (if provided) are numeric and cover the full period
* No all-null columns

5 - `core/assumptions/stationarity.py`

Two checks:

* ADF test on the pre-period response series — flags if it's non-stationary
* Covariate exogeneity warning — reminds the user that covariates must be unaffected by the intervention (can't be tested, but should be surfaced explicitly)

6 - `core/methods/causal_impact.py`

Thin wrapper around tfcausalimpact. Accepts the validated, wrangled DataFrame and intervention date. Returns a standardized result object.

7 - `core/results/models.py`

Result dataclass for CausalImpact output — posterior series, summary statistics, plain-language interpretation string.

8 - `components/ingestion_ui.py`

Reusable upload widget + column mapping UI. Built generically so other methods can use it.

0 - `components/assumption_panel.py`

Renders assumption check results in a consistent format — pass/warn/fail with explanation.

10 - `components/results_panel.py`

Renders the three output charts (actual vs. counterfactual, pointwise effect, cumulative effect) and the summary text.

11 - `pages/01_causal_impact.py`

Orchestrates the above into a linear Streamlit flow: upload → column mapping → assumption checks → run → results.
