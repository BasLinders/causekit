import pandas as pd
import streamlit as st

from core.results.models import CausalImpactResult


def render(result: CausalImpactResult) -> None:
    st.subheader("Results")

    _render_report(result.report)
    _render_actual_vs_predicted(result)
    _render_pointwise_effect(result)
    _render_cumulative_effect(result)
    _render_summary_table(result.summary)


def _render_report(report: str) -> None:
    st.markdown("#### Interpretation")
    st.info(report)


def _render_actual_vs_predicted(result: CausalImpactResult) -> None:
    st.markdown("#### Actual vs. counterfactual")

    chart_data = pd.DataFrame({
        "Observed": result.observed,
        "Counterfactual": result.inferences["complete_preds_means"],
    })

    st.line_chart(chart_data)
    st.caption(
        f"Intervention occurred at {result.post_period[0].date()}."
    )


def _render_pointwise_effect(result: CausalImpactResult) -> None:
    st.markdown("#### Pointwise effect")

    post_mask = result.inferences.index >= result.post_period[0]
    post = result.inferences[post_mask]

    chart_data = pd.DataFrame({
        "Effect": post["point_effects_means"],
    })

    st.line_chart(chart_data)
    st.caption("Estimated effect at each point in the post-period (observed minus counterfactual).")


def _render_cumulative_effect(result: CausalImpactResult) -> None:
    st.markdown("#### Cumulative effect")

    post_mask = result.inferences.index >= result.post_period[0]
    post = result.inferences[post_mask]

    chart_data = pd.DataFrame({
        "Cumulative effect": post["post_cum_effects_means"],
    })

    st.line_chart(chart_data)
    st.caption("Running total of the estimated effect since the intervention.")


def _render_summary_table(summary: str) -> None:
    with st.expander("Statistical summary"):
        st.text(summary)
