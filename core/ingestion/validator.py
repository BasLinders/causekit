import pandas as pd
from dataclasses import dataclass, field
from diff_diff import validate_did_data

MIN_PRE_PERIODS_DID = 4

# Minimum recommended pre-period points per granularity, anchored to 4 weeks in days.
# Monthly uses 6 as a practical minimum — 1 month is insufficient for reliable BSTS fitting.
PRE_PERIOD_THRESHOLDS = {
    "Daily": 28,   # 4 weeks × 7 days
    "Weekly": 4,   # 4 weeks
    "Monthly": 6,  # 6 months
}

PRE_PERIOD_LABELS = {
    "Daily": "4 full weeks",
    "Weekly": "4 full weeks",
    "Monthly": "6 months",
}

PERIOD_UNIT = {
    "Daily": "day",
    "Weekly": "week",
    "Monthly": "month",
}


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate(
    df: pd.DataFrame,
    response_col: str,
    intervention_date: pd.Timestamp,
    selected_granularity: str = "Daily",
    native_granularity: str | None = None,
    covariate_cols: list[str] | None = None,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    # Response column
    if response_col not in df.columns:
        errors.append(f"Response column '{response_col}' not found in the data.")
    else:
        if not pd.api.types.is_numeric_dtype(df[response_col]):
            errors.append(f"Response column '{response_col}' must be numeric.")
        if df[response_col].isnull().all():
            errors.append(f"Response column '{response_col}' contains only null values.")

    # Granularity downsampling warning
    if native_granularity and selected_granularity != native_granularity:
        granularity_order = ["Daily", "Weekly", "Monthly"]
        if granularity_order.index(selected_granularity) < granularity_order.index(native_granularity):
            warnings.append(
                f"The selected granularity ({selected_granularity.lower()}) is finer than the "
                f"data's native cadence ({native_granularity.lower()}). This will introduce "
                "empty periods that are filled by interpolation."
            )

    # Intervention date bounds
    if intervention_date <= df.index.min():
        errors.append("Intervention date must fall after the start of the time series.")
    elif intervention_date >= df.index.max():
        errors.append("Intervention date must fall before the end of the time series.")
    else:
        pre_period_points = (df.index < intervention_date).sum()
        threshold = PRE_PERIOD_THRESHOLDS.get(selected_granularity, 28)
        label = PRE_PERIOD_LABELS.get(selected_granularity, "4 full weeks")
        unit = PERIOD_UNIT.get(selected_granularity, "day")

        if pre_period_points < threshold:
            warnings.append(
                f"The pre-period contains {pre_period_points} {unit}"
                f"{'s' if pre_period_points != 1 else ''}. "
                f"At least {threshold} are recommended ({label}) "
                "for a reliable counterfactual estimate."
            )

    # Covariate columns
    if covariate_cols:
        for col in covariate_cols:
            if col not in df.columns:
                errors.append(f"Covariate column '{col}' not found in the data.")
            else:
                if not pd.api.types.is_numeric_dtype(df[col]):
                    errors.append(f"Covariate column '{col}' must be numeric.")
                if df[col].isnull().all():
                    errors.append(f"Covariate column '{col}' contains only null values.")

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


def validate_did(panel: pd.DataFrame) -> ValidationResult:
    """
    Validate a panel shaped by wrangler.shape_for_did() (columns: unit, time,
    group, outcome, post). Delegates the core checks — both groups present and
    non-empty, both groups have pre- and post-period observations, the group
    column is binary — to diff_diff.validate_did_data(), which already
    implements them, and adds two causekit-specific checks on top.
    """
    errors: list[str] = []
    warnings: list[str] = []

    required_cols = {"unit", "time", "group", "outcome", "post"}
    missing_cols = required_cols - set(panel.columns)
    if missing_cols:
        errors.append(f"Missing required column(s): {', '.join(sorted(missing_cols))}.")
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    lib_result = validate_did_data(
        panel, outcome="outcome", treatment="group", time="post", unit="unit", raise_on_error=False
    )
    errors.extend(lib_result["errors"])
    warnings.extend(lib_result["warnings"])

    if errors:
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    pre_periods_per_group = panel.loc[panel["post"] == 0].groupby("group")["time"].nunique()
    if len(pre_periods_per_group) < 2 or (pre_periods_per_group < MIN_PRE_PERIODS_DID).any():
        warnings.append(
            f"At least one group has fewer than {MIN_PRE_PERIODS_DID} distinct pre-period time points. "
            "The pre-trends check may be unreliable with so little pre-period data."
        )

    units_per_group = panel.groupby("group")["unit"].nunique()
    if (units_per_group < 2).any():
        warnings.append(
            "At least one group contains only a single unit, so cluster-robust standard "
            "errors aren't meaningful. Heteroskedasticity-robust standard errors will be "
            "used instead."
        )

    return ValidationResult(valid=True, errors=errors, warnings=warnings)
