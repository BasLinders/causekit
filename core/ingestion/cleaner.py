import pandas as pd

LARGE_GAP_THRESHOLD = 3  # consecutive nulls before a warning is raised


def coerce_numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    df = df.copy()
    for col in columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def interpolate_gaps(
    df: pd.DataFrame,
    columns: list[str],
) -> tuple[pd.DataFrame, list[str]]:
    """
    Interpolate null gaps using time-based interpolation.
    Returns the cleaned DataFrame and a list of warnings for large gaps.
    """
    df = df.copy()
    warnings = []

    for col in columns:
        null_mask = df[col].isnull()
        if null_mask.any():
            consecutive_nulls = null_mask.groupby((~null_mask).cumsum()).transform("sum")
            if (consecutive_nulls > LARGE_GAP_THRESHOLD).any():
                warnings.append(
                    f"'{col}' contains gaps of more than {LARGE_GAP_THRESHOLD} consecutive missing points. "
                    "Time-based interpolation was applied but results in these regions may be unreliable."
                )
            df[col] = df[col].interpolate(method="time")

    return df, warnings


def drop_duplicate_dates(df: pd.DataFrame) -> pd.DataFrame:
    return df[~df.index.duplicated(keep="first")]


def enforce_regular_frequency(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """
    Reindex to a regular frequency so there are no implicit gaps.
    Missing rows introduced by reindexing are left as NaN for interpolation to handle.
    """
    full_index = pd.date_range(start=df.index.min(), end=df.index.max(), freq=freq)
    return df.reindex(full_index)
