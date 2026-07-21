"""Tawn MCP server — exposes recall / note / brief as MCP tools.

Transports:
  stdio  — run via `tawn mcp` (for Claude Code, Cursor, Cline)
  HTTP/SSE — mounted on FastAPI app at /mcp (for browser MCP clients)

Requires fastmcp >= 2.0.
"""

from __future__ import annotations

from fastmcp import FastMCP

from tawn.memory.brief import brief as _brief
from tawn.memory.note import note as _note
from tawn.memory.recall import recall as _recall

mcp = FastMCP("tawn", instructions="Tawn memory — recall / note / brief")


@mcp.tool()
def recall(
    query: str,
    domain: str | None = None,
    top_k: int = 5,
    format: str = "snippets",
) -> dict:
    """Search Tawn's compiled memory for relevant knowledge chunks.

    Args:
        query: Natural-language search query.
        domain: Filter to a specific domain (work/research/wealth/academic/hobby).
        top_k: Number of chunks to return (default 5).
        format: 'snippets' returns raw chunks; 'composed' synthesises a prose answer.
    """
    return _recall(query=query, domain=domain, top_k=top_k, format=format)


@mcp.tool()
def note(
    payload: str,
    domain: str | None = None,
    type: str = "observation",
    confidence: str = "medium",
    source: str | None = None,
    ttl_days: int | None = None,
) -> dict:
    """Append a structured note to Tawn's memory and queue a compile.

    Args:
        payload: Markdown text or plain fact to record.
        domain: Domain this note belongs to (work/research/wealth/academic/hobby).
        type: Note type — observation | decision | fact | question.
        confidence: high | medium | low.
        source: Calling agent name (e.g. 'claude-code').
        ttl_days: Days until this note expires. None = permanent.
    """
    return _note(
        payload=payload,
        domain=domain,
        type=type,
        confidence=confidence,
        source=source,
        ttl_days=ttl_days,
    )


@mcp.tool()
def brief(domain: str) -> dict:
    """Get a summary brief for a Tawn domain.

    Args:
        domain: Domain name (work/research/wealth/academic/hobby).
    """
    return _brief(domain=domain)
