import math
import re
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

ISO_DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", flags=re.ASCII)
StockSymbol = Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$", min_length=6, max_length=6)]


class ScoringEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: StockSymbol
    as_of_date: date
    metrics: dict[str, float | None] = Field(max_length=100)

    @field_validator("as_of_date", mode="before")
    @classmethod
    def require_iso_calendar_date_string(cls, value: Any) -> Any:
        if not isinstance(value, str) or ISO_DATE_PATTERN.fullmatch(value) is None:
            raise ValueError("as_of_date must be a YYYY-MM-DD date string")
        return value

    @field_validator("metrics", mode="before")
    @classmethod
    def require_strict_finite_metric_numbers(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        normalized: dict[str, float | None] = {}
        for key, metric_value in value.items():
            if metric_value is None:
                normalized[key] = None
            elif isinstance(metric_value, bool) or not isinstance(metric_value, (int, float)):
                raise ValueError("metric values must be JSON numbers or null")
            elif not math.isfinite(metric_value):
                raise ValueError("metric values must be finite")
            else:
                normalized[key] = float(metric_value)
        return normalized


class ScoringEvaluationResponse(BaseModel):
    status: Literal["ok", "insufficient_data"]
    coverage: float
    missing_core_dimensions: list[str]
    missing_metrics: list[str]
    result: dict[str, Any] | None
