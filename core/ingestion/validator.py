import pandas as pd
from dataclasses import dataclass, field

PRE_PERIOD_WARN_THRESHOLD = 28


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate(
    df: pd.DataFrame,
    response_col: str,
    intervention_date: pd.Timestamp,
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

    # Intervention date bounds
    if intervention_date <= df.index.min():
        errors.append("Intervention date must fall after the start of the time series.")
    elif intervention_date >= df.index.max():
        errors.append("Intervention date must fall before the end of the time series.")
    else:
        pre_period_points = (df.index < intervention_date).sum()
        if pre_period_points < PRE_PERIOD_WARN_THRESHOLD:
            warnings.append(
                f"The pre-period contains {pre_period_points} data "
                f"point{'s' if pre_period_points != 1 else ''}. "
                f"At least {PRE_PERIOD_WARN_THRESHOLD} are recommended (4 full weeks) "
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
