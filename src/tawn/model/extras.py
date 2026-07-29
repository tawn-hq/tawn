"""The rest of the standard toolset: research, the twin's own knowledge, repos.

`builtins.py` holds the generic agent primitives (files, search, net, shell).
These are the tools that only make sense because Tawn has a compiled memory, an
entity graph and domains — the ones that make the agent *this* agent.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable

from tawn.capability.grants import Grants, capability_allowed, path_allowed
from tawn.model.types import ToolSpec

MAX_OUTPUT = 20_000
GIT_TIMEOUT = 20


def _spec(name, description, properties, required, caps,
          untrusted=False, side_effecting=False):
    return ToolSpec(
        name=name,
        description=description,
        parameters={"type": "object", "properties": properties, "required": required},
        source="tawn:builtin",
        capabilities=caps,
        returns_untrusted=untrusted,
        side_effecting=side_effecting,
    )


def extra_tools(home: Path, grants: Grants) -> list[tuple[ToolSpec, Callable[..., str]]]:
    home = Path(home)

    # ── research ─────────────────────────────────────────────────────────
    def deep_research(
        question: str,
        domain: str | None = None,
        depth: int = 2,
        remember: bool = False,
    ) -> str:
        from tawn.model.research import deep_research as _run

        return _run(
            question=question, domain=domain, depth=depth,
            home=home, remember=remember,
        ).to_markdown()

    def gather_context(topic: str, domain: str | None = None) -> str:
        from tawn.model.research import gather_context as _ctx

        return _ctx(topic=topic, domain=domain, home=home).to_markdown()

    def web_search(query: str, limit: int = 6) -> str:
        from tawn.model.research import web_search as _search

        hits = _search(query, limit)
        if not hits:
            return "no results — check connectivity and the `net:` grant"
        return "\n".join(f"{h.title}\n  {h.url}\n  {h.snippet[:200]}" for h in hits)

    def fetch_many(urls: str) -> str:
        """Fetch several pages at once — comma or newline separated."""
        from tawn.model.research import fetch_page

        targets = [u.strip() for u in re.split(r"[,\n]", urls) if u.strip()][:8]
        if not targets:
            return "no urls given"
        out = []
        for u in targets:
            try:
                out.append(f"=== {u} ===\n{fetch_page(u)[:4000]}")
            except Exception as exc:
                out.append(f"=== {u} ===\nfetch failed: {exc}")
        return "\n\n".join(out)[:MAX_OUTPUT]

    # ── diagrams ─────────────────────────────────────────────────────────
    def draw_diagram(
        name: str, description: str, format: str = "mermaid", context: str = ""
    ) -> str:
        from tawn.model.diagrams import DiagramError, draft, formats_help

        try:
            d = draft(home, name, description, fmt=format, context=context)
        except DiagramError as exc:
            return f"{exc}\n\nAvailable formats:\n{formats_help()}"
        except Exception as exc:
            return f"could not draft the diagram: {exc}"
        state = "saved" if d.is_new else "unchanged (identical to an existing version)"
        return (
            f"{d.name} v{d.version} ({d.fmt}) — {state}\n{d.path}\n\n{d.source}"
        )

    def revise_diagram(name: str, instruction: str) -> str:
        from tawn.model.diagrams import DiagramError, revise

        try:
            d = revise(home, name, instruction)
        except DiagramError as exc:
            return str(exc)
        except Exception as exc:
            return f"could not revise: {exc}"
        return f"{d.name} v{d.version} — earlier versions kept\n{d.path}\n\n{d.source}"

    def list_diagrams() -> str:
        from tawn.artifacts import list_artifacts

        arts = list_artifacts(home, "diagrams")
        if not arts:
            return "no diagrams yet"
        return "\n".join(
            f"{a.name:<28} {a.fmt:<6} v{a.latest.number if a.latest else 0} "
            f"— {a.description[:60]}"
            for a in arts
        )

    def get_diagram(name: str, version: int | None = None) -> str:
        from tawn.artifacts import read_artifact

        found = read_artifact(home, "diagrams", name, version)
        if found is None:
            return f"no diagram named {name!r}"
        art, v, source = found
        return f"{art.name} v{v.number} ({art.fmt})\n\n{source}"

    # ── the twin's own knowledge ─────────────────────────────────────────
    def wiki_lookup(entity: str) -> str:
        from tawn.compiler.wiki import wiki_root

        root = wiki_root(home) if callable(globals().get("wiki_root", None)) else home / "wiki"
        matches = list(Path(root).rglob(f"{entity}.md")) if Path(root).exists() else []
        if not matches:
            slug = entity.lower().replace(" ", "-")
            matches = [p for p in Path(root).rglob("*.md")] if Path(root).exists() else []
            matches = [p for p in matches if p.stem.lower() in (entity.lower(), slug)]
        if not matches:
            return f"no wiki page for {entity!r} — try `recall` instead"
        try:
            return matches[0].read_text(errors="replace")[:MAX_OUTPUT]
        except OSError as exc:
            return f"could not read the page: {exc}"

    def graph_neighbors(entity: str, limit: int = 25) -> str:
        from tawn.db import make_engine, session as db_session
        from tawn.memory.schema import Entity, EntityEdge

        try:
            with db_session(make_engine()) as s:
                ent = (
                    s.query(Entity).filter(Entity.canonical.ilike(entity)).first()
                )
                if ent is None:
                    return f"no entity named {entity!r}"
                rows = (
                    s.query(EntityEdge)
                    .filter(
                        (EntityEdge.from_entity_id == ent.id)
                        | (EntityEdge.to_entity_id == ent.id)
                    )
                    .order_by(EntityEdge.weight.desc())
                    .limit(limit)
                    .all()
                )
                out = []
                for e in rows:
                    other_id = (
                        e.to_entity_id if e.from_entity_id == ent.id else e.from_entity_id
                    )
                    other = s.get(Entity, other_id)
                    if other is not None:
                        out.append(f"{ent.canonical} —{e.relation}→ {other.canonical} (x{e.weight})")
        except Exception as exc:
            return f"graph unavailable: {exc}"
        return "\n".join(out) or f"{entity} has no recorded links"

    def list_domains() -> str:
        try:
            from tawn.domains.registry import enabled_domains

            names = [d.name for d in enabled_domains()]
        except Exception as exc:
            return f"could not list domains: {exc}"
        return ", ".join(names) or "no domains enabled"

    def memory_status() -> str:
        from tawn.compiler.compiler import compile_status

        try:
            return str(compile_status(home))
        except Exception as exc:
            return f"status unavailable: {exc}"

    # ── repositories ─────────────────────────────────────────────────────
    def _git(repo: str, *args: str) -> str:
        root = Path(repo).expanduser()
        if not path_allowed(grants, root, "read"):
            return f"denied: {root} is not under a granted `read:` path"
        if not (root / ".git").exists():
            return f"not a git repository: {root}"
        try:
            proc = subprocess.run(
                ["git", "-C", str(root), *args],
                capture_output=True, text=True, timeout=GIT_TIMEOUT, check=False,
            )
        except Exception as exc:
            return f"git failed: {exc}"
        return (proc.stdout + proc.stderr)[:MAX_OUTPUT] or "(no output)"

    def git_log(repo: str, limit: int = 20) -> str:
        return _git(repo, "log", f"-{max(1, min(limit, 200))}", "--oneline", "--decorate")

    def git_diff(repo: str, ref: str = "HEAD") -> str:
        return _git(repo, "diff", ref, "--stat")

    def git_status(repo: str) -> str:
        return _git(repo, "status", "--short", "--branch")

    catalogue: list[tuple[ToolSpec, Callable[..., str]]] = [
        (
            _spec(
                "deep_research",
                "Research a question against the user's own memory AND the web, "
                "returning a cited briefing. Use for anything needing evidence "
                "rather than recall alone.",
                {
                    "question": {"type": "string"},
                    "domain": {
                        "type": "string",
                        "description": "Optional domain to bias local recall.",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Search rounds, 1-5. Default 2. Higher digs further.",
                    },
                    "remember": {
                        "type": "boolean",
                        "description": "Save the briefing into memory so later questions build on it.",
                    },
                },
                ["question"],
                ["read", "net"],
                untrusted=True,
            ),
            deep_research,
        ),
        (
            _spec(
                "gather_context",
                "Load broad context on a subject — what it is, where it stands, "
                "what is disputed, what is adjacent. Use before writing or "
                "deciding, when you need to surround a topic rather than "
                "answer one question.",
                {
                    "topic": {"type": "string"},
                    "domain": {"type": "string", "description": "Optional domain."},
                },
                ["topic"],
                ["read", "net"],
                untrusted=True,
            ),
            gather_context,
        ),
        (
            _spec(
                "web_search",
                "Search the web and return titles, URLs and snippets.",
                {"query": {"type": "string"}, "limit": {"type": "integer"}},
                ["query"],
                ["net"],
                untrusted=True,
            ),
            web_search,
        ),
        (
            _spec(
                "fetch_many",
                "Fetch several URLs at once and return their text.",
                {"urls": {"type": "string", "description": "Comma or newline separated."}},
                ["urls"],
                ["net"],
                untrusted=True,
            ),
            fetch_many,
        ),
        (
            _spec(
                "draw_diagram",
                "Draft a diagram as SOURCE (TikZ for LaTeX papers, Mermaid for "
                "docs, DOT for graphs, PlantUML for UML) and save it, versioned. "
                "Use to illustrate research findings or figures for academic "
                "writing. Produces editable source, not an image.",
                {
                    "name": {"type": "string", "description": "Short name to save it under."},
                    "description": {"type": "string", "description": "What to draw."},
                    "format": {
                        "type": "string",
                        "enum": ["mermaid", "tikz", "dot", "plantuml"],
                        "description": "tikz for papers, mermaid for docs.",
                    },
                    "context": {
                        "type": "string",
                        "description": "Optional material to base the diagram on.",
                    },
                },
                ["name", "description"],
                ["write"],
                side_effecting=True,
            ),
            draw_diagram,
        ),
        (
            _spec(
                "revise_diagram",
                "Revise a saved diagram. Creates a new version; earlier "
                "versions are never modified or deleted.",
                {"name": {"type": "string"}, "instruction": {"type": "string"}},
                ["name", "instruction"],
                ["write"],
                side_effecting=True,
            ),
            revise_diagram,
        ),
        (
            _spec("list_diagrams", "List saved diagrams and their versions.", {}, [], ["read"]),
            list_diagrams,
        ),
        (
            _spec(
                "get_diagram",
                "Read a saved diagram's source, latest or a specific version.",
                {"name": {"type": "string"}, "version": {"type": "integer"}},
                ["name"],
                ["read"],
            ),
            get_diagram,
        ),
        (
            _spec(
                "wiki_lookup",
                "Read the twin's wiki page for an entity — people, projects, tools.",
                {"entity": {"type": "string"}},
                ["entity"],
                ["read"],
                untrusted=True,
            ),
            wiki_lookup,
        ),
        (
            _spec(
                "graph_neighbors",
                "List what an entity is connected to in the twin's knowledge graph.",
                {"entity": {"type": "string"}, "limit": {"type": "integer"}},
                ["entity"],
                ["read"],
            ),
            graph_neighbors,
        ),
        (
            _spec("list_domains", "List the user's configured domains.", {}, [], ["read"]),
            list_domains,
        ),
        (
            _spec(
                "memory_status",
                "How current the compiled memory is — chunk counts and last compile.",
                {}, [], ["read"],
            ),
            memory_status,
        ),
        (
            _spec(
                "git_log",
                "Recent commits in a granted repository.",
                {"repo": {"type": "string"}, "limit": {"type": "integer"}},
                ["repo"],
                ["read"],
                untrusted=True,
            ),
            git_log,
        ),
        (
            _spec(
                "git_diff",
                "Change summary against a ref in a granted repository.",
                {"repo": {"type": "string"}, "ref": {"type": "string"}},
                ["repo"],
                ["read"],
                untrusted=True,
            ),
            git_diff,
        ),
        (
            _spec(
                "git_status",
                "Working-tree status of a granted repository.",
                {"repo": {"type": "string"}},
                ["repo"],
                ["read"],
                untrusted=True,
            ),
            git_status,
        ),
    ]

    return [
        (spec, impl)
        for spec, impl in catalogue
        if all(capability_allowed(grants, c) for c in spec.capabilities)
    ]
