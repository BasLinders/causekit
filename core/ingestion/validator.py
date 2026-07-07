import pandas as pd
from dataclasses import dataclass, field

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
