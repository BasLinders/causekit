import pandas as pd
import streamlit as st

from core.results.models import CausalImpactResult


def render(result: CausalImpactResult) -> None:
    st.subheader("Results")

    _render_report(result.report)
    _render_actual_vs_predicted(result.inferences, result.post_period)
    _render_pointwise_effect(result.inferences, result.post_period)
    _render_cumulative_effect(result.inferences, result.post_period)
    _render_summary_table(result.summary)


def _render_report(report: str) -> None:
    st.markdown("#### Interpretation")
    st.info(report)


def _render_actual_vs_predicted(inferences: pd.DataFrame, post_period: list) -> None:
    st.markdown("#### Actual vs. counterfactual")

    chart_data = pd.DataFrame({
        "Observed": inferences["observed"],
        "Counterfactual": inferences["predicted"],
        "Lower": inferences["predicted_lower"],
        "Upper": inferences["predicted_upper"],
    })

    st.line_chart(chart_data[["Observed", "Counterfactual"]])
    st.caption(
        "Shaded credible interval and counterfactual shown. "
        f"Intervention occurred at {post_period[0].date()}."
    )


def _render_pointwise_effect(inferences: pd.DataFrame, post_period: list) -> None:
    st.markdown("#### Pointwise effect")

    post_mask = inferences.index >= post_period[0]
    post = inferences[post_mask]

    chart_data = pd.DataFrame({
        "Effect": post["point_effect"],
        "Lower": post["point_effect_lower"],
        "Upper": post["point_effect_upper"],
    })

    st.line_chart(chart_data[["Effect"]])
    st.caption("Estimated effect at each point in the post-period (observed minus counterfactual).")


def _render_cumulative_effect(inferences: pd.DataFrame, post_period: list) -> None:
    st.markdown("#### Cumulative effect")

    post_mask = inferences.index >= post_period[0]
    post = inferences[post_mask]

    chart_data = pd.DataFrame({
        "Cumulative effect": post["cum_effect"],
        "Lower": post["cum_effect_lower"],
        "Upper": post["cum_effect_upper"],
    })

    st.line_chart(chart_data[["Cumulative effect"]])
    st.caption("Running total of the estimated effect since the intervention.")


def _render_summary_table(summary: str) -> None:
    with st.expander("Statistical summary"):
        st.text(summary)
