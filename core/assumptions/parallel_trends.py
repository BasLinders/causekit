import pandas as pd
from diff_diff import check_parallel_trends

from core.assumptions.stationarity import AssumptionResult


def check_parallel_pre_trends(panel: pd.DataFrame) -> AssumptionResult:
    """
    Pre-trend test: thin wrapper around diff_diff.check_parallel_trends(),
    restricted to the pre-period. Flags if treated/control trends diverged
    significantly before treatment — a warning, not a hard blocker, since
    the analyst may still have reasons to proceed (e.g. a known one-off shock).
    """
    # check_parallel_trends() computes slopes via plain numpy arithmetic on the
    # time column, which breaks on datetimes (squaring a timedelta isn't
    # defined) — pass it an ordinal step index instead of raw timestamps.
    periods = sorted(panel["time"].unique())
    period_ordinal = {period: i for i, period in enumerate(periods)}
    working = panel.assign(time_ordinal=panel["time"].map(period_ordinal))

    pre_periods = sorted(working.loc[working["post"] == 0, "time_ordinal"].unique())

    if len(pre_periods) < 2:
        return AssumptionResult(
            name="Parallel trends",
            passed=False,
            is_warning=True,
            message=(
                "Could not run the parallel-trends test — at least two distinct "
                "pre-period time points are required. Proceed with caution."
            ),
        )

    result = check_parallel_trends(
        working, outcome="outcome", time="time_ordinal", treatment_group="group", pre_periods=pre_periods
    )

    p_value = result["p_value"]
    plausible = result["parallel_trends_plausible"]

    if plausible is None:
        return AssumptionResult(
            name="Parallel trends",
            passed=False,
            is_warning=True,
            message=(
                "Could not run the parallel-trends test — one of the groups has no "
                "variation in the pre-period. Proceed with caution."
            ),
        )

    if plausible:
        message = (
            "Treated and control groups show no statistically significant difference "
            "in pre-period trends. Parallel trends is plausible."
        )
    else:
        message = (
            f"Treated and control pre-period trends differ significantly (p = {p_value:.3f}). "
            "The parallel trends assumption may be violated, which would bias the effect "
            "estimate. Consider a longer pre-period, a different control group, or a method "
            "that doesn't rely on parallel trends."
        )

    return AssumptionResult(
        name="Parallel trends",
        passed=bool(plausible),
        is_warning=True,
        message=message,
        detail=(
            f"Treated trend: {result['treated_trend']:.4f} | Control trend: {result['control_trend']:.4f} | "
            f"Difference: {result['trend_difference']:.4f} | p-value: {p_value:.4f}"
        ),
    )


def pre_trend_series(panel: pd.DataFrame) -> pd.DataFrame:
    """
    Group-mean outcome by period for the pre-treatment window, for the UI to
    plot treated-vs-control pre-period trends side by side.
    """
    pre = panel.loc[panel["post"] == 0]
    return (
        pre.groupby(["time", "group"], as_index=False)["outcome"]
        .mean()
        .sort_values(["group", "time"])
        .reset_index(drop=True)
    )


def run_all(panel: pd.DataFrame) -> list[AssumptionResult]:
    return [check_parallel_pre_trends(panel)]
