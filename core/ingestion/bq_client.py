"""
core/ingestion/bq_client.py

Thin wrapper around google-cloud-bigquery and google-auth-oauthlib, used as
an alternative to CSV upload: each page (Causal Impact, Difference-in-
Differences) lets the analyst connect to BigQuery, pick a project/dataset,
and pull a query result straight into the same ingestion pipeline a CSV
upload feeds.

OAuth client credentials are entered by the analyst at runtime (stored only
in st.session_state, never written to disk) rather than pre-provisioned in
secrets — this tool is meant to be handed to any analyst on the team, each
using their own Google Cloud project. Only the redirect base URL comes from
st.secrets, since it's a deployment-level constant, not a per-analyst one.

Streamlit Cloud notes
----------------------
- When Google redirects back after OAuth, the browser navigates away and
  returns, breaking the WebSocket and starting a fresh Streamlit session.
  Session state written before the redirect is therefore NOT available on
  the callback. Fix: the OAuth client id/secret and which page started the
  flow are embedded in the `state` param (Google echoes it back verbatim),
  and the callback side reconstructs the Flow from that instead of relying
  on session state.
- Credentials ARE stored in session state once exchanged — they survive for
  the duration of the browser session (until the tab closes or the page is
  hard-refreshed), not persisted anywhere else.
"""

from __future__ import annotations

import base64
import json
import urllib.parse
from typing import Optional

import streamlit as st

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import Flow
    from google.cloud import bigquery
    from google.cloud import resourcemanager_v3
    import pandas as pd

    DEPS_AVAILABLE = True
except ImportError:
    DEPS_AVAILABLE = False


SCOPES = [
    "https://www.googleapis.com/auth/bigquery",
    "https://www.googleapis.com/auth/cloud-platform.read-only",
]

_FREE_TIER_BYTES = 1_000_000_000_000  # 1 TB


# ---------------------------------------------------------------------------
# OAuth config
# ---------------------------------------------------------------------------

def _get_redirect_base_url() -> str:
    """
    Read the app's base URL from secrets — must be a single string with no
    page path (get_redirect_uri appends the page path). Register each page's
    full URL (e.g. https://<app>.streamlit.app/causal_impact) as its own
    authorised redirect URI in the Google Cloud OAuth client.
    Expected: BQ_REDIRECT_URI = "https://<your-deployment>.streamlit.app"
    """
    try:
        base = st.secrets["BQ_REDIRECT_URI"]
    except Exception:
        raise RuntimeError(
            "BQ_REDIRECT_URI is not set in .streamlit/secrets.toml. Add "
            'BQ_REDIRECT_URI = "https://<your-deployment-url>" (no page path — '
            "it's appended automatically) before using the BigQuery data source."
        )
    if not isinstance(base, str):
        raise TypeError(
            "BQ_REDIRECT_URI in secrets must be a single string with no page path, "
            'e.g. BQ_REDIRECT_URI = "https://<your-deployment-url>" — '
            f"got {base!r}."
        )
    return base


def get_redirect_uri(page_path: str = "") -> str:
    """
    Build the OAuth redirect URI for a given page. Each Streamlit page needs
    its own redirect URI (e.g. .../causal_impact, .../diff_in_diff)
    registered as an authorised redirect URI in the Google Cloud OAuth
    client, so the callback lands back on the page that started the flow.
    """
    base = _get_redirect_base_url()
    if not page_path:
        return base
    return f"{base.rstrip('/')}/{page_path.strip('/')}"


def _build_client_config(client_id: str, client_secret: str, redirect_uri: str) -> dict:
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }


def get_auth_url(client_id: str, client_secret: str, page_path: str = "") -> str:
    redirect_uri = get_redirect_uri(page_path)
    config = _build_client_config(client_id, client_secret, redirect_uri)
    flow = Flow.from_client_config(config, scopes=SCOPES, redirect_uri=redirect_uri)

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    # verifier/client_id/client_secret/page_path all need to survive the
    # redirect, since it starts a fresh Streamlit session with none of this
    # in session state — see module docstring.
    verifier: str = getattr(flow, "code_verifier", None) or ""
    state_data = json.dumps({
        "verifier": verifier,
        "client_id": client_id,
        "client_secret": client_secret,
        "page_path": page_path,
    })
    encoded = base64.urlsafe_b64encode(state_data.encode()).decode().rstrip("=")

    parsed = urllib.parse.urlparse(auth_url)
    qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    qs["state"] = [encoded]
    new_query = urllib.parse.urlencode({k: v[0] for k, v in qs.items()})
    return urllib.parse.urlunparse(parsed._replace(query=new_query))


def exchange_code_for_credentials(code: str, state: str = "") -> Credentials:
    verifier: Optional[str] = None
    client_id = ""
    client_secret = ""
    page_path = ""
    if state:
        try:
            padding = 4 - len(state) % 4
            padded = state + ("=" * (padding % 4))
            state_data = json.loads(base64.urlsafe_b64decode(padded).decode())
            verifier = state_data.get("verifier") or None
            client_id = state_data.get("client_id", "")
            client_secret = state_data.get("client_secret", "")
            page_path = state_data.get("page_path", "")
        except Exception:
            verifier = None

    redirect_uri = get_redirect_uri(page_path)
    config = _build_client_config(client_id, client_secret, redirect_uri)

    flow = Flow.from_client_config(config, scopes=SCOPES, redirect_uri=redirect_uri)
    fetch_kwargs: dict = {"code": code}
    if verifier:
        fetch_kwargs["code_verifier"] = verifier
    flow.fetch_token(**fetch_kwargs)

    creds = flow.credentials
    st.session_state["gcp_client_id"] = client_id
    st.session_state["gcp_client_secret"] = client_secret
    st.session_state["credentials"] = _creds_to_dict(creds)
    return creds


def get_credentials() -> Optional[Credentials]:
    """Return valid credentials from session state, refreshing if expired."""
    creds_dict = st.session_state.get("credentials")
    if not creds_dict:
        return None
    creds = Credentials(
        token=creds_dict["token"],
        refresh_token=creds_dict.get("refresh_token"),
        token_uri=creds_dict.get("token_uri"),
        client_id=creds_dict.get("client_id"),
        client_secret=creds_dict.get("client_secret"),
        scopes=creds_dict.get("scopes"),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        st.session_state["credentials"] = _creds_to_dict(creds)
    return creds if creds.valid else None


def _creds_to_dict(creds: Credentials) -> dict:
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else [],
    }


def is_authenticated() -> bool:
    return get_credentials() is not None


def sign_out() -> None:
    st.session_state.pop("credentials", None)


# ---------------------------------------------------------------------------
# BQ client factory
# ---------------------------------------------------------------------------

def get_bq_client(project: Optional[str] = None) -> "bigquery.Client":
    creds = get_credentials()
    if not creds:
        raise RuntimeError("Not authenticated. Please sign in first.")
    return bigquery.Client(credentials=creds, project=project)


# ---------------------------------------------------------------------------
# Project / dataset discovery
# ---------------------------------------------------------------------------

def list_projects() -> dict[str, str]:
    """{project_id: display_name} for every GCP project accessible to the
    authenticated user. display_name may be empty for unnamed projects."""
    creds = get_credentials()
    if not creds:
        return {}
    try:
        client = resourcemanager_v3.ProjectsClient(credentials=creds)
        result = {p.project_id: p.display_name or "" for p in client.search_projects()}
        return dict(sorted(result.items()))
    except Exception as e:
        st.warning(f"Could not list projects: {e}")
        return {}


def list_datasets(project: str) -> dict[str, str]:
    """{dataset_id: friendly_name} for a project. friendly_name is commonly
    empty for GA4 export datasets."""
    try:
        client = get_bq_client(project)
        result = {d.dataset_id: d.friendly_name or "" for d in client.list_datasets()}
        return dict(sorted(result.items()))
    except Exception as e:
        st.warning(f"Could not list datasets in {project}: {e}")
        return {}


# ---------------------------------------------------------------------------
# Dry run — bytes scanned estimation
# ---------------------------------------------------------------------------

def dry_run(project: str, sql: str) -> dict:
    """Estimated bytes scanned via a BigQuery dry run — no rows returned,
    no cost incurred."""
    try:
        client = get_bq_client(project)
        job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        job = client.query(sql, job_config=job_config)
        bytes_processed = job.total_bytes_processed or 0
        gb = bytes_processed / 1e9
        return {
            "bytes": bytes_processed,
            "gb": round(gb, 2),
            "display": _format_bytes(bytes_processed),
            "free_tier_pct": round((gb / (_FREE_TIER_BYTES / 1e9)) * 100, 3),
            "error": None,
        }
    except Exception as e:
        return {"bytes": 0, "gb": 0.0, "display": "N/A", "free_tier_pct": 0.0, "error": str(e)}


def _format_bytes(n: int) -> str:
    if n < 1_000:
        return f"{n} B"
    if n < 1_000_000:
        return f"{n / 1_000:.1f} KB"
    if n < 1_000_000_000:
        return f"{n / 1_000_000:.1f} MB"
    return f"{n / 1_000_000_000:.2f} GB"


# ---------------------------------------------------------------------------
# Query execution
# ---------------------------------------------------------------------------

def run_query(project: str, sql: str) -> "pd.DataFrame":
    client = get_bq_client(project)
    return client.query(sql).result().to_dataframe()


def run_preview(project: str, sql: str, limit: int = 25) -> "pd.DataFrame":
    """Strips a trailing semicolon, appends LIMIT if not already present, runs
    the query. Only valid for pure SELECT queries."""
    clean = sql.rstrip().rstrip(";")
    last_line = clean.upper().rsplit("\n", 1)[-1]
    if "LIMIT" not in last_line:
        clean = clean + f"\nLIMIT {limit}"
    return run_query(project, clean)


# ---------------------------------------------------------------------------
# Auto-detect — distinct values of an event-params key
# ---------------------------------------------------------------------------
# Samples a short recent window rather than the full date range: which
# distinct values a param key holds is stable over the course of a rollout,
# so scanning the whole range buys no extra accuracy, only extra cost.

def autodetect_param_values(project: str, dataset: str, start_date: str, end_date: str, param_key: str) -> list[str]:
    from datetime import datetime, timedelta
    from core.ingestion.bq_sql_builder import build_autodetect_param_values_query

    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    start_dt = max(end_dt - timedelta(days=2), datetime.strptime(start_date, "%Y-%m-%d"))
    sample_start, sample_end = start_dt.strftime("%Y-%m-%d"), end_date

    sql = build_autodetect_param_values_query(project, dataset, sample_start, sample_end, param_key)
    cost = dry_run(project, sql)
    st.caption(
        f"Auto-detect scanned {sample_start} → {sample_end}: **{cost['display']}** — "
        "separate from your export query cost."
    )
    df = run_query(project, sql)
    return df["value"].tolist() if not df.empty else []
