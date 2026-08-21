"""Evidence-oriented MCP adapter for a lightweight research query."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from backend.app.tools.news_tool import NewsDataUnavailableError, search_news
from backend.app.tools.search_tool import SearchDataUnavailableError, search_web


async def research_query(query: str, limit: int = 10) -> dict[str, Any]:
    """Search public web and news sources and return a source-attributed bundle.

    This is a retrieval tool, not an investment recommendation. Each result
    retains its URL/source and the response includes an ``as_of`` timestamp.
    Provider failures are reported in ``errors`` while successful sources are
    still returned, so callers can distinguish partial evidence from an empty
    answer.
    """

    normalized = query.strip()
    if not normalized:
        raise ValueError("query must not be empty")
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")

    gathered = await asyncio.gather(
        search_web(normalized, limit=limit),
        search_news(normalized, limit=limit),
        return_exceptions=True,
    )
    web_result: list[dict[str, Any]] | BaseException = gathered[0]
    news_result: list[dict[str, Any]] | BaseException = gathered[1]
    errors: list[dict[str, str]] = []
    web: list[dict[str, Any]] = []
    news: list[dict[str, Any]] = []
    if isinstance(web_result, BaseException):
        if isinstance(web_result, asyncio.CancelledError):
            raise web_result
        code = "search_data_unavailable" if isinstance(web_result, SearchDataUnavailableError) else "search_error"
        errors.append({"source": "web", "code": code})
    else:
        web = web_result
    if isinstance(news_result, BaseException):
        if isinstance(news_result, asyncio.CancelledError):
            raise news_result
        code = "news_data_unavailable" if isinstance(news_result, NewsDataUnavailableError) else "news_error"
        errors.append({"source": "news", "code": code})
    else:
        news = news_result

    return {
        "query": normalized,
        "web": web,
        "news": news,
        "errors": errors,
        "evidence_required": True,
        "as_of": datetime.now(UTC).isoformat(),
    }
