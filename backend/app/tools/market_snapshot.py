from pydantic import BaseModel, Field


class MarketSnapshotInput(BaseModel):
    symbol: str = Field(pattern=r"^[0-9]{6}$")


class MarketSnapshotOutput(BaseModel):
    summary: str
