"""FastMCP entrypoint exposing the investment system's read-only tools.

Run locally over stdio (the default) with ``python -m mcp_server``. For a
connector that supports HTTP MCP, use ``--transport streamable-http``.
"""

from __future__ import annotations

import argparse
import os
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from mcp_server.tools.financial_query import financial_query as _financial_query
from mcp_server.tools.research_query import research_query as _research_query
from mcp_server.tools.stock_query import (
    StockInterval,
    StockRange,
)
from mcp_server.tools.stock_query import (
    stock_query as _stock_query,
)

mcp = FastMCP(
    name="investment-research",
    instructions=(
        "Read-only public investment research tools. Results include source and "
        "timestamp fields; do not treat retrieved data as financial advice."
    ),
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "8000")),
    stateless_http=True,
)


@mcp.tool(
    name="stock_query",
    description="Query a public stock quote and bounded price history for a ticker.",
    structured_output=True,
)
async def stock_query(
    symbol: Annotated[str, Field(min_length=1, max_length=16)],
    range: StockRange = "1mo",
    interval: StockInterval = "1d",
) -> dict[str, object]:
    return await _stock_query(symbol=symbol, range=range, interval=interval)


@mcp.tool(
    name="financial_query",
    description="Query the latest public annual or quarterly financial report for a ticker.",
    structured_output=True,
)
async def financial_query(
    symbol: Annotated[str, Field(min_length=1, max_length=16)],
    period: Literal["annual", "quarterly"] = "annual",
) -> dict[str, object]:
    return await _financial_query(symbol=symbol, period=period)


@mcp.tool(
    name="research_query",
    description="Retrieve source-attributed public web and news evidence for a research question.",
    structured_output=True,
)
async def research_query(
    query: Annotated[str, Field(min_length=1, max_length=500)],
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
) -> dict[str, object]:
    return await _research_query(query=query, limit=limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Investment research MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="MCP transport (stdio is suitable for Claude Desktop/Cursor)",
    )
    args = parser.parse_args()
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
