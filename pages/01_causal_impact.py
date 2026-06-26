import streamlit as st

from components import assumption_panel, ingestion_ui, results_panel
from core.assumptions import stationarity
from core.ingestion import cleaner, loader, validator, wrangler
from core.methods import causal_impact

st.set_page_config(page_title="Causal Impact", layout="wide")
st.title("Causal Impact")
st.caption(
    "Estimate the effect of an intervention on a time series metric "
    "using a Bayesian structural time series model."
)

# ── Documentation ──────────────────────────────────────────────────────────────

with st.expander("Data requirements"):
    st.markdown(
        """
        Your CSV must contain at least two columns:

        | Column | Type | Description |
        |---|---|---|
        | Date | date / datetime | One row per time period. Supported formats: `YYYY-MM-DD`, `DD-MM-YYYY`, `MM/DD/YYYY`. |
        | Response | numeric | The metric you want to analyze (e.g. conversions, revenue, sessions). |
        | Covariates *(optional)* | numeric | Control time series unaffected by the intervention. Improves counterfactual accuracy. |

        The column names themselves do not matter — you will map them in the interface.
        At least 28 data points in the pre-period are recommended (4 full weeks for daily data).
        """
    )
    st.info("Make sure that your data spans **both** the pre-intervention and post-intervention periods. You can indicate the intervention date in the tool to split the data.")
    st.markdown(
        """
        **Covariates**

        A covariate must correlate with the response metric during the pre-period,
        and must not have been affected by the intervention itself.

        | | Examples |
        |---|---|
        | ✅ Good | Organic sessions (if the intervention was paid) |
        | ✅ Good | A comparable market or region that was not treated |
        | ✅ Good | A related product category the intervention did not touch |
        | ✅ Good | A market-wide benchmark or macro indicator |
        | ❌ Bad | Any metric downstream of the intervention (e.g. revenue if sessions were treated) |
        | ❌ Bad | Metrics measured on the same exposed users |
        | ❌ Bad | Series with a different seasonal pattern than the response |

        One or two well-chosen covariates outperform a large set of loosely related ones.
        Covariates do not need to be the same data type as the response — rates, counts, and
        continuous values can be mixed freely. If covariates differ greatly in scale from the
        response, consider normalizing them before upload to avoid numerical instability.
        """
    )
    st.markdown("**SQL template (BigQuery)**")
    st.code(
        """
SELECT
    DATE(event_date) AS date,
    SUM(metric)      AS response
FROM `project.dataset.table`
WHERE event_date BETWEEN '2024-01-01' AND '2024-06-30'
GROUP BY date
ORDER BY date
        """,
        language="sql",
    )
with st.expander("What it does"):
    st.markdown(
        """
        Causal Impact fits a Bayesian structural time series (BSTS) model on the pre-intervention period
        to learn the normal behaviour of your metric. It then projects that model forward into the
        post-intervention period to construct a **counterfactual** — what the metric would have looked
        like had the intervention never happened.

        The difference between the observed values and the counterfactual is the estimated causal effect.
        Credible intervals quantify the uncertainty around that estimate.

        If covariate series are provided, the model uses them to produce a more accurate counterfactual
        by anchoring on control metrics that were not affected by the intervention.
        """
    )

with st.expander("How to use"):
    st.markdown(
        """
        1. **Upload** a CSV file containing your time series data.
        2. **Map columns** — select which column is the date, which is the response metric,
           and optionally which columns are covariates.
        3. **Set granularity** — choose whether to analyze at daily, weekly, or monthly level.
           Select the appropriate aggregation method (sum for volume metrics, mean for rates).
        4. **Set the intervention date** — the date on which the intervention occurred.
           This splits the series into the pre-period (model training) and post-period (effect estimation).
        5. **Review assumption checks** — address any warnings before proceeding.
        6. **Run the analysis** and review the results.
        """
    )

with st.expander("How to interpret the results"):
    st.markdown(
        """
        **Actual vs. counterfactual**
        Shows the observed metric alongside what the model predicted it would have been without the
        intervention. A persistent gap after the intervention date indicates an effect.

        **Pointwise effect**
        The estimated effect at each individual time point in the post-period — observed minus
        counterfactual. Positive values indicate a lift; negative values indicate a drop.

        **Cumulative effect**
        The running total of the pointwise effect since the intervention. This is the most practical
        number for reporting: it tells you the total impact accumulated over the post-period.

        **Credible intervals**
        All estimates come with 95% credible intervals. If the interval excludes zero throughout the
        post-period, the effect is unlikely to be due to chance. If it crosses zero, treat the
        result with caution.

        **Plain-language summary**
        The interpretation block below the charts summarises the direction, magnitude, and
        statistical confidence of the effect in plain language.
        """
    )

# ── 1. Upload ──────────────────────────────────────────────────────────────────

raw_df = ingestion_ui.render_uploader()

if raw_df is None:
    st.info("Upload a CSV file to get started.")
    st.stop()

with st.expander("Preview raw data"):
    st.dataframe(raw_df.head(20), use_container_width=True)

# ── 2. Column mapping & settings ───────────────────────────────────────────────

st.divider()
mapping = ingestion_ui.render_column_mapping(raw_df)

if mapping is None:
    st.stop()

# ── 3. Ingest pipeline ─────────────────────────────────────────────────────────

try:
    df = loader.parse_dates(raw_df, mapping["date_col"])
except Exception as e:
    st.error(f"Failed to parse date column: {e}")
    st.stop()

all_metric_cols = [mapping["response_col"]] + (mapping["covariate_cols"] or [])

df = cleaner.drop_duplicate_dates(df)
df = cleaner.coerce_numeric(df, all_metric_cols)
df, gap_warnings = cleaner.interpolate_gaps(df, all_metric_cols)

for warning in gap_warnings:
    st.warning(warning)

df = wrangler.resample(df, mapping["granularity"], mapping["aggregation"])

# ── 4. Validation ──────────────────────────────────────────────────────────────

st.divider()
validation = validator.validate(
    df,
    response_col=mapping["response_col"],
    intervention_date=mapping["intervention_date"],
    covariate_cols=mapping["covariate_cols"],
)

for error in validation.errors:
    st.error(f"❌ {error}")

for warning in validation.warnings:
    st.warning(f"⚠️ {warning}")

if not validation.valid:
    st.stop()

# ── 5. Assumption checks ───────────────────────────────────────────────────────

st.divider()
pre_period, post_period = wrangler.split_periods(df, mapping["intervention_date"])
pre_series = df.loc[pre_period[0]:pre_period[1], mapping["response_col"]]

assumption_results = stationarity.run_all(pre_series, mapping["covariate_cols"])
can_proceed = assumption_panel.render(assumption_results)

if not can_proceed:
    st.stop()

# ── 6. Run analysis ────────────────────────────────────────────────────────────

st.divider()

if st.button("Run Causal Impact analysis", type="primary"):
    model_df = wrangler.shape_for_model(df, mapping["response_col"], mapping["covariate_cols"])

    with st.spinner("Fitting model…"):
        try:
            result = causal_impact.run(model_df, pre_period, post_period)
        except Exception as e:
            st.error(f"Model fitting failed: {e}")
            st.stop()

    st.session_state["ci_result"] = result

if "ci_result" in st.session_state:
    st.divider()
    results_panel.render(st.session_state["ci_result"])
