"""General web-search tool with a keyless DuckDuckGo provider."""

from __future__ import annotations

import asyncio
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.tools.stock_tool import StockDataUnavailableError, _request_json


class SearchDataUnavailableError(RuntimeError):
    """The search provider returned no usable response."""


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        return value.strip()


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    summary: str = ""
    url: str
    source: str = "DuckDuckGo"


class SearchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    results: list[SearchResult] = Field(default_factory=list, max_length=50)
    source: str = "DuckDuckGo Instant Answer API"
    as_of: datetime


class SearchProvider(Protocol):
    async def search(self, payload: SearchInput) -> SearchOutput: ...


def _search_url(query: str) -> str:
    params = urllib.parse.urlencode({"q": query, "format": "json", "no_html": 1, "no_redirect": 1, "skip_disambig": 1})
    return f"https://api.duckduckgo.com/?{params}"


def _flatten_topics(topics: list[Any], output: list[SearchResult], limit: int) -> None:
    for topic in topics:
        if len(output) >= limit:
            return
        if not isinstance(topic, dict):
            continue
        if topic.get("Topics"):
            _flatten_topics(topic["Topics"], output, limit)
            continue
        text = topic.get("Text")
        url = topic.get("FirstURL")
        if text and url:
            title, _, summary = str(text).partition(" - ")
            output.append(SearchResult(title=title, summary=summary or str(text), url=str(url)))


class DuckDuckGoProvider:
    async def search(self, payload: SearchInput) -> SearchOutput:
        try:
            response = await asyncio.to_thread(_request_json, _search_url(payload.query))
        except StockDataUnavailableError as error:
            raise SearchDataUnavailableError("search_data_unavailable") from error
        results: list[SearchResult] = []
        abstract = response.get("AbstractText")
        abstract_url = response.get("AbstractURL")
        heading = response.get("Heading") or payload.query
        if abstract and abstract_url:
            results.append(SearchResult(title=str(heading), summary=str(abstract), url=str(abstract_url)))
        _flatten_topics(response.get("RelatedTopics") or [], results, payload.limit)
        return SearchOutput(query=payload.query, results=results[: payload.limit], as_of=datetime.now(UTC))


_provider: SearchProvider = DuckDuckGoProvider()


def get_search_provider() -> SearchProvider:
    return _provider


async def search_tool(payload: SearchInput) -> SearchOutput:
    return await get_search_provider().search(payload)


async def search_web(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    result = await search_tool(SearchInput(query=query, limit=limit))
    return [item.model_dump(mode="json") for item in result.results]
