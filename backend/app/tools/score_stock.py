from pydantic import BaseModel, Field


class ScoreStockInput(BaseModel):
    symbol: str = Field(pattern=r"^[0-9]{6}$")


class ScoreStockOutput(BaseModel):
    status: str
    coverage: float
