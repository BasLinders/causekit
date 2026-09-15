"""
components/bq_ui.py

Streamlit UI for the BigQuery data source: OAuth sign-in, project/dataset
selection, and query building — an alternative to ingestion_ui's CSV
upload, feeding the same downstream ingestion pipeline (both return a raw
pandas DataFrame in the same shape a CSV upload would).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.ingestion.bq_client import (
    DEPS_AVAILABLE,
    autodetect_param_values,
    dry_run,
    exchange_code_for_credentials,
    get_auth_url,
    get_redirect_uri,
    is_authenticated,
    list_datasets,
    list_projects,
    run_query,
    sign_out,
)
from core.ingestion.bq_sql_builder import METRICS, build_grouped_timeseries, build_timeseries

_METRIC_LABELS = {
    "visitors": "Visitors",
    "conversions": "Conversions",
    "revenue": "Revenue",
    "transactions": "Transactions",
    "event_count": "Custom event count",
}


def _missing_deps_error() -> None:
    st.error(
        "BigQuery support requires the `google-cloud-bigquery`, `google-auth-oauthlib`, "
        "and `google-cloud-resourcemanager` packages — add them to `requirements.txt` "
        "and reinstall."
    )


# ---------------------------------------------------------------------------
# GCP credentials gate
# ---------------------------------------------------------------------------

def render_gcp_credentials_gate(page_path: str = "") -> bool:
    """
    Renders the GCP OAuth client id/secret entry (skipped once already set)
    and the Google sign-in panel. Handles the OAuth callback itself, since
    session state written before the redirect doesn't survive it (see
    core.ingestion.bq_client module docstring).

    Returns True once the session is fully authenticated and ready to proceed.
    """
    params = st.query_params
    if "code" in params and not is_authenticated():
        try:
            exchange_code_for_credentials(params["code"], params.get("state", ""))
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Authentication failed: {e}")

    st.subheader("GCP credentials")

    if is_authenticated():
        st.success("✓ GCP credentials connected", icon="🔑")
    else:
        try:
            redirect_uri = get_redirect_uri(page_path)
        except RuntimeError as e:
            st.error(str(e))
            return False
        st.caption(
            "Enter your own GCP OAuth client credentials. Create one at "
            "[console.cloud.google.com](https://console.cloud.google.com) under "
            "APIs & Services → Credentials → OAuth 2.0 Client IDs. "
            f"Add `{redirect_uri}` as an authorised redirect URI."
        )
        creds_set = bool(
            st.session_state.get("gcp_client_id") and st.session_state.get("gcp_client_secret")
        )
        with st.expander("🔑 Enter credentials", expanded=not creds_set):
            client_id = st.text_input(
                "Client ID",
                value=st.session_state.get("gcp_client_id", ""),
                placeholder="123456789-abc...apps.googleusercontent.com",
                key=f"{page_path}_gcp_client_id_input",
            )
            client_secret = st.text_input(
                "Client secret",
                value=st.session_state.get("gcp_client_secret", ""),
                type="password",
                key=f"{page_path}_gcp_client_secret_input",
            )
            if st.button("Save credentials", key=f"{page_path}_gcp_creds_save_btn"):
                if client_id and client_secret:
                    st.session_state["gcp_client_id"] = client_id
                    st.session_state["gcp_client_secret"] = client_secret
                    st.session_state.pop("credentials", None)
                    st.rerun()
                else:
                    st.warning("Both Client ID and Client secret are required.")

    if not st.session_state.get("gcp_client_id"):
        return False

    st.divider()
    return _render_auth_panel(page_path)


def _render_auth_panel(page_path: str) -> bool:
    client_id = st.session_state.get("gcp_client_id", "")
    client_secret = st.session_state.get("gcp_client_secret", "")

    if is_authenticated():
        col1, col2 = st.columns([4, 1])
        with col1:
            st.success("✓ Connected to Google")
        with col2:
            if st.button("Sign out", key=f"{page_path}_bq_sign_out", width="stretch"):
                sign_out()
                _clear_connection_caches(page_path)
                st.rerun()
        return True

    st.info(
        "Sign in with your Google account to access BigQuery. You'll be taken to Google "
        "in a new tab — after signing in, continue in that tab."
    )
    auth_url = get_auth_url(client_id, client_secret, page_path)
    st.link_button("🔐 Sign in with Google", auth_url, width="stretch", type="primary")
    return False


# ---------------------------------------------------------------------------
# Connection selectors
# ---------------------------------------------------------------------------

def _clear_connection_caches(key_prefix: str) -> None:
    """Drops cached project/dataset lists on sign-out, so signing in again
    (possibly as a different Google account) re-fetches rather than showing
    the previous account's now-stale/inaccessible projects and datasets."""
    stale_keys = [
        k for k in st.session_state
        if k == f"{key_prefix}_projects_cache" or k.startswith(f"{key_prefix}_datasets_")
    ]
    for k in stale_keys:
        del st.session_state[k]


def _render_connection_selectors(key_prefix: str) -> tuple[str | None, str | None]:
    st.subheader("BigQuery connection")

    projects_key = f"{key_prefix}_projects_cache"
    if projects_key not in st.session_state:
        with st.spinner("Loading projects…"):
            st.session_state[projects_key] = list_projects()
    projects: dict[str, str] = st.session_state[projects_key]
    if not projects:
        st.warning("No projects found for this account.")
        return None, None

    project_ids = list(projects.keys())
    project = st.selectbox(
        "Project",
        options=project_ids,
        format_func=lambda pid: f"{projects[pid]}  ({pid})" if projects[pid] else pid,
        key=f"{key_prefix}_selected_project",
        help="GCP project that owns the BigQuery dataset.",
    )

    datasets_key = f"{key_prefix}_datasets_{project}"
    if datasets_key not in st.session_state:
        with st.spinner(f"Loading datasets for {project}…"):
            st.session_state[datasets_key] = list_datasets(project)
    datasets: dict[str, str] = st.session_state[datasets_key]
    if not datasets:
        st.warning(f"No datasets found in {project}.")
        return project, None

    dataset_ids = list(datasets.keys())
    dataset = st.selectbox(
        "Dataset",
        options=dataset_ids,
        format_func=lambda did: f"{datasets[did]}  ({did})" if datasets[did] else did,
        key=f"{key_prefix}_selected_dataset",
        help="BigQuery dataset containing the GA4 events_* tables.",
    )

    return project, dataset


def _render_date_range(key_prefix: str) -> tuple[str, str]:
    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("Start date", key=f"{key_prefix}_bq_start_date")
    with col2:
        end = st.date_input("End date", key=f"{key_prefix}_bq_end_date")
    return str(start), str(end)


def _render_metric_picker(key_prefix: str) -> tuple[list[str], str, str | None]:
    metrics = st.multiselect(
        "Metrics",
        options=list(METRICS),
        default=["visitors", "conversions"],
        format_func=lambda m: _METRIC_LABELS[m],
        key=f"{key_prefix}_bq_metrics",
    )
    conversion_event = "purchase"
    if {"conversions", "transactions", "revenue"} & set(metrics):
        conversion_event = st.text_input(
            "Conversion event name", value="purchase", key=f"{key_prefix}_bq_conversion_event"
        )
    custom_event_name = None
    if "event_count" in metrics:
        custom_event_name = st.text_input("Custom event name", key=f"{key_prefix}_bq_custom_event")
    return metrics, conversion_event, custom_event_name


def _run_and_show_cost(key_prefix: str, project: str, sql: str) -> pd.DataFrame | None:
    with st.expander("View SQL"):
        st.code(sql, language="sql")

    cost = dry_run(project, sql)
    if cost["error"]:
        st.warning(f"Could not estimate query cost: {cost['error']}")
    else:
        st.info(f"Estimated scan: **{cost['display']}** ({cost['free_tier_pct']}% of the 1 TB monthly free tier)")

    result_key = f"{key_prefix}_bq_result"
    if st.button("Run query", key=f"{key_prefix}_bq_run_btn", type="primary"):
        with st.spinner("Running query…"):
            try:
                st.session_state[result_key] = run_query(project, sql)
            except Exception as e:
                st.error(f"Query failed: {e}")
                return None

    return st.session_state.get(result_key)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def render_bq_timeseries_export(page_path: str) -> pd.DataFrame | None:
    """Plain daily time series (date + metric columns) — for Causal Impact.
    Returns a DataFrame once the analyst runs a query, or None until then."""
    if not DEPS_AVAILABLE:
        _missing_deps_error()
        return None
    if not render_gcp_credentials_gate(page_path):
        return None

    project, dataset = _render_connection_selectors(page_path)
    if not project or not dataset:
        return None

    st.subheader("Query")
    start_date, end_date = _render_date_range(page_path)
    metrics, conversion_event, custom_event_name = _render_metric_picker(page_path)
    if not metrics:
        st.info("Select at least one metric.")
        return None

    try:
        sql = build_timeseries(
            project, dataset, start_date, end_date,
            metrics=metrics, conversion_event=conversion_event, custom_event_name=custom_event_name,
        )
    except ValueError as e:
        st.error(str(e))
        return None

    return _run_and_show_cost(page_path, project, sql)


def render_bq_grouped_export(page_path: str) -> pd.DataFrame | None:
    """Daily time series split by group (date + segment + metric columns) —
    for Difference-in-Differences. The 'segment' column is selected as the
    group column in the normal column-mapping step afterward."""
    if not DEPS_AVAILABLE:
        _missing_deps_error()
        return None
    if not render_gcp_credentials_gate(page_path):
        return None

    project, dataset = _render_connection_selectors(page_path)
    if not project or not dataset:
        return None

    st.subheader("Query")
    start_date, end_date = _render_date_range(page_path)
    metrics, conversion_event, custom_event_name = _render_metric_picker(page_path)
    if not metrics:
        st.info("Select at least one metric.")
        return None

    mode = st.radio(
        "Group source",
        options=["flat_column", "event_param"],
        format_func=lambda m: (
            "A built-in GA4 column (e.g. geo.country, device.category)"
            if m == "flat_column"
            else "An event-params value (feature flag / rollout)"
        ),
        key=f"{page_path}_bq_group_mode",
    )

    if mode == "flat_column":
        segment_col = st.text_input(
            "Column", placeholder="geo.country", key=f"{page_path}_bq_segment_col"
        )
        if not segment_col:
            st.info("Enter a column to split by.")
            return None
        try:
            sql = build_timeseries(
                project, dataset, start_date, end_date,
                metrics=metrics, conversion_event=conversion_event,
                custom_event_name=custom_event_name, segment_col=segment_col,
            )
        except ValueError as e:
            st.error(str(e))
            return None
    else:
        param_key = st.text_input(
            "event_params key", value="feature_flag", key=f"{page_path}_bq_param_key"
        )
        detected_key = f"{page_path}_bq_detected_values"
        if st.button("Auto-detect values", key=f"{page_path}_bq_autodetect_btn"):
            with st.spinner("Scanning a recent sample…"):
                st.session_state[detected_key] = autodetect_param_values(
                    project, dataset, start_date, end_date, param_key
                )
        detected = st.session_state.get(detected_key, [])
        manual = st.text_input(
            "Additional values (comma-separated, optional)", key=f"{page_path}_bq_manual_values"
        )
        manual_values = [v.strip() for v in manual.split(",") if v.strip()]
        options = sorted(set(detected) | set(manual_values))

        # Each multiselect's options exclude the other's current selection, so
        # a value can't end up picked for both — reading the *other* widget's
        # session_state value from before it re-renders this run, since only
        # one of the two can see the other's fresh selection within one run.
        prior_control_values = st.session_state.get(f"{page_path}_bq_control_values", [])
        treated_values = st.multiselect(
            "Value(s) meaning Treated",
            options=[o for o in options if o not in prior_control_values],
            key=f"{page_path}_bq_treated_values",
        )
        control_values = st.multiselect(
            "Value(s) meaning Control",
            options=[o for o in options if o not in treated_values],
            key=f"{page_path}_bq_control_values",
        )
        match_strategy = st.radio(
            "Match strategy", options=["exact", "like"], horizontal=True,
            key=f"{page_path}_bq_match_strategy",
        )

        if not treated_values or not control_values:
            st.info("Select at least one value for both Treated and Control.")
            return None

        try:
            sql = build_grouped_timeseries(
                project, dataset, start_date, end_date,
                param_key=param_key,
                group_labels={"Treated": treated_values, "Control": control_values},
                metrics=metrics, match_strategy=match_strategy,
                conversion_event=conversion_event, custom_event_name=custom_event_name,
            )
        except ValueError as e:
            st.error(str(e))
            return None

    return _run_and_show_cost(page_path, project, sql)
