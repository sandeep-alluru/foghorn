"""MCP server for foghorn.

Start:  python -m foghorn.mcp_server
Or:     foghorn-mcp

Add to Claude Desktop (~/.config/claude/claude_desktop_config.json):
    {
        "mcpServers": {
            "foghorn": {
                "command": "foghorn-mcp"
            }
        }
    }
"""

from __future__ import annotations

import sys
from typing import Any

try:
    import mcp.server.stdio as _mcp_stdio
    import mcp.types as _mcp_types
    from mcp.server import Server as _Server
    _HAS_MCP = True
except ImportError:
    _HAS_MCP = False


def run_server() -> None:
    """Start the MCP server on stdio."""
    if not _HAS_MCP:
        print("MCP server requires: pip install 'foghorn[mcp]'", file=sys.stderr)
        sys.exit(1)

    server = _Server("foghorn")

    @server.list_tools()
    async def list_tools() -> list[_mcp_types.Tool]:
        # TODO: define tools matching your CLI commands
        return []

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[_mcp_types.TextContent]:
        raise ValueError(f"Unknown tool: {name}")

    import asyncio

    async def _main() -> None:
        async with _mcp_stdio.stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_main())


if __name__ == "__main__":
    run_server()
