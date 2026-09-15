import pandas as pd
from diff_diff import DifferenceInDifferences

from core.results.models import DiDResult

MIN_UNITS_PER_GROUP_FOR_CLUSTERING = 2


def run(panel: pd.DataFrame, alpha: float = 0.05) -> DiDResult:
    """
    Fit a canonical 2x2 DiD model on a panel shaped by wrangler.shape_for_did()
    (columns: unit, time, group, outcome, post).

    Cluster-robust standard errors (clustered by unit) are used when both groups
    contain more than one unit; otherwise clustering degenerates (as few as one
    cluster per group produces meaningless near-zero standard errors), so the
    estimator falls back to heteroskedasticity-robust standard errors instead —
    validator.validate_did() surfaces this as a warning before the run.
    """
    units_per_group = panel.groupby("group")["unit"].nunique()
    can_cluster = bool((units_per_group >= MIN_UNITS_PER_GROUP_FOR_CLUSTERING).all())

    did = DifferenceInDifferences(cluster="unit" if can_cluster else None, alpha=alpha)
    results = did.fit(panel, outcome="outcome", treatment="group", post="post")

    group_period_means = (
        panel.groupby(["group", "post"], as_index=False)["outcome"]
        .mean()
        .pivot(index="group", columns="post", values="outcome")
        .rename(index={0: "control", 1: "treated"}, columns={0: "pre", 1: "post"})
    )

    return DiDResult(
        att=results.att,
        se=results.se,
        conf_int=results.conf_int,
        p_value=results.p_value,
        clustered=can_cluster,
        group_period_means=group_period_means,
        summary=results.summary(),
        alpha=alpha,
    )
