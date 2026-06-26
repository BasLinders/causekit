import pandas as pd
import streamlit as st

from core.ingestion.loader import load_csv, parse_dates
from core.ingestion.wrangler import GRANULARITY_MAP, AGGREGATION_MAP


def render_uploader() -> pd.DataFrame | None:
    """File upload widget. Returns a raw DataFrame or None if no file is uploaded."""
    uploaded_file = st.file_uploader("Upload a CSV file", type=["csv"])
    if uploaded_file is None:
        return None
    return load_csv(uploaded_file)


def render_column_mapping(df: pd.DataFrame) -> dict | None:
    """
    Column mapping UI. Returns a dict with selected columns and settings,
    or None if the user has not completed the mapping.
    """
    st.subheader("Column mapping")

    columns = list(df.columns)

    date_col = st.selectbox("Date column", options=columns, key="date_col")
    remaining = [c for c in columns if c != date_col]

    response_col = st.selectbox("Response column (metric to analyze)", options=remaining, key="response_col")
    remaining_after_response = [c for c in remaining if c != response_col]

    covariate_cols = st.multiselect(
        "Covariate columns (optional)",
        options=remaining_after_response,
        key="covariate_cols",
        help="Control time series unaffected by the intervention. Improves counterfactual accuracy.",
    )

    st.subheader("Time settings")

    granularity = st.selectbox(
        "Granularity",
        options=list(GRANULARITY_MAP.keys()),
        key="granularity",
        help="Aggregate the data to this time interval before analysis.",
    )

    aggregation = st.selectbox(
        "Aggregation",
        options=list(AGGREGATION_MAP.keys()),
        key="aggregation",
        help="How to aggregate values when resampling. Use Sum for volume metrics, Mean for rates.",
    )

    try:
        parsed_df = parse_dates(df, date_col)
        min_date = parsed_df.index.min().date()
        max_date = parsed_df.index.max().date()
    except Exception:
        st.error("Could not parse the selected date column. Ensure it contains valid dates.")
        return None

    intervention_date = st.date_input(
        "Intervention date",
        value=min_date + (max_date - min_date) // 2,
        min_value=min_date,
        max_value=max_date,
        key="intervention_date",
        help="The date on which the intervention occurred. Splits the series into pre and post periods.",
    )

    return {
        "date_col": date_col,
        "response_col": response_col,
        "covariate_cols": covariate_cols or None,
        "granularity": granularity,
        "aggregation": aggregation,
        "intervention_date": pd.Timestamp(intervention_date),
    }
