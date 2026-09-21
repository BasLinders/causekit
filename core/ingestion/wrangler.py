import pandas as pd
from diff_diff import rank_control_units

GRANULARITY_MAP = {
    "Daily": "D",
    "Weekly": "W-MON",
    "Monthly": "MS",
}

# Lower rank = finer-grained. Used to detect when a user requests a granularity
# finer than the data's native cadence, which would require fabricating data.
GRANULARITY_RANK = {
    "Daily": 0,
    "Weekly": 1,
    "Monthly": 2,
}

AGGREGATION_MAP = {
    "Sum": "sum",
    "Mean": "mean",
}


def resample(
    df: pd.DataFrame,
    granularity: str,
    aggregation: str = "Sum",
) -> pd.DataFrame:
    freq = GRANULARITY_MAP[granularity]
    agg = AGGREGATION_MAP[aggregation]
    return df.resample(freq).agg(agg)


def split_periods(
    df: pd.DataFrame,
    intervention_date: pd.Timestamp,
) -> tuple[list, list]:
    """
    Derive pre and post period bounds aligned to the resampled index.
    The intervention date is aligned to the nearest index entry on or after it.
    """
    pre_index = df.index[df.index < intervention_date]
    post_index = df.index[df.index >= intervention_date]

    pre_period = [pre_index[0], pre_index[-1]]
    post_period = [post_index[0], post_index[-1]]

    return pre_period, post_period


def shape_for_model(
    df: pd.DataFrame,
    response_col: str,
    covariate_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Place response column first, covariates after — required by tfcausalimpact."""
    cols = [response_col] + (covariate_cols or [])
    return df[cols]


def shape_for_did(
    df: pd.DataFrame,
    group_col: str,
    outcome_col: str,
    treated_label,
    intervention_date: pd.Timestamp,
    granularity: str,
    aggregation: str = "Sum",
    unit_col: str | None = None,
) -> pd.DataFrame:
    """
    Reshape date-indexed long-format data (as produced by loader.parse_dates)
    into the panel structure the DiD estimator expects: one row per unit-period
    with columns unit, time, group (0/1 treated), outcome, post (0/1).

    If unit_col is omitted, each group is treated as a single aggregate unit
    (e.g. two summed time series, treated vs. control) — validate_did() will
    warn that cluster-robust standard errors aren't meaningful in that case.
    """
    cols = [group_col, outcome_col] + ([unit_col] if unit_col else [])
    working = df[cols].rename(columns={group_col: "group", outcome_col: "outcome"})
    working["unit"] = working[unit_col] if unit_col else working["group"]
    working["group"] = (working["group"] == treated_label).astype(int)

    parts = []
    for unit, unit_df in working.groupby("unit"):
        group_value = unit_df["group"].iloc[0]
        resampled = resample(unit_df[["outcome"]], granularity, aggregation)
        resampled["unit"] = unit
        resampled["group"] = group_value
        parts.append(resampled)

    panel = pd.concat(parts).rename_axis("time").reset_index()
    panel["post"] = (panel["time"] >= intervention_date).astype(int)

    return panel[["unit", "time", "group", "outcome", "post"]].sort_values(["unit", "time"]).reset_index(drop=True)


def suggest_control_units(
    df: pd.DataFrame,
    unit_col: str,
    outcome_col: str,
    treated_units: list,
    intervention_date: pd.Timestamp,
    n_top: int | None = None,
) -> pd.DataFrame:
    """
    Rank candidate control units by pre-treatment outcome-trend similarity to
    the given treated unit(s), for when the analyst hasn't already settled on
    a control group. df must be date-indexed (as produced by loader.parse_dates).
    Thin wrapper around diff_diff.rank_control_units() — pre_periods are the
    index entries before intervention_date.
    """
    working = df[[unit_col, outcome_col]].rename(columns={outcome_col: "outcome"}).reset_index(names="time")
    pre_periods = working.loc[working["time"] < intervention_date, "time"].unique().tolist()

    return rank_control_units(
        working,
        unit_column=unit_col,
        time_column="time",
        outcome_column="outcome",
        treated_units=treated_units,
        pre_periods=pre_periods,
        n_top=n_top,
    )
