# Investment research MCP server

The server exposes three read-only tools backed by the existing provider
adapters:

| Tool | Purpose |
| --- | --- |
| `stock_query` | Public quote and bounded price history (Yahoo Finance) |
| `financial_query` | Latest annual or quarterly public financial report |
| `research_query` | Source-attributed web and news evidence bundle |

## Run

From the repository root:

```bash
./.venv/bin/python -m mcp_server                 # stdio (Claude Desktop/Cursor)
./.venv/bin/python -m mcp_server --transport streamable-http
```

The HTTP server defaults to `127.0.0.1:8000` and serves MCP at `/mcp`.
`MCP_HOST`, `MCP_PORT`, and `MCP_TRANSPORT` can override these defaults.

## Client configuration

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "investment-research": {
      "command": "/absolute/path/to/repo/.venv/bin/python",
      "args": ["-m", "mcp_server"],
      "cwd": "/absolute/path/to/repo"
    }
  }
}
```

Cursor uses the same command/args under `mcpServers` in `.cursor/mcp.json`.
ChatGPT connectors require a reachable HTTPS MCP endpoint; put the
`streamable-http` transport behind the deployment's authentication and TLS
proxy before registering its `/mcp` URL. The local server intentionally binds
to localhost and has no public authentication layer.

All outputs preserve provider timestamps, sources, URLs (where applicable),
and explicit missing/unavailable fields. They are research evidence, not
investment advice.
