"""News provider seam; implementations must return source-attributed items."""

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class NewsItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    url: str
    published_at: datetime
    source: str = Field(min_length=1)


class NewsService(Protocol):
    async def search(self, query: str, *, limit: int = 10) -> list[NewsItem]: ...

