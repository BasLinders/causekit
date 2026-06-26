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
