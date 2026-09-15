"""
core/ingestion/bq_sql_builder.py

Builds BigQuery SQL against a GA4 events_* export for the two shapes
causekit's ingestion pipeline needs:

  * build_timeseries()          — date [+ flat segment] + metrics, for
                                   Causal Impact (no segment) and geo/device-
                                   split DiD (segment_col = a flat GA4 struct
                                   column, e.g. 'geo.country', 'device.category').
  * build_grouped_timeseries()  — date + group + metrics, where group comes
                                   from classifying users by an event_params
                                   value (e.g. a feature-flag/rollout param) —
                                   for DiD where the treated/control split
                                   isn't a built-in GA4 dimension.

Structurally these mirror _build_baseline_daily / build_binomial from
first-order-engine's and hexkit's SQL builders, generalized for arbitrary
metric sets and (for the grouped case) an arbitrary event-params split
instead of a fixed experiment-variant shape.
"""

from __future__ import annotations

import re

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")

METRICS = ("visitors", "conversions", "revenue", "transactions", "event_count")


def _table_ref(project: str, dataset: str) -> str:
    return f"`{project}.{dataset}.events_*`"


def _suffix_filter(start: str, end: str, alias: str = "") -> str:
    col = f"{alias}._TABLE_SUFFIX" if alias else "_TABLE_SUFFIX"
    return (
        f"{col} BETWEEN FORMAT_DATE('%Y%m%d', PARSE_DATE('%Y-%m-%d', '{_esc(start)}'))\n"
        f"    AND FORMAT_DATE('%Y%m%d', PARSE_DATE('%Y-%m-%d', '{_esc(end)}'))"
    )


def _esc(value: str) -> str:
    """Escapes a value for interpolation inside a single-quoted SQL string literal."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def validate_identifier(value: str, field_name: str = "identifier") -> str:
    """
    Restricts a caller-supplied column reference to safe dotted-identifier
    characters (letters, digits, underscores, dots) before it's interpolated
    into SQL directly (not as a string literal, so it can't be escaped the
    normal way) — e.g. a segment_col value like 'device.category'.
    """
    if not _IDENTIFIER_RE.match(value):
        raise ValueError(
            f"{field_name} must be a plain dotted column reference (letters, digits, "
            f"underscores, dots only) — got {value!r}."
        )
    return value


def _metric_columns(metrics: list[str], conversion_event: str, custom_event_name: str | None) -> list[str]:
    cols = []
    if "visitors" in metrics:
        cols.append("  COUNT(DISTINCT main.user_pseudo_id) AS visitors")
    if "conversions" in metrics:
        cols.append(
            f"  COUNT(DISTINCT CASE WHEN main.event_name = '{_esc(conversion_event)}' "
            f"THEN main.user_pseudo_id END) AS conversions"
        )
    if "transactions" in metrics:
        cols.append(
            "  COUNT(DISTINCT CASE WHEN main.event_name = 'purchase' "
            "THEN main.ecommerce.transaction_id END) AS transactions"
        )
    if "revenue" in metrics:
        cols.append(
            "  SUM(CASE WHEN main.event_name = 'purchase' "
            "THEN main.ecommerce.purchase_revenue ELSE 0 END) AS revenue"
        )
    if "event_count" in metrics:
        if not custom_event_name:
            raise ValueError("custom_event_name is required when 'event_count' is in metrics.")
        cols.append(
            f"  COUNT(DISTINCT CASE WHEN main.event_name = '{_esc(custom_event_name)}' "
            f"THEN main.user_pseudo_id END) AS event_count"
        )
    if not cols:
        raise ValueError(f"metrics must include at least one of {METRICS}.")
    return cols


def build_timeseries(
    project: str,
    dataset: str,
    start_date: str,
    end_date: str,
    metrics: list[str],
    conversion_event: str = "purchase",
    custom_event_name: str | None = None,
    segment_col: str | None = None,
) -> str:
    """Daily date [+ segment] + metrics. segment_col, if given, must be a flat
    GA4 struct column (e.g. 'geo.country', 'device.category') — for an
    event-params-based split (a feature-flag/rollout param), use
    build_grouped_timeseries() instead."""
    table = _table_ref(project, dataset)
    suffix = _suffix_filter(start_date, end_date)

    segment_select, group_extra, order_extra = "", "", ""
    if segment_col:
        segment_expr = validate_identifier(segment_col, field_name="segment_col")
        segment_select = f"  main.{segment_expr} AS segment,\n"
        group_extra, order_extra = ", segment", ", segment"

    select_block = ",\n".join(_metric_columns(metrics, conversion_event, custom_event_name))

    return f"""-- Time-series export (daily)
DECLARE start_date STRING DEFAULT '{_esc(start_date)}';
DECLARE end_date   STRING DEFAULT '{_esc(end_date)}';

SELECT
  PARSE_DATE('%Y%m%d', main.event_date) AS date,
{segment_select}{select_block}
FROM {table} AS main
WHERE main.{suffix}
GROUP BY date{group_extra}
ORDER BY date{order_extra};
"""


def build_grouped_timeseries(
    project: str,
    dataset: str,
    start_date: str,
    end_date: str,
    param_key: str,
    group_labels: dict[str, list[str]],
    metrics: list[str],
    match_strategy: str = "exact",
    conversion_event: str = "purchase",
    custom_event_name: str | None = None,
) -> str:
    """
    Daily date + group + metrics, where group is derived by classifying each
    user's first-seen value of an event_params key (param_key) against
    group_labels ({label: [raw_param_values]}), e.g. {"Treated": ["flag_on"],
    "Control": ["flag_off", "flag_off_v2"]} for a feature-flag/rollout split
    that isn't a built-in GA4 dimension. Each label may list more than one
    raw value (e.g. two flag variants that both count as "Treated").

    match_strategy: 'exact' (param value equals a raw value exactly) or
    'like' (param value contains a raw value as a substring).
    """
    if match_strategy not in ("exact", "like"):
        raise ValueError("match_strategy must be 'exact' or 'like'.")
    if not group_labels or not any(group_labels.values()):
        raise ValueError("group_labels must have at least one label with at least one raw value.")

    table = _table_ref(project, dataset)
    suffix = _suffix_filter(start_date, end_date)

    case_lines = []
    for label, raw_values in group_labels.items():
        for raw_value in raw_values:
            if match_strategy == "exact":
                case_lines.append(f"      WHEN raw_value = '{_esc(raw_value)}' THEN '{_esc(label)}'")
            else:
                # STRPOS is a plain substring search, not LIKE pattern
                # matching — a raw_value containing '%' or '_' is matched
                # literally instead of those being interpreted as wildcards.
                case_lines.append(f"      WHEN STRPOS(raw_value, '{_esc(raw_value)}') > 0 THEN '{_esc(label)}'")
    case_block = "\n".join(case_lines)

    select_block = ",\n".join(_metric_columns(metrics, conversion_event, custom_event_name))

    return f"""-- Time-series export (daily, grouped by event-params value)
DECLARE start_date STRING DEFAULT '{_esc(start_date)}';
DECLARE end_date   STRING DEFAULT '{_esc(end_date)}';

WITH user_group AS (
  SELECT
    user_pseudo_id,
    CASE
{case_block}
      ELSE NULL
    END AS segment
  FROM (
    SELECT
      user_pseudo_id,
      params.value.string_value AS raw_value,
      ROW_NUMBER() OVER (PARTITION BY user_pseudo_id ORDER BY event_timestamp ASC) AS rn
    FROM {table}, UNNEST(event_params) AS params
    WHERE {suffix}
      AND params.key = '{_esc(param_key)}'
      AND params.value.string_value IS NOT NULL
  )
  WHERE rn = 1
)

SELECT
  PARSE_DATE('%Y%m%d', main.event_date) AS date,
  user_group.segment AS segment,
{select_block}
FROM {table} AS main
INNER JOIN user_group ON main.user_pseudo_id = user_group.user_pseudo_id
WHERE main.{suffix}
  AND user_group.segment IS NOT NULL
GROUP BY date, segment
ORDER BY date, segment;
"""


def build_autodetect_param_values_query(project: str, dataset: str, start_date: str, end_date: str, param_key: str) -> str:
    """Distinct string values seen for an event_params key, most frequent
    first — feeds the UI's auto-detect for building group_labels."""
    table = _table_ref(project, dataset)
    suffix = _suffix_filter(start_date, end_date)
    return f"""-- Auto-detect: distinct event_params values for '{_esc(param_key)}'
SELECT
  params.value.string_value AS value,
  COUNT(*) AS occurrences
FROM {table}, UNNEST(event_params) AS params
WHERE {suffix}
  AND params.key = '{_esc(param_key)}'
  AND params.value.string_value IS NOT NULL
GROUP BY value
ORDER BY occurrences DESC
LIMIT 50;
"""
