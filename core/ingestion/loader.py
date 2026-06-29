import pandas as pd
from io import StringIO


def load_csv(uploaded_file) -> pd.DataFrame:
    content = uploaded_file.read().decode("utf-8")
    return pd.read_csv(StringIO(content))


def parse_dates(df: pd.DataFrame, date_column: str) -> pd.DataFrame:
    df = df.copy()
    df[date_column] = pd.to_datetime(df[date_column])
    df = df.set_index(date_column).sort_index()
    return df
