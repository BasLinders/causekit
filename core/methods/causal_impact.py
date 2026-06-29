import pandas as pd
from causalimpact import CausalImpact

from core.results.models import CausalImpactResult


def run(
    df: pd.DataFrame,
    pre_period: list,
    post_period: list,
    alpha: float = 0.05,
) -> CausalImpactResult:
    """
    Fit a CausalImpact model on the prepared DataFrame.

    df must be datetime-indexed with the response column first
    and any covariates in subsequent columns — use wrangler.shape_for_model()
    to prepare the input.
    """
    ci = CausalImpact(df, pre_period, post_period, alpha=alpha)

    return CausalImpactResult(
        inferences=ci.inferences,
        observed=df.iloc[:, 0],
        pre_period=pre_period,
        post_period=post_period,
        summary=ci.summary(),
        report=ci.summary(output="report"),
        alpha=alpha,
    )
