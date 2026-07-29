"""Diagram drafting — source, not pixels.

The model writes diagram *source* (TikZ, Mermaid, DOT, PlantUML) rather than an
image, because source is what a user can paste into a paper, version in git,
edit six months later, and re-render at any resolution. An image is a dead end
in every one of those directions.

Every diagram is stored through `tawn.artifacts`, which is append-only and
atomic: revising produces a new version and never touches the old one.
Rendering to PDF or SVG is optional and best-effort — the source is the
artifact, the render is a convenience.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

KIND = "diagrams"

#: format → (file extension, what it is for, how it is validated)
FORMATS: dict[str, dict] = {
    "tikz": {
        "ext": "tex",
        "use": "LaTeX papers and theses — publication quality, vector output",
        "opens": ("\\begin{tikzpicture}",),
    },
    "mermaid": {
        "ext": "mmd",
        "use": "documentation and the web — renders natively in Tawn's own UI",
        "opens": ("graph", "flowchart", "sequenceDiagram", "classDiagram",
                  "stateDiagram", "erDiagram", "gantt", "mindmap", "timeline",
                  "journey", "pie", "quadrantChart", "gitGraph"),
    },
    "dot": {
        "ext": "dot",
        "use": "graphs and dependency structures — Graphviz",
        "opens": ("digraph", "graph", "strict"),
    },
    "plantuml": {
        "ext": "puml",
        "use": "UML — sequence, class, component, deployment",
        "opens": ("@startuml",),
    },
}

RENDERERS = {
    "tikz": ("pdflatex", "pdf"),
    "mermaid": ("mmdc", "svg"),
    "dot": ("dot", "svg"),
    "plantuml": ("plantuml", "svg"),
}


class DiagramError(ValueError):
    pass


@dataclass
class Diagram:
    name: str
    fmt: str
    source: str
    version: int
    path: Path
    is_new: bool


_PROMPT = """Draft a diagram in {fmt} format.

Subject: {description}
{context}
Requirements:
- Output ONLY the diagram source. No markdown fences, no commentary, no prose.
- It must be syntactically valid and compile/render as-is.
- Label everything a reader needs; an unlabelled node is a wasted node.
- Prefer clarity over decoration. No colour unless it encodes meaning.
{extra}"""

_EXTRA = {
    "tikz": (
        "- Emit only the `\\begin{tikzpicture}...\\end{tikzpicture}` block.\n"
        "- No preamble, no \\documentclass, no \\usepackage — it is being pasted\n"
        "  into an existing document.\n"
        "- Use standard TikZ libraries only (arrows.meta, positioning, shapes)."
    ),
    "mermaid": (
        "- Start with the diagram type keyword (graph TD, flowchart LR,\n"
        "  sequenceDiagram, erDiagram, ...).\n"
        "- Quote any label containing spaces or punctuation."
    ),
    "dot": (
        "- Start with `digraph G {` or `graph G {`.\n"
        "- Set rankdir where it helps readability."
    ),
    "plantuml": "- Wrap in @startuml / @enduml.",
}


def _strip_fences(text: str) -> str:
    text = (text or "").strip()
    m = re.match(r"^```[a-zA-Z]*\s*\n(.*?)\n?```\s*$", text, re.S)
    return (m.group(1) if m else text).strip()


def validate(source: str, fmt: str) -> None:
    """Cheap structural check. Not a compiler — a guard against empty or
    obviously-wrong output being stored as if it were a diagram."""
    if fmt not in FORMATS:
        raise DiagramError(f"unknown format {fmt!r} — pick one of {', '.join(FORMATS)}")
    src = (source or "").strip()
    if not src:
        raise DiagramError("empty diagram source")
    opens = FORMATS[fmt]["opens"]
    if not any(tok in src for tok in opens):
        raise DiagramError(
            f"does not look like {fmt}: expected one of {', '.join(opens[:4])}"
        )
    if fmt in ("dot", "tikz", "mermaid") and src.count("{") != src.count("}"):
        raise DiagramError("unbalanced braces")


def generate_source(
    description: str,
    fmt: str,
    client,
    context: str = "",
    allow_cloud: bool = False,
) -> str:
    from tawn.model.types import Message

    if fmt not in FORMATS:
        raise DiagramError(f"unknown format {fmt!r} — pick one of {', '.join(FORMATS)}")
    prompt = _PROMPT.format(
        fmt=fmt,
        description=description,
        context=f"\nUse this material:\n{context[:6000]}\n" if context else "\n",
        extra=_EXTRA.get(fmt, ""),
    )
    resp = client.complete(
        [Message(role="user", content=prompt)], sensitive=not allow_cloud
    )
    source = _strip_fences(resp.text)
    validate(source, fmt)
    return source


def save(
    home: Path,
    name: str,
    source: str,
    fmt: str,
    description: str = "",
    note: str = "",
) -> Diagram:
    """Store a diagram. Never overwrites — a revision becomes a new version."""
    from tawn.artifacts import artifact_dir, save_artifact, slugify

    validate(source, fmt)
    ext = FORMATS[fmt]["ext"]
    art, version, is_new = save_artifact(
        home, KIND, name, source, ext, description=description, note=note
    )
    return Diagram(
        name=art.name,
        fmt=fmt,
        source=source,
        version=version.number,
        path=artifact_dir(home, KIND, slugify(name)) / version.filename,
        is_new=is_new,
    )


def draft(
    home: Path,
    name: str,
    description: str,
    fmt: str = "mermaid",
    context: str = "",
    client=None,
    allow_cloud: bool = False,
) -> Diagram:
    """Generate and store a diagram in one step."""
    if client is None:
        from tawn.model.router import default_router

        client = default_router(Path(home))
    source = generate_source(description, fmt, client, context, allow_cloud)
    return save(home, name, source, fmt, description=description, note="drafted")


def revise(
    home: Path,
    name: str,
    instruction: str,
    client=None,
    allow_cloud: bool = False,
) -> Diagram:
    """Revise the latest version into a new one. The original is untouched."""
    from tawn.artifacts import read_artifact
    from tawn.model.types import Message

    found = read_artifact(home, KIND, name)
    if found is None:
        raise DiagramError(f"no diagram named {name!r}")
    art, version, source = found
    fmt = _fmt_for_ext(art.fmt)

    if client is None:
        from tawn.model.router import default_router

        client = default_router(Path(home))

    prompt = (
        f"Revise this {fmt} diagram.\n\nChange requested: {instruction}\n\n"
        f"Current source:\n{source}\n\n"
        "Output ONLY the complete revised source. No fences, no commentary."
    )
    revised = _strip_fences(
        client.complete([Message(role="user", content=prompt)], sensitive=not allow_cloud).text
    )
    validate(revised, fmt)
    return save(home, name, revised, fmt, description=art.description, note=instruction[:120])


def _fmt_for_ext(ext: str) -> str:
    for fmt, meta in FORMATS.items():
        if meta["ext"] == ext:
            return fmt
    return "mermaid"


def render(home: Path, name: str, version: int | None = None) -> tuple[bool, str]:
    """Best-effort render to PDF/SVG. Returns (ok, message-or-path).

    Failure is never destructive: the source artifact is already durable, and a
    missing toolchain is a normal state rather than an error worth raising.
    """
    from tawn.artifacts import artifact_dir, read_artifact, slugify

    found = read_artifact(home, KIND, name, version)
    if found is None:
        return False, f"no diagram named {name!r}"
    art, v, source = found
    fmt = _fmt_for_ext(art.fmt)
    tool, out_ext = RENDERERS.get(fmt, (None, None))
    if tool is None or shutil.which(tool) is None:
        return False, (
            f"{tool or fmt} is not installed — the source is saved and still "
            f"usable at {artifact_dir(home, KIND, slugify(name)) / v.filename}"
        )

    d = artifact_dir(home, KIND, slugify(name))
    src_path = d / v.filename
    out_path = d / f"v{v.number:03d}.{out_ext}"
    try:
        if fmt == "dot":
            cmd = [tool, f"-T{out_ext}", str(src_path), "-o", str(out_path)]
        elif fmt == "mermaid":
            cmd = [tool, "-i", str(src_path), "-o", str(out_path)]
        elif fmt == "plantuml":
            cmd = [tool, "-tsvg", str(src_path)]
        else:  # tikz
            cmd = [tool, "-interaction=nonstopmode", "-output-directory", str(d), str(src_path)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    except Exception as exc:
        return False, f"render failed: {exc}"
    if proc.returncode != 0 and not out_path.exists():
        return False, f"render failed: {(proc.stderr or proc.stdout)[:400]}"
    return True, str(out_path)


def formats_help() -> str:
    return "\n".join(f"{k:<10} {v['use']}" for k, v in FORMATS.items())
