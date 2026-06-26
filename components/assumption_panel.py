import streamlit as st

from core.assumptions.stationarity import AssumptionResult


def render(results: list[AssumptionResult]) -> bool:
    """
    Render assumption check results. Returns True if no hard violations are present
    (warnings are allowed through), False if any hard violation blocks analysis.
    """
    st.subheader("Assumption checks")

    hard_violation = False

    for result in results:
        if result.passed:
            icon = "✅"
            fn = st.success
        elif result.is_warning:
            icon = "⚠️"
            fn = st.warning
        else:
            icon = "❌"
            fn = st.error
            hard_violation = True

        with fn(f"{icon} **{result.name}**"):
            st.write(result.message)
            if result.detail:
                st.caption(result.detail)

    return not hard_violation
