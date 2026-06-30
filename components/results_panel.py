import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import streamlit as st

from core.results.models import CausalImpactResult

OBSERVED_COLOR = "#1f77b4"
COUNTERFACTUAL_COLOR = "#d62728"
EFFECT_COLOR = "#2ca02c"
INTERVENTION_COLOR = "#555555"
CI_ALPHA = 0.2


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


def _ci_label(alpha: float) -> str:
    return f"{round((1 - alpha) * 100)}% credible interval"


def _new_axes(figsize: tuple[float, float]):
    fig, ax = plt.subplots(figsize=figsize)
    return fig, ax


def _finish_axes(fig, ax, intervention_date) -> None:
    ax.axvline(
        intervention_date,
        color=INTERVENTION_COLOR,
        linestyle="--",
        linewidth=1.5,
        label="Intervention date",
    )
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    ax.legend(loc="upper left", frameon=False)
    fig.tight_layout()


def _render_actual_vs_predicted(result: CausalImpactResult) -> None:
    st.markdown("#### Actual vs. counterfactual")

    inferences = result.inferences
    intervention_date = result.post_period[0]

    fig, ax = _new_axes((10, 4.5))

    ax.plot(
        result.observed.index, result.observed,
        color=OBSERVED_COLOR, linewidth=1.6, label="Observed",
    )
    ax.plot(
        inferences.index, inferences["complete_preds_means"],
        color=COUNTERFACTUAL_COLOR, linewidth=1.6, linestyle="--", label="Counterfactual",
    )
    ax.fill_between(
        inferences.index,
        inferences["complete_preds_lower"],
        inferences["complete_preds_upper"],
        color=COUNTERFACTUAL_COLOR, alpha=CI_ALPHA, linewidth=0,
        label=_ci_label(result.alpha),
    )

    ax.set_ylabel("Value")
    _finish_axes(fig, ax, intervention_date)
    st.pyplot(fig)
    plt.close(fig)

    st.caption(
        f"Intervention occurred at {intervention_date.date()} (dashed grey line). "
        "The dashed red line is the model's counterfactual prediction, with its "
        "credible interval shaded; a persistent gap from the observed (blue) line "
        "after the intervention indicates an effect."
    )


def _render_pointwise_effect(result: CausalImpactResult) -> None:
    st.markdown("#### Pointwise effect")

    inferences = result.inferences
    intervention_date = result.post_period[0]
    post = inferences[inferences.index >= intervention_date]

    fig, ax = _new_axes((10, 3.5))

    ax.axhline(0, color="black", linewidth=0.9, alpha=0.6, label="No effect")
    ax.plot(post.index, post["point_effects_means"], color=EFFECT_COLOR, linewidth=1.6, label="Effect")
    ax.fill_between(
        post.index, post["point_effects_lower"], post["point_effects_upper"],
        color=EFFECT_COLOR, alpha=CI_ALPHA, linewidth=0,
        label=_ci_label(result.alpha),
    )

    ax.set_ylabel("Effect")
    _finish_axes(fig, ax, intervention_date)
    st.pyplot(fig)
    plt.close(fig)

    st.caption(
        "Estimated effect at each point in the post-period (observed minus counterfactual). "
        "If the shaded credible interval stays clear of the black zero line, the effect "
        "at that point is unlikely to be due to chance."
    )


def _render_cumulative_effect(result: CausalImpactResult) -> None:
    st.markdown("#### Cumulative effect")

    inferences = result.inferences
    intervention_date = result.post_period[0]
    post = inferences[inferences.index >= intervention_date]

    fig, ax = _new_axes((10, 3.5))

    ax.axhline(0, color="black", linewidth=0.9, alpha=0.6, label="No effect")
    ax.plot(
        post.index, post["post_cum_effects_means"],
        color=EFFECT_COLOR, linewidth=1.6, label="Cumulative effect",
    )
    ax.fill_between(
        post.index, post["post_cum_effects_lower"], post["post_cum_effects_upper"],
        color=EFFECT_COLOR, alpha=CI_ALPHA, linewidth=0,
        label=_ci_label(result.alpha),
    )

    ax.set_ylabel("Cumulative effect")
    _finish_axes(fig, ax, intervention_date)
    st.pyplot(fig)
    plt.close(fig)

    st.caption(
        "Running total of the estimated effect since the intervention — the most "
        "practical number for reporting total impact over the post-period."
    )


def _render_summary_table(summary: str) -> None:
    with st.expander("Statistical summary"):
        cleaned = "\n".join(
            line for line in summary.splitlines()
            if "print(impact.summary" not in line
        ).strip()
        st.markdown(f"```\n{cleaned}\n```")
