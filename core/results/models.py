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


@dataclass
class DiDResult:
    att: float                     # Effect estimate (group:post coefficient)
    se: float                      # Standard error
    conf_int: tuple[float, float]
    p_value: float
    clustered: bool                # Whether cluster-robust (vs. heteroskedasticity-robust) SE were used
    group_period_means: pd.DataFrame  # 2x2 table: index treated/control, columns pre/post
    summary: str                   # Tabular summary string from diff_diff
    alpha: float = 0.05

    @property
    def report(self) -> str:
        direction = "an increase" if self.att > 0 else "a decrease"
        significance = (
            "statistically significant"
            if self.p_value < self.alpha
            else "not statistically significant"
        )
        ci_label = f"{round((1 - self.alpha) * 100)}%"
        return (
            f"The estimated effect (ATT) is {self.att:,.2f} — {direction} in the treated group "
            f"relative to the counterfactual implied by the control group. This effect is "
            f"{significance} (p = {self.p_value:.3f}), with a {ci_label} confidence interval "
            f"of [{self.conf_int[0]:,.2f}, {self.conf_int[1]:,.2f}]."
        )
