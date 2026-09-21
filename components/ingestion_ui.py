import pandas as pd
import streamlit as st

from core.ingestion.loader import load_csv, parse_dates
from core.ingestion.wrangler import GRANULARITY_MAP, AGGREGATION_MAP, suggest_control_units


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


def render_control_suggestion(df: pd.DataFrame, key_prefix: str = "") -> pd.DataFrame:
    """
    Optional pre-step for panel data with many candidate units and no group
    column yet: pick the treated unit(s), rank the rest by pre-period trend
    similarity (diff_diff.rank_control_units()), and let the analyst confirm
    which to use as control. Adds a 'did_group' column to a filtered copy of
    df for the analyst to select in render_did_column_mapping() below.

    Returns df unchanged unless the analyst completes and applies this step.
    """
    ranked_key = f"{key_prefix}suggest_ranked"
    ranked_signature_key = f"{key_prefix}suggest_ranked_signature"
    applied_key = f"{key_prefix}suggested_df"
    applied_signature_key = f"{key_prefix}suggested_df_signature"

    df_signature = pd.util.hash_pandas_object(df, index=True).sum()

    with st.expander("Don't have a control group yet? Suggest one"):
        st.caption(
            "Pick the treated unit(s) — candidate control units are ranked by how closely "
            "their pre-period trend matches the treated unit(s)."
        )

        columns = list(df.columns)
        date_col = st.selectbox("Date column", options=columns, key=f"{key_prefix}suggest_date_col")
        remaining = [c for c in columns if c != date_col]
        if not remaining:
            return df

        unit_col = st.selectbox("Unit column", options=remaining, key=f"{key_prefix}suggest_unit_col")
        remaining_after_unit = [c for c in remaining if c != unit_col]
        if not remaining_after_unit:
            return df

        outcome_col = st.selectbox(
            "Outcome column", options=remaining_after_unit, key=f"{key_prefix}suggest_outcome_col"
        )

        try:
            parsed_df, _ = parse_dates(df, date_col)
        except Exception as e:
            st.error(f"Could not parse the selected date column: {e}")
            return df

        unit_values = sorted(parsed_df[unit_col].dropna().unique().tolist(), key=str)
        treated_units = st.multiselect(
            "Treated unit(s)", options=unit_values, key=f"{key_prefix}suggest_treated_units"
        )

        min_date = parsed_df.index.min().date()
        max_date = parsed_df.index.max().date()
        as_of_date = st.date_input(
            "Approximate intervention date (for ranking only — confirm the exact date below)",
            value=min_date + (max_date - min_date) // 2,
            min_value=min_date,
            max_value=max_date,
            key=f"{key_prefix}suggest_intervention_date",
        )

        if not treated_units:
            st.info("Select at least one treated unit to rank candidate controls.")
            return df

        current_ranking_signature = (df_signature, unit_col, outcome_col, tuple(sorted(map(str, treated_units))), as_of_date)

        if st.button("Rank candidate controls", key=f"{key_prefix}suggest_rank_button"):
            try:
                st.session_state[ranked_key] = suggest_control_units(
                    parsed_df,
                    unit_col=unit_col,
                    outcome_col=outcome_col,
                    treated_units=treated_units,
                    intervention_date=pd.Timestamp(as_of_date),
                )
                st.session_state[ranked_signature_key] = current_ranking_signature
            except Exception as e:
                st.error(f"Could not rank control units: {e}")
                return df

        ranked = st.session_state.get(ranked_key)
        if ranked is None:
            return df

        if st.session_state.get(ranked_signature_key) != current_ranking_signature:
            st.info(
                "Inputs changed since this ranking was computed — click 'Rank candidate "
                "controls' again to refresh it."
            )
            return df

        st.dataframe(ranked, width="stretch")

        selected_controls = st.multiselect(
            "Confirm control units to use",
            options=ranked["unit"].tolist(),
            default=ranked["unit"].tolist(),
            key=f"{key_prefix}suggest_selected_controls",
        )

        if st.button("Use as my group column", key=f"{key_prefix}suggest_apply_button", disabled=not selected_controls):
            selected_units = set(treated_units) | set(selected_controls)
            augmented = df[df[unit_col].isin(selected_units)].copy()
            augmented["did_group"] = augmented[unit_col].apply(
                lambda u: "Treated" if u in treated_units else "Control"
            )
            st.session_state[applied_key] = augmented
            st.session_state[applied_signature_key] = df_signature
            st.success(
                f"Group column added: {len(treated_units)} treated unit(s), "
                f"{len(selected_controls)} control unit(s). Select 'did_group' as the group "
                "column below, and consider setting the unit column too for cluster-robust "
                "standard errors."
            )

    if st.session_state.get(applied_signature_key) == df_signature:
        return st.session_state.get(applied_key, df)
    return df
