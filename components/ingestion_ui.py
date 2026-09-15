import pandas as pd
import streamlit as st

from core.ingestion.loader import load_csv, parse_dates
from core.ingestion.wrangler import GRANULARITY_MAP, AGGREGATION_MAP


def render_uploader(key_prefix: str = "") -> pd.DataFrame | None:
    """File upload widget. Returns a raw DataFrame or None if no file is uploaded."""
    uploaded_file = st.file_uploader("Upload a CSV file", type=["csv"], key=f"{key_prefix}file_uploader")
    if uploaded_file is None:
        return None
    try:
        return load_csv(uploaded_file)
    except ValueError as e:
        st.error(str(e))
        return None


def render_column_mapping(df: pd.DataFrame, key_prefix: str = "") -> dict | None:
    """
    Column mapping UI. Returns a dict with selected columns and settings,
    or None if the user has not completed the mapping.

    key_prefix namespaces the underlying widget keys so this component can be
    reused on multiple pages within the same Streamlit session without their
    selections bleeding into each other.
    """
    st.subheader("Column mapping")

    columns = list(df.columns)

    date_col = st.selectbox("Date column", options=columns, key=f"{key_prefix}date_col")
    remaining = [c for c in columns if c != date_col]

    if not remaining:
        st.error(
            "No columns are left to use as the response metric once the date column is excluded. "
            "Your CSV needs at least one numeric column besides the date."
        )
        return None

    response_col = st.selectbox(
        "Response column (metric to analyze)", options=remaining, key=f"{key_prefix}response_col"
    )
    remaining_after_response = [c for c in remaining if c != response_col]

    covariate_cols = st.multiselect(
        "Covariate columns (optional)",
        options=remaining_after_response,
        key=f"{key_prefix}covariate_cols",
        help="Control time series unaffected by the intervention. Improves counterfactual accuracy.",
    )

    st.subheader("Time settings")

    granularity = st.selectbox(
        "Granularity",
        options=list(GRANULARITY_MAP.keys()),
        key=f"{key_prefix}granularity",
        help="Aggregate the data to this time interval before analysis.",
    )

    aggregation = st.selectbox(
        "Aggregation",
        options=list(AGGREGATION_MAP.keys()),
        key=f"{key_prefix}aggregation",
        help="How to aggregate values when resampling. Use Sum for volume metrics, Mean for rates.",
    )

    try:
        parsed_df, _ = parse_dates(df, date_col)
        min_date = parsed_df.index.min().date()
        max_date = parsed_df.index.max().date()
    except Exception as e:
        st.error(f"Could not parse the selected date column: {e}")
        return None

    intervention_date = st.date_input(
        "Intervention date",
        value=min_date + (max_date - min_date) // 2,
        min_value=min_date,
        max_value=max_date,
        key=f"{key_prefix}intervention_date",
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


def render_did_column_mapping(df: pd.DataFrame, key_prefix: str = "") -> dict | None:
    """
    Column mapping UI for panel data (unit, time, group, outcome).
    Returns a dict with selected columns and settings, or None if the user
    has not completed the mapping.
    """
    st.subheader("Column mapping")

    columns = list(df.columns)

    time_col = st.selectbox("Date/period column", options=columns, key=f"{key_prefix}time_col")
    remaining = [c for c in columns if c != time_col]

    if not remaining:
        st.error("No columns are left once the date column is excluded. Your CSV needs group, outcome (and optionally unit) columns.")
        return None

    group_col = st.selectbox(
        "Group column (treated vs. control)", options=remaining, key=f"{key_prefix}group_col"
    )
    remaining_after_group = [c for c in remaining if c != group_col]

    if not remaining_after_group:
        st.error("No columns are left once the date and group columns are excluded. Your CSV needs an outcome column.")
        return None

    outcome_col = st.selectbox(
        "Outcome column (metric to analyze)", options=remaining_after_group, key=f"{key_prefix}outcome_col"
    )
    remaining_after_outcome = [c for c in remaining_after_group if c != outcome_col]

    unit_options = ["(none — each group is one aggregate series)"] + remaining_after_outcome
    unit_choice = st.selectbox(
        "Unit column (optional)",
        options=unit_options,
        key=f"{key_prefix}unit_col",
        help=(
            "Identifies individual units within each group (e.g. stores, regions). "
            "Enables cluster-robust standard errors. Leave unset if you only have one "
            "aggregate time series per group."
        ),
    )
    unit_col = None if unit_choice == unit_options[0] else unit_choice

    group_values = df[group_col].dropna().unique().tolist()
    if len(group_values) != 2:
        st.error(
            f"The group column must have exactly 2 distinct values (found {len(group_values)}: "
            f"{group_values})."
        )
        return None

    treated_label = st.selectbox(
        "Which value represents the treated group?", options=group_values, key=f"{key_prefix}treated_label"
    )

    st.subheader("Time settings")

    granularity = st.selectbox(
        "Granularity",
        options=list(GRANULARITY_MAP.keys()),
        key=f"{key_prefix}granularity",
        help="Aggregate the data to this time interval before analysis.",
    )

    aggregation = st.selectbox(
        "Aggregation",
        options=list(AGGREGATION_MAP.keys()),
        key=f"{key_prefix}aggregation",
        help="How to aggregate values when resampling. Use Sum for volume metrics, Mean for rates.",
    )

    try:
        parsed_df, _ = parse_dates(df, time_col)
        min_date = parsed_df.index.min().date()
        max_date = parsed_df.index.max().date()
    except Exception as e:
        st.error(f"Could not parse the selected date column: {e}")
        return None

    intervention_date = st.date_input(
        "Intervention date",
        value=min_date + (max_date - min_date) // 2,
        min_value=min_date,
        max_value=max_date,
        key=f"{key_prefix}intervention_date",
        help="The date on which the intervention occurred. Splits the series into pre and post periods.",
    )

    return {
        "time_col": time_col,
        "group_col": group_col,
        "outcome_col": outcome_col,
        "unit_col": unit_col,
        "treated_label": treated_label,
        "granularity": granularity,
        "aggregation": aggregation,
        "intervention_date": pd.Timestamp(intervention_date),
    }
