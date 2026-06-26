import pandas as pd

GRANULARITY_MAP = {
    "Daily": "D",
    "Weekly": "W-MON",
    "Monthly": "MS",
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
