import streamlit as st

st.set_page_config(page_title="Causekit", layout="wide")

st.title("Causekit")
st.caption("Causal inference toolkit for CRO teams.")

st.markdown(
    """
    Causekit makes it possible to analyze the impact of interventions that couldn't be randomized —
    launches, rollouts, policy changes, and other real-world events where an A/B test wasn't feasible.

    Select a method from the sidebar to get started.
    """
)

st.divider()

st.markdown("#### Available methods")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**Causal Impact**")
    st.caption("Estimate the effect of an intervention on a time series metric without a control group.")

    st.markdown("**Difference-in-Differences**")
    st.caption("Compare a treated and control group across a before/after period (ROADMAPPED).")

    st.markdown("**Propensity Score Matching**")
    st.caption("Construct comparable groups from observational data to reduce selection bias (ROADMAPPED).")

with col2:
    st.markdown("**Regression Discontinuity**")
    st.caption("Estimate effects at a hard assignment threshold (ROADMAPPED).")

    st.markdown("**Synthetic Control**")
    st.caption("Build a weighted counterfactual from donor units when a single unit is treated (ROADMAPPED).")

    st.markdown("**Mediation Analysis**")
    st.caption("Decompose a total effect into direct and indirect paths through a mediator (ROADMAPPED).")
