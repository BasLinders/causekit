import pandas as pd
from dataclasses import dataclass
from statsmodels.tsa.stattools import adfuller

STATIONARITY_ALPHA = 0.05
MIN_POINTS_FOR_ADF = 8


@dataclass
class AssumptionResult:
    name: str
    passed: bool
    is_warning: bool  # If True: surface as warning. If False: hard violation.
    message: str
    detail: str | None = None


def check_stationarity(pre_period_series: pd.Series) -> AssumptionResult:
    """
    ADF test on the pre-period response series.
    Non-stationarity is a warning, not a hard blocker — the BSTS model can handle
    some degree of non-stationarity, but it degrades counterfactual reliability.
    """
    series = pre_period_series.dropna()

    if len(series) < MIN_POINTS_FOR_ADF or series.nunique() <= 1:
        return AssumptionResult(
            name="Stationarity",
            passed=False,
            is_warning=True,
            message=(
                "Could not run the stationarity test — the pre-period is too short or "
                "has no variation. Proceed with caution; the counterfactual may be unreliable."
            ),
        )

    try:
        result = adfuller(series, autolag="AIC")
    except Exception as e:
        return AssumptionResult(
            name="Stationarity",
            passed=False,
            is_warning=True,
            message=(
                f"Could not run the stationarity test ({e}). "
                "Proceed with caution; the counterfactual may be unreliable."
            ),
        )

    p_value = result[1]
    passed = p_value < STATIONARITY_ALPHA

    if passed:
        message = "The pre-period series is stationary. No issues detected."
    else:
        message = (
            f"The pre-period series may be non-stationary (p = {p_value:.3f}). "
            "This can reduce the reliability of the counterfactual. "
            "Consider differencing the metric or adding covariates that capture the trend."
        )

    return AssumptionResult(
        name="Stationarity",
        passed=passed,
        is_warning=True,
        message=message,
        detail=f"ADF statistic: {result[0]:.4f} | p-value: {p_value:.4f} | Lags used: {result[2]}",
    )


def check_covariate_exogeneity(covariate_cols: list[str]) -> AssumptionResult:
    """
    Static reminder that covariates must be unaffected by the intervention.
    This cannot be tested automatically and is always surfaced when covariates are present.
    """
    col_list = ", ".join(f"'{c}'" for c in covariate_cols)
    return AssumptionResult(
        name="Covariate exogeneity",
        passed=False,
        is_warning=True,
        message=(
            f"Verify that {col_list} were not affected by the intervention. "
            "Covariates that were impacted will bias the counterfactual. "
            "This cannot be checked automatically."
        ),
    )


def run_all(
    pre_period_series: pd.Series,
    covariate_cols: list[str] | None = None,
) -> list[AssumptionResult]:
    results = [check_stationarity(pre_period_series)]
    if covariate_cols:
        results.append(check_covariate_exogeneity(covariate_cols))
    return results
