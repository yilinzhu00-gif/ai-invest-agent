"""Source-attributed news search over a public RSS endpoint."""

from __future__ import annotations

import asyncio
import html
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NewsDataUnavailableError(RuntimeError):
    """The news provider returned no usable response."""


class NewsSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        return value.strip()


class NewsItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    summary: str = ""
    source: str = Field(min_length=1)
    date: datetime
    url: str


class NewsSearchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    items: list[NewsItem] = Field(default_factory=list, max_length=50)
    source: str = "Google News RSS"
    as_of: datetime


class NewsProvider(Protocol):
    async def search(self, payload: NewsSearchInput) -> NewsSearchOutput: ...


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value or ""))).strip()


def _fetch_rss(query: str) -> bytes:
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"})
    request = urllib.request.Request(url, headers={"User-Agent": "ai-investment-copilot/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read()
    except Exception as error:
        raise NewsDataUnavailableError("news_data_unavailable") from error


def _parse_rss(body: bytes, limit: int) -> list[NewsItem]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as error:
        raise NewsDataUnavailableError("news_data_schema_changed") from error
    items: list[NewsItem] = []
    for element in root.findall(".//item")[:limit]:
        title = _clean(element.findtext("title"))
        link = _clean(element.findtext("link"))
        description = _clean(element.findtext("description"))
        source = _clean(element.findtext("source")) or "Google News"
        published = _clean(element.findtext("pubDate"))
        try:
            date = parsedate_to_datetime(published).astimezone(UTC) if published else datetime.now(UTC)
        except (TypeError, ValueError, IndexError):
            date = datetime.now(UTC)
        if title and link:
            items.append(NewsItem(title=title, summary=description, source=source, date=date, url=link))
    return items


class GoogleNewsProvider:
    async def search(self, payload: NewsSearchInput) -> NewsSearchOutput:
        body = await asyncio.to_thread(_fetch_rss, payload.query)
        return NewsSearchOutput(
            query=payload.query,
            items=_parse_rss(body, payload.limit),
            as_of=datetime.now(UTC),
        )


_provider: NewsProvider = GoogleNewsProvider()


def get_news_provider() -> NewsProvider:
    return _provider


async def news_tool(payload: NewsSearchInput) -> NewsSearchOutput:
    return await get_news_provider().search(payload)


async def search_news(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """Search news, returning the requested ``title/summary/source/date`` fields."""
    result = await news_tool(NewsSearchInput(query=query, limit=limit))
    return [item.model_dump(mode="json", exclude={"url"}) for item in result.items]
