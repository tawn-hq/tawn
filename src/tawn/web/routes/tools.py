"""MCP servers, skills and generated tools — one surface.

"What can my twin do" is one question, so the three sources of capability are
served together. Every mutating route here stages rather than activates:
adoption writes disabled servers, generation writes disabled tools, and
enabling is its own explicit call.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from tawn.capability.grants import Grants
from tawn.home import tawn_home

router = APIRouter(tags=["tools"])


def _grants() -> Grants:
    return Grants.load(tawn_home() / "grants.yaml")


# ── MCP servers ──────────────────────────────────────────────────────────────

@router.get("/mcp/servers")
def list_servers():
    from tawn.mcp.catalog import cached_tools
    from tawn.mcp.registry import load_servers

    granted = set(_grants().mcp or [])
    return {
        "servers": [
            {
                "name": s.name,
                "transport": s.transport,
                "enabled": s.enabled,
                "granted": s.name in granted,
                # Both gates, so the UI can explain which one is closed.
                "callable": s.enabled and s.name in granted,
                "source": s.source,
                "env_keys": s.env_keys,
                "tool_count": len(cached_tools(tawn_home(), s.name)),
            }
            for s in load_servers(tawn_home())
        ]
    }


class ServerBody(BaseModel):
    name: str
    transport: str = "stdio"
    command: str | None = None
    args: list[str] = []
    url: str | None = None
    env_keys: list[str] = []


@router.post("/mcp/servers")
def add_server(body: ServerBody):
    from tawn.mcp.registry import MCPServer, upsert_server

    server = MCPServer(**body.model_dump(), enabled=False)
    created = upsert_server(tawn_home(), server)
    return {"ok": True, "created": created, "enabled": False}


@router.get("/mcp/discovered")
def discovered():
    from tawn.mcp.adopt import discover_configured_servers
    from tawn.mcp.registry import load_servers

    known = {s.name for s in load_servers(tawn_home())}
    return {
        "servers": [
            {
                "name": s.name, "transport": s.transport, "source": s.source,
                "env_keys": s.env_keys, "known": s.name in known,
            }
            for s in discover_configured_servers()
        ]
    }


@router.post("/mcp/adopt")
def adopt():
    from tawn.mcp.adopt import adopt as adopt_servers
    from tawn.mcp.adopt import discover_configured_servers

    found = discover_configured_servers()
    return {"added": adopt_servers(tawn_home(), found), "found": len(found)}


@router.post("/mcp/{name}/{action}")
def server_action(name: str, action: str):
    from tawn.mcp.catalog import forget, get_tools
    from tawn.mcp.client import probe
    from tawn.mcp.registry import get_server, remove_server, upsert_server

    home = tawn_home()
    if action == "remove":
        return {"ok": remove_server(home, name)}

    server = get_server(home, name)
    if server is None:
        return {"ok": False, "error": f"no such server: {name}"}

    if action in ("enable", "disable"):
        server.enabled = action == "enable"
        upsert_server(home, server)
        granted = name in (_grants().mcp or [])
        return {
            "ok": True,
            "enabled": server.enabled,
            "granted": granted,
            # Enabling alone does not make it callable; say so plainly.
            "callable": server.enabled and granted,
        }

    if action == "test":
        health = probe(server)
        if health.reachable:
            forget(home, name)
            get_tools(home, server, refresh=True)
        return {
            "ok": health.reachable, "error": health.error,
            "tool_count": health.tool_count, "tools": health.tools,
        }

    return {"ok": False, "error": f"unknown action: {action}"}


@router.get("/mcp/{name}/tools")
def server_tools(name: str):
    from tawn.mcp.catalog import cached_tools

    return {"tools": cached_tools(tawn_home(), name)}


# ── skills ───────────────────────────────────────────────────────────────────

@router.get("/skills")
def list_skills_route():
    from tawn.skills.store import list_skills
    from tawn.skills.sync import detect_targets

    return {
        "skills": [
            {
                "name": s.name, "description": s.description, "body": s.body,
                "source": s.source, "imported_from": s.imported_from,
            }
            for s in list_skills(tawn_home())
        ],
        "targets": [a for a, _ in detect_targets()],
    }


class SkillBody(BaseModel):
    name: str
    description: str = ""
    body: str = ""


@router.post("/skills")
def save_skill_route(body: SkillBody):
    from tawn.skills.store import Skill, save_skill

    save_skill(tawn_home(), Skill(**body.model_dump()))
    return {"ok": True}


@router.post("/skills/sync")
def sync_skills():
    from tawn.skills.sync import sync_out

    report = sync_out(tawn_home())
    return {
        "written": report.written, "skipped": report.skipped,
        "conflicts": report.conflicts, "targets": report.targets,
    }


@router.post("/skills/import")
def import_skills_route(dry_run: bool = True):
    from tawn.skills.importer import import_skills

    report = import_skills(tawn_home(), dry_run=dry_run)
    return {
        "imported": report.imported, "skipped": report.skipped,
        "conflicts": report.conflicts, "dry_run": report.dry_run,
        "found": len(report.found),
    }


@router.delete("/skills/{name}")
def delete_skill(name: str):
    from tawn.skills.store import remove_skill

    return {"ok": remove_skill(tawn_home(), name)}


# ── generated tools ──────────────────────────────────────────────────────────

@router.get("/generated")
def list_generated():
    from tawn.capability.grants import capability_allowed
    from tawn.tools.creator import list_tools

    grants = _grants()
    out = []
    for m in list_tools(tawn_home()):
        caps = m.get("capabilities") or []
        out.append({
            "name": m.get("name"),
            "description": m.get("description", ""),
            "capabilities": caps,
            "enabled": bool(m.get("enabled")),
            "granted": all(capability_allowed(grants, c) for c in caps),
            "created_from": m.get("created_from", ""),
        })
    return {"tools": out}


@router.get("/generated/{name}")
def show_generated(name: str):
    from tawn.tools.creator import read_manifest, read_source

    manifest = read_manifest(tawn_home(), name)
    if manifest is None:
        return {"ok": False, "error": f"no tool named {name}"}
    return {"ok": True, "manifest": manifest, "source": read_source(tawn_home(), name)}


class GenerateBody(BaseModel):
    description: str
    cloud: bool = False


@router.post("/generated")
def generate(body: GenerateBody):
    from tawn.model.router import default_router
    from tawn.tools.creator import (
        CapabilityMismatch, generate_tool, write_tool,
    )

    home = tawn_home()
    try:
        manifest, impl, test = generate_tool(
            body.description, default_router(home), allow_cloud=body.cloud
        )
        write_tool(home, manifest["name"], manifest, impl, test)
    except CapabilityMismatch as exc:
        return {"ok": False, "error": str(exc), "kind": "capability_mismatch"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True, "name": manifest["name"],
        "capabilities": manifest["capabilities"],
        # Always false. Enabling is a separate, human decision.
        "enabled": False,
    }


@router.post("/generated/{name}/{action}")
def generated_action(name: str, action: str):
    from tawn.tools.creator import read_manifest, remove_tool, set_enabled
    from tawn.tools.loader import run_tool_test

    home = tawn_home()
    if action in ("enable", "disable"):
        if not set_enabled(home, name, action == "enable"):
            return {"ok": False, "error": f"no tool named {name}"}
        manifest = read_manifest(home, name) or {}
        return {"ok": True, "enabled": bool(manifest.get("enabled"))}
    if action == "test":
        ok, output = run_tool_test(home, name)
        return {"ok": ok, "output": output}
    if action == "remove":
        return {"ok": remove_tool(home, name)}
    return {"ok": False, "error": f"unknown action: {action}"}
