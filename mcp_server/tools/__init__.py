"""Read-only MCP tool adapters."""

from mcp_server.tools.financial_query import financial_query
from mcp_server.tools.research_query import research_query
from mcp_server.tools.stock_query import stock_query

__all__ = ["financial_query", "research_query", "stock_query"]
