"""Tawn's own callables, as tools.

`mcp_server.py` exposes recall/note/brief *outward* to Claude Code and Cursor.
This module registers the same functions *inward*, so a model answering in
`tawn chat` can search your memory mid-turn. One implementation, two directions.

`manage_tools` is the self-configuration set: the user can say "add the GitHub
MCP server" in chat and have it happen. Every one of them stages a **disabled**
artifact and returns the command needed to activate it — see `tools.py` for why
the enable switch is never delegated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from tawn.model.types import ToolSpec

_OBJ = {"type": "object", "properties": {}}


def _spec(name, description, properties, required=None, source="tawn", caps=None):
    return ToolSpec(
        name=name,
        description=description,
        parameters={
            "type": "object",
            "properties": properties,
            "required": required or [],
        },
        source=source,
        capabilities=caps or [],
    )


def verb_tools() -> list[tuple[ToolSpec, Callable[..., str]]]:
    from tawn.memory.brief import brief as _brief
    from tawn.memory.note import note as _note
    from tawn.memory.recall import recall as _recall

    def recall(query: str, domain: str | None = None, top_k: int = 5) -> str:
        return json.dumps(_recall(query=query, domain=domain, top_k=top_k))

    def note(payload: str, domain: str | None = None) -> str:
        return json.dumps(_note(payload=payload, domain=domain, source="model"))

    def brief(domain: str) -> str:
        return json.dumps(_brief(domain=domain))

    return [
        (
            _spec(
                "recall",
                "Search the user's compiled memory for relevant knowledge.",
                {
                    "query": {"type": "string", "description": "Natural-language query."},
                    "domain": {"type": "string", "description": "Optional domain filter."},
                    "top_k": {"type": "integer", "description": "How many chunks."},
                },
                ["query"],
                caps=["read"],
            ),
            recall,
        ),
        (
            _spec(
                "note",
                "Record a fact or decision in the user's memory.",
                {
                    "payload": {"type": "string", "description": "What to remember."},
                    "domain": {"type": "string", "description": "Optional domain."},
                },
                ["payload"],
                caps=["write"],
            ),
            note,
        ),
        (
            _spec(
                "brief",
                "Summarise what is going on in one of the user's domains.",
                {"domain": {"type": "string", "description": "Domain name."}},
                ["domain"],
                caps=["read"],
            ),
            brief,
        ),
    ]


def manage_tools(home: Path) -> list[tuple[ToolSpec, Callable[..., str]]]:
    """Self-configuration. Every tool here stages something disabled."""
    from tawn.model.tools import MANAGE_SOURCE

    home = Path(home)

    def mcp_add(
        name: str,
        command: str | None = None,
        args: str = "",
        url: str | None = None,
        env_keys: str = "",
    ) -> str:
        from tawn.mcp.registry import MCPServer, upsert_server

        if not command and not url:
            return "error: need either a command (stdio) or a url (http)"
        upsert_server(
            home,
            MCPServer(
                name=name,
                transport="http" if url else "stdio",
                command=command,
                args=args.split() if args else [],
                url=url,
                env_keys=[e.strip() for e in env_keys.split(",") if e.strip()],
            ),
        )
        return (
            f"Registered '{name}', disabled. To use it the user must run "
            f"`tawn mcp enable {name}` and add '{name}' to `mcp:` in "
            "~/.tawn/grants.yaml. I cannot do either of those."
        )

    def mcp_adopt() -> str:
        from tawn.mcp.adopt import adopt, discover_configured_servers

        found = discover_configured_servers()
        if not found:
            return "No MCP servers configured in any other tool on this machine."
        written = adopt(home, found)
        listing = ", ".join(f"{s.name} (from {s.source.split(':')[-1]})" for s in found)
        return (
            f"Found: {listing}. Added {written} new, all disabled. "
            "The user enables them with `tawn mcp enable <name>` plus an "
            "`mcp:` grant entry."
        )

    def skill_new(name: str, description: str, body: str) -> str:
        from tawn.skills.store import Skill, save_skill

        save_skill(home, Skill(name=name, description=description, body=body))
        return (
            f"Wrote skill '{name}'. It is active for Tawn immediately; run "
            f"`tawn skill sync` to project it into the user's other agents."
        )

    def skill_list() -> str:
        from tawn.skills.store import list_skills

        skills = list_skills(home)
        if not skills:
            return "No skills yet."
        return "\n".join(f"{s.name}: {s.description}" for s in skills)

    def tool_new(description: str) -> str:
        from tawn.model.router import default_router
        from tawn.tools.creator import CapabilityMismatch, generate_tool, write_tool

        try:
            manifest, impl, test = generate_tool(description, default_router(home))
            write_tool(home, manifest["name"], manifest, impl, test)
        except CapabilityMismatch as exc:
            return f"Rejected: {exc}"
        except Exception as exc:
            return f"Could not generate a tool: {exc}"
        return (
            f"Generated tool '{manifest['name']}', disabled. It declares "
            f"{manifest.get('capabilities') or 'no'} capabilities. The user "
            f"should review the source, then run `tawn tool enable "
            f"{manifest['name']}`. I cannot enable it myself."
        )

    return [
        (
            _spec(
                "mcp_add",
                "Register an MCP server for the user. It is added DISABLED — "
                "the user must enable and grant it separately.",
                {
                    "name": {"type": "string"},
                    "command": {"type": "string", "description": "For stdio servers."},
                    "args": {"type": "string", "description": "Space-separated."},
                    "url": {"type": "string", "description": "For http servers."},
                    "env_keys": {
                        "type": "string",
                        "description": "Comma-separated env var NAMES, never values.",
                    },
                },
                ["name"],
                MANAGE_SOURCE,
                ["write"],
            ),
            mcp_add,
        ),
        (
            _spec(
                "mcp_adopt",
                "Find MCP servers the user's other tools already configure and "
                "register them, disabled.",
                {},
                [],
                MANAGE_SOURCE,
                ["read", "write"],
            ),
            mcp_adopt,
        ),
        (
            _spec(
                "skill_new",
                "Author a skill for the user — reusable instructions, portable "
                "to their other agents.",
                {
                    "name": {"type": "string", "description": "kebab-case."},
                    "description": {"type": "string", "description": "One line."},
                    "body": {"type": "string", "description": "Markdown instructions."},
                },
                ["name", "description", "body"],
                MANAGE_SOURCE,
                ["write"],
            ),
            skill_new,
        ),
        (
            _spec("skill_list", "List the user's skills.", {}, [], MANAGE_SOURCE, ["read"]),
            skill_list,
        ),
        (
            _spec(
                "tool_new",
                "Generate a new tool from a description. It is created DISABLED "
                "and the user must review the source before enabling it.",
                {"description": {"type": "string"}},
                ["description"],
                MANAGE_SOURCE,
                ["write"],
            ),
            tool_new,
        ),
    ]
