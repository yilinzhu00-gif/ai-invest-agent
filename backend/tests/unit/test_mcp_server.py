from __future__ import annotations

import asyncio

from mcp_server.server import mcp


def test_mcp_registers_the_three_read_only_tools() -> None:
    assert set(mcp._tool_manager._tools) == {"stock_query", "financial_query", "research_query"}


def test_research_query_returns_partial_evidence_without_provider_network() -> None:
    result = asyncio.run(
        mcp._tool_manager.call_tool("research_query", {"query": "A 股", "limit": 1})
    )
    assert result["query"] == "A 股"
    assert result["evidence_required"] is True
    assert isinstance(result["as_of"], str)
    assert isinstance(result["errors"], list)
