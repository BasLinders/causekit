import re

import pandas as pd
from io import StringIO

# Matches YYYY-MM-DD with -, / or . as separator (ISO order, unambiguous).
_ISO_PATTERN = re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}$")
# Matches DD-MM-YYYY with -, / or . as separator.
_DAY_FIRST_PATTERN = re.compile(r"^\d{1,2}[-/.]\d{1,2}[-/.]\d{4}$")


def load_csv(uploaded_file) -> pd.DataFrame:
    content = uploaded_file.read().decode("utf-8")
    return pd.read_csv(StringIO(content))


def parse_dates(df: pd.DataFrame, date_column: str) -> pd.DataFrame:
    df = df.copy()
    df[date_column] = _parse_date_series(df[date_column])
    df = df.set_index(date_column).sort_index()
    return df


def _parse_date_series(series: pd.Series) -> pd.Series:
    """
    Parse a date column that may be formatted as YYYY-MM-DD or DD-MM-YYYY,
    with -, / or . as the separator. The two formats can't be told apart
    value-by-value (e.g. 03-04-2024), so the format is inferred once from
    the whole column and applied consistently.
    """
    raw = series.astype(str).str.strip()
    non_null = raw[raw.str.lower() != "nan"]

    if non_null.empty:
        raise ValueError("Date column is empty.")

    is_iso = non_null.str.match(_ISO_PATTERN)
    is_day_first = non_null.str.match(_DAY_FIRST_PATTERN)

    if is_iso.all():
        dayfirst = False
    elif is_day_first.all():
        dayfirst = True
    elif (is_iso | is_day_first).all():
        raise ValueError(
            "Date column mixes YYYY-MM-DD and DD-MM-YYYY formats. "
            "Please use a single, consistent date format throughout the column."
        )
    else:
        raise ValueError(
            "Date column contains values that aren't in YYYY-MM-DD or DD-MM-YYYY format "
            "(separators -, / and . are all accepted)."
        )

    return pd.to_datetime(raw, dayfirst=dayfirst, errors="raise")
