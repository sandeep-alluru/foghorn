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

    from foghorn.repo import WorldRepo

    server = _Server("foghorn")

    @server.list_tools()
    async def list_tools() -> list[_mcp_types.Tool]:
        return [
            _mcp_types.Tool(
                name="foghorn/list_facts",
                description="List all facts stored in a foghorn repository.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "repo_path": {
                            "type": "string",
                            "description": "Path to the foghorn database file (e.g. .foghorn/world.db).",
                        },
                    },
                    "required": ["repo_path"],
                },
            ),
            _mcp_types.Tool(
                name="foghorn/record_decision",
                description=(
                    "Stage a decision that depends on a set of facts. "
                    "Call foghorn/commit afterwards to persist it."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "repo_path": {
                            "type": "string",
                            "description": "Path to the foghorn database file.",
                        },
                        "decision": {
                            "type": "string",
                            "description": "Short slug label for the decision (e.g. 'chose-redis').",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Full reasoning text for the decision.",
                        },
                        "facts": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of Fact IDs this decision depends on.",
                        },
                    },
                    "required": ["repo_path", "decision", "rationale", "facts"],
                },
            ),
            _mcp_types.Tool(
                name="foghorn/commit",
                description="Commit all staged facts and decisions to the foghorn repository.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "repo_path": {
                            "type": "string",
                            "description": "Path to the foghorn database file.",
                        },
                        "message": {
                            "type": "string",
                            "description": "Human-readable commit message.",
                        },
                    },
                    "required": ["repo_path", "message"],
                },
            ),
            _mcp_types.Tool(
                name="foghorn/check_stale",
                description=(
                    "Return all decisions that are stale because their upstream facts changed "
                    "since the previous commit."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "repo_path": {
                            "type": "string",
                            "description": "Path to the foghorn database file.",
                        },
                    },
                    "required": ["repo_path"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[_mcp_types.TextContent]:
        import json

        if name == "foghorn/list_facts":
            repo_path = arguments["repo_path"]
            with WorldRepo.init(repo_path) as repo:
                facts = repo.store.list_facts()
            lines = [
                f"{f.id}  {f.subject} {f.predicate} {f.object}  (confidence={f.confidence})"
                for f in facts
            ]
            text = "\n".join(lines) if lines else "No facts found."
            return [_mcp_types.TextContent(type="text", text=text)]

        elif name == "foghorn/record_decision":
            repo_path = arguments["repo_path"]
            label = arguments["decision"]
            rationale = arguments["rationale"]
            fact_ids: list[str] = arguments.get("facts", [])
            with WorldRepo.init(repo_path) as repo:
                d = repo.decide(label, rationale, depends_on=fact_ids)
            text = f"Staged decision  {d.id}  {d.label}  (depends on {len(d.fact_ids)} facts)"
            return [_mcp_types.TextContent(type="text", text=text)]

        elif name == "foghorn/commit":
            repo_path = arguments["repo_path"]
            message = arguments["message"]
            with WorldRepo.init(repo_path) as repo:
                try:
                    wc = repo.commit(message)
                    text = (
                        f"Committed  {wc.id[:8]}  {wc.message}\n"
                        f"  {len(wc.fact_ids)} facts · {len(wc.decision_ids)} decisions"
                    )
                except ValueError as exc:
                    text = f"Error: {exc}"
            return [_mcp_types.TextContent(type="text", text=text)]

        elif name == "foghorn/check_stale":
            repo_path = arguments["repo_path"]
            with WorldRepo.init(repo_path) as repo:
                alerts = repo.stale()
            if not alerts:
                text = "No stale decisions."
            else:
                payload = [
                    {
                        "decision_id": a.decision_id,
                        "decision_label": a.decision_label,
                        "stale_fact_ids": a.stale_fact_ids,
                        "impact_score": a.impact_score,
                    }
                    for a in alerts
                ]
                text = json.dumps(payload, indent=2)
            return [_mcp_types.TextContent(type="text", text=text)]

        else:
            raise ValueError(f"Unknown tool: {name}")

    import asyncio

    async def _main() -> None:
        async with _mcp_stdio.stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_main())


if __name__ == "__main__":
    run_server()
