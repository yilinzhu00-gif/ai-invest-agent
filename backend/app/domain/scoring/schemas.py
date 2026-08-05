from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

StockSymbol = Annotated[str, StringConstraints(pattern=r"^\d{6}$", min_length=6, max_length=6)]


class ScoringEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: StockSymbol
    as_of_date: date
    metrics: dict[str, Any] = Field(max_length=100)


class ScoringEvaluationResponse(BaseModel):
    status: Literal["ok", "insufficient_data"]
    coverage: float
    missing_core_dimensions: list[str]
    missing_metrics: list[str]
    result: dict[str, Any] | None
