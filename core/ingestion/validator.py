import pandas as pd
from dataclasses import dataclass, field

from core.ingestion.wrangler import GRANULARITY_RANK

PRE_PERIOD_WARN_THRESHOLD = 28
POST_PERIOD_WARN_THRESHOLD = 7


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
    selected_granularity: str | None = None,
    native_granularity: str | None = None,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    # Response column
    if response_col not in df.columns:
        errors.append(f"Response column '{response_col}' not found in the data.")
    else:
        if not pd.api.types.is_numeric_dtype(df[response_col]):
            errors.append(f"Response column '{response_col}' must be numeric.")
        elif df[response_col].isnull().all():
            errors.append(f"Response column '{response_col}' contains only null values.")
        elif df[response_col].isnull().any():
            errors.append(
                f"Response column '{response_col}' still contains missing values after cleaning. "
                "This usually means a gap was too large to interpolate reliably."
            )

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

        post_period_points = (df.index >= intervention_date).sum()
        if post_period_points < POST_PERIOD_WARN_THRESHOLD:
            warnings.append(
                f"The post-period contains {post_period_points} data "
                f"point{'s' if post_period_points != 1 else ''}. "
                f"At least {POST_PERIOD_WARN_THRESHOLD} are recommended for a stable effect estimate."
            )

    # Covariate columns
    if covariate_cols:
        for col in covariate_cols:
            if col not in df.columns:
                errors.append(f"Covariate column '{col}' not found in the data.")
            else:
                if not pd.api.types.is_numeric_dtype(df[col]):
                    errors.append(f"Covariate column '{col}' must be numeric.")
                elif df[col].isnull().all():
                    errors.append(f"Covariate column '{col}' contains only null values.")
                elif df[col].isnull().any():
                    errors.append(
                        f"Covariate column '{col}' still contains missing values after cleaning. "
                        "This usually means a gap was too large to interpolate reliably."
                    )

    # Granularity vs. the data's native cadence
    if selected_granularity and native_granularity:
        selected_rank = GRANULARITY_RANK.get(selected_granularity)
        native_rank = GRANULARITY_RANK.get(native_granularity)
        if selected_rank is not None and native_rank is not None and selected_rank < native_rank:
            warnings.append(
                f"You selected '{selected_granularity}' granularity, but the data's native cadence "
                f"looks like '{native_granularity}'. Periods finer than the source data have to be "
                "fabricated and may distort results — consider matching the granularity to the data."
            )

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)
