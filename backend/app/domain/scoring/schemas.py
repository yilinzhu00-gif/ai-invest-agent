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
    metrics: dict[str, Any] = Field(max_length=100)

    @field_validator("as_of_date", mode="before")
    @classmethod
    def require_iso_calendar_date_string(cls, value: Any) -> Any:
        if not isinstance(value, str) or ISO_DATE_PATTERN.fullmatch(value) is None:
            raise ValueError("as_of_date must be a YYYY-MM-DD date string")
        return value


class ScoringEvaluationResponse(BaseModel):
    status: Literal["ok", "insufficient_data"]
    coverage: float
    missing_core_dimensions: list[str]
    missing_metrics: list[str]
    result: dict[str, Any] | None
