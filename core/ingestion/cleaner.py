import pandas as pd

from core.ingestion.wrangler import GRANULARITY_MAP

LARGE_GAP_THRESHOLD = 3  # consecutive nulls before a warning is raised


def coerce_numeric(df: pd.DataFrame, columns: list[str]) -> tuple[pd.DataFrame, dict[str, int]]:
    """
    Returns the coerced DataFrame and a dict of {column: count} for values that
    were non-null before coercion but became null after (i.e. couldn't be parsed
    as numbers), so callers can warn instead of silently losing data.
    """
    df = df.copy()
    coerced_counts: dict[str, int] = {}

    for col in columns:
        was_non_null = df[col].notna()
        converted = pd.to_numeric(df[col], errors="coerce")
        newly_null = (was_non_null & converted.isna()).sum()
        if newly_null:
            coerced_counts[col] = int(newly_null)
        df[col] = converted

    return df, coerced_counts


def drop_duplicate_dates(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    deduped = df[~df.index.duplicated(keep="first")]
    return deduped, len(df) - len(deduped)


def infer_native_granularity(df: pd.DataFrame) -> str:
    """
    Infer the data's native cadence from the median gap between consecutive
    index entries, expressed as one of the wrangler granularity labels.
    """
    if len(df.index) < 2:
        return "Daily"

    median_gap_days = df.index.to_series().diff().dropna().dt.days.median()

    if median_gap_days <= 1.5:
        return "Daily"
    elif median_gap_days <= 10:
        return "Weekly"
    else:
        return "Monthly"


def enforce_regular_frequency(df: pd.DataFrame, granularity: str) -> tuple[pd.DataFrame, int]:
    """
    Reindex to a regular frequency so there are no implicit gaps — a date
    that's simply missing from the source file (vs. present with a null value)
    would otherwise bypass interpolate_gaps entirely, since that function only
    fills nulls in rows that exist. Missing rows introduced by reindexing are
    left as NaN for interpolate_gaps to handle next.

    Returns the reindexed DataFrame and the number of rows that were synthesized.
    """
    freq = GRANULARITY_MAP[granularity]
    full_index = pd.date_range(start=df.index.min(), end=df.index.max(), freq=freq)
    reindexed = df.reindex(full_index)
    return reindexed, len(reindexed) - len(df)


def interpolate_gaps(
    df: pd.DataFrame,
    columns: list[str],
) -> tuple[pd.DataFrame, list[str]]:
    """
    Interpolate null gaps using time-based interpolation. Leading/trailing nulls
    (no anchor point on one side) are filled from the nearest available value so
    they don't reach the model as raw NaNs.
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
            df[col] = df[col].interpolate(method="time", limit_direction="both")

    return df, warnings
