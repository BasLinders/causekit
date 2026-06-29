import pandas as pd
from dataclasses import dataclass


@dataclass
class CausalImpactResult:
    inferences: pd.DataFrame   # Full inference DataFrame from tfcausalimpact
    observed: pd.Series        # Original response series
    pre_period: list           # [start, end] timestamps
    post_period: list          # [start, end] timestamps
    summary: str               # Tabular summary string
    report: str                # Plain-language report string
    alpha: float = 0.05
