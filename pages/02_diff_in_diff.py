import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import streamlit as st

from components import assumption_panel, ingestion_ui, results_panel
from core.assumptions import parallel_trends
from core.ingestion import cleaner, loader, validator, wrangler
from core.methods import diff_in_diff

st.set_page_config(page_title="Difference-in-Differences", layout="wide")
st.title("Difference-in-Differences")
st.caption(
    "Compare a treated and control group observed before and after an intervention."
)


def _compute_signature(raw_df: pd.DataFrame, mapping: dict) -> str:
    """
    Identifies the data + settings that produced a result, so stale results
    from a previous file/mapping aren't shown alongside changed inputs.
    """
    df_hash = pd.util.hash_pandas_object(raw_df, index=True).sum()
    mapping_repr = repr(sorted(mapping.items(), key=lambda kv: kv[0]))
    return hashlib.sha256(f"{df_hash}|{mapping_repr}".encode()).hexdigest()


# ── Documentation ──────────────────────────────────────────────────────────────

with st.expander("Data requirements"):
    st.markdown(
        """
        Your CSV must contain at least three columns:

        | Column | Type | Description |
        |---|---|---|
        | Date | date / datetime | One row per unit-period observation. Supported formats: `YYYY-MM-DD` or `DD-MM-YYYY`, with `-`, `/` or `.` as separator. The whole column must use one consistent format. |
        | Group | text / categorical | Exactly two distinct values — which group (treated or control) each row belongs to. |
        | Outcome | numeric | The metric you want to analyze (e.g. conversions, revenue, sessions). |
        | Unit *(optional)* | text / categorical | Identifies individual units within each group (e.g. stores, regions). Enables cluster-robust standard errors. Leave unset if you only have one aggregate time series per group. |

        The column names themselves do not matter — you will map them in the interface.
        At least 4 distinct pre-period time points per group are recommended for a reliable
        parallel-trends check.
        """
    )
    st.markdown("**SQL template (BigQuery)**")
    st.code(
        """
SELECT
    DATE(event_date)      AS date,
    region                AS "group",
    store_id               AS unit,
    SUM(metric)            AS outcome
FROM `project.dataset.table`
WHERE event_date BETWEEN '2024-01-01' AND '2024-06-30'
GROUP BY date, region, store_id
ORDER BY date
        """,
        language="sql",
    )

with st.expander("What it does"):
    st.markdown(
        """
        Difference-in-Differences compares the change in a metric for a **treated** group against
        the change for a **control** group over the same before/after window. The control group's
        change stands in for what would have happened to the treated group without the intervention —
        the **counterfactual**.

        The effect estimate (the Average Treatment effect on the Treated, or **ATT**) is the
        difference between the treated group's actual change and the control group's change.

        This only works if the two groups would have moved in parallel absent the intervention —
        the **parallel trends** assumption, checked against the pre-period before any analysis runs.
        """
    )

with st.expander("How to use"):
    st.markdown(
        """
        1. **Upload** a CSV file containing panel data — one row per unit-period observation.
        2. **Map columns** — select the date, group, outcome, and (optionally) unit columns,
           and which value of the group column is the treated group.
        3. **Set granularity** — choose whether to analyze at daily, weekly, or monthly level.
        4. **Set the intervention date** — the date on which the intervention occurred.
           This splits the series into the pre-period and post-period.
        5. **Review assumption checks** — address the parallel-trends warning before proceeding.
        6. **Run the analysis** and review the results.
        """
    )

with st.expander("How to interpret the results"):
    st.markdown(
        """
        **Pre-period trends**
        Treated and control group means over the pre-period. Roughly parallel lines support the
        parallel trends assumption; diverging lines mean the effect estimate below may be biased.

        **The 2×2 comparison**
        The classic DiD diagram: treated and control group means at pre and post, plus a
        counterfactual line projecting the treated group's pre-period level forward using the
        control group's change. The gap between the counterfactual and the treated group's actual
        post-period value is the effect estimate.

        **Effect estimate (ATT)**
        The estimated causal effect of the intervention on the treated group, with a confidence
        interval. If the interval excludes zero, the effect is unlikely to be due to chance.

        **Plain-language summary**
        The interpretation block below the charts summarises the direction, magnitude, and
        statistical confidence of the effect in plain language.
        """
    )

# ── 1. Upload ──────────────────────────────────────────────────────────────────

raw_df = ingestion_ui.render_uploader(key_prefix="did_")

if raw_df is None:
    st.info("Upload a CSV file to get started.")
    st.stop()

with st.expander("Preview raw data"):
    st.dataframe(raw_df.head(20), width="stretch")

# ── 2. Column mapping & settings ───────────────────────────────────────────────

st.divider()
mapping = ingestion_ui.render_did_column_mapping(raw_df, key_prefix="did_")

if mapping is None:
    st.stop()

current_signature = _compute_signature(raw_df, mapping)

# ── 3. Ingest pipeline ─────────────────────────────────────────────────────────

try:
    df, dropped_date_rows = loader.parse_dates(raw_df, mapping["time_col"])
except Exception as e:
    st.error(f"Failed to parse date column: {e}")
    st.stop()

if dropped_date_rows:
    st.warning(
        f"Dropped {dropped_date_rows} row{'s' if dropped_date_rows != 1 else ''} with a blank or "
        "unparseable date."
    )

# Duplicate-date and gap-filling steps are skipped here (unlike Causal Impact):
# multiple rows legitimately share a date across different units in panel data,
# and shape_for_did() resamples each unit's series independently below.
df, coerced_counts = cleaner.coerce_numeric(df, [mapping["outcome_col"]])
for col, count in coerced_counts.items():
    st.warning(
        f"'{col}' had {count} value{'s' if count != 1 else ''} that couldn't be read as a number "
        "and were treated as missing."
    )

# ── 4. Wrangle & validate ──────────────────────────────────────────────────────

st.divider()

try:
    panel = wrangler.shape_for_did(
        df,
        group_col=mapping["group_col"],
        outcome_col=mapping["outcome_col"],
        treated_label=mapping["treated_label"],
        intervention_date=mapping["intervention_date"],
        granularity=mapping["granularity"],
        aggregation=mapping["aggregation"],
        unit_col=mapping["unit_col"],
    )
except Exception as e:
    st.error(f"Failed to build the panel dataset: {e}")
    st.stop()

validation = validator.validate_did(panel)

for error in validation.errors:
    st.error(f"❌ {error}")

for warning in validation.warnings:
    st.warning(f"⚠️ {warning}")

if not validation.valid:
    st.stop()

# ── 5. Assumption checks ───────────────────────────────────────────────────────

st.divider()
assumption_results = parallel_trends.run_all(panel)
can_proceed = assumption_panel.render(assumption_results)

if not can_proceed:
    st.stop()

# ── 6. Run analysis ────────────────────────────────────────────────────────────

st.divider()

if st.button("Run Difference-in-Differences analysis", type="primary"):
    with st.spinner("Fitting model…"):
        try:
            result = diff_in_diff.run(panel)
        except Exception as e:
            st.error(f"Model fitting failed: {e}")
            st.stop()

    st.session_state["did_result"] = result
    st.session_state["did_panel"] = panel
    st.session_state["did_signature"] = current_signature

if "did_result" in st.session_state:
    st.divider()
    if st.session_state.get("did_signature") == current_signature:
        results_panel.render_did(st.session_state["did_result"], st.session_state["did_panel"])
    else:
        st.info(
            "Data or settings changed since the last run — click "
            "'Run Difference-in-Differences analysis' to refresh the results."
        )
