"""Normalise ConvTurn lists into frontmatter-tagged markdown for raw/imports/."""

from __future__ import annotations

import datetime
from pathlib import Path

import yaml

from tawn.federation.adapters.base import BaseAdapter, ConvTurn

# Path segments that aren't useful project-name candidates
_BORING_SEGMENTS = {
    "home", "users", "user", "documents", "downloads", "desktop",
    "github", "gitlab", "bitbucket", "src", "code", "dev",
    "projects", "repos", "workspace", "workspaces",
}


def _claude_code_cwd(source_path: Path) -> str | None:
    """Scan first 30 lines of Claude Code JSONL for a cwd field."""
    import json
    try:
        with source_path.open(encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= 60:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    cwd = obj.get("cwd")
                    if cwd:
                        return str(cwd)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return None


def infer_project(source_path: Path, adapter_name: str) -> str | None:
    """Extract a human-readable project name from the source file path.

    For Claude Code: reads `cwd` from JSONL metadata lines (most reliable).
    Falls back to decoding the parent dir name encoding.
    """
    if adapter_name in ("claude-code", "generic"):
        # Primary: cwd field gives the actual project root (works for both adapters)
        cwd = _claude_code_cwd(source_path)
        if cwd:
            return Path(cwd).name or None

        # For paths inside ~/.claude/projects/<encoded-dir>/ — decode dir name
        parts = source_path.parts
        try:
            idx = parts.index(".claude")
            if idx + 2 < len(parts) and parts[idx + 1] == "projects":
                dir_name = parts[idx + 2].strip("-")
                segments = [s for s in dir_name.split("-") if s and s.lower() not in _BORING_SEGMENTS]
                return segments[-1] if segments else None
        except ValueError:
            pass

        # Generic fallback: last non-boring segment of parent dir
        dir_name = source_path.parent.name.strip("-")
        segments = [s for s in dir_name.split("-") if s and s.lower() not in _BORING_SEGMENTS]
        return segments[-1] if segments else None

    return None


def infer_domain(
    turns: list[ConvTurn],
    adapter: BaseAdapter,
    source_path: Path | None = None,
) -> str:
    """Domain inference: turn metadata → content classifier → adapter default."""
    for turn in turns:
        if turn.metadata.get("domain"):
            return str(turn.metadata["domain"])

    # Run content classifier on first ~4000 chars of conversation
    if source_path is not None:
        content = " ".join(t.content for t in turns if t.content)[:4000]
        if content:
            try:
                from tawn.compiler.classifier import classify
                domain = classify(source_path, content)
                if domain:
                    return domain
            except Exception:
                pass

    return adapter.default_domain or "unknown"


def normalise(
    turns: list[ConvTurn],
    source: str,
    domain: str | None = None,
    project: str | None = None,
) -> str:
    """Build a markdown string with YAML frontmatter from a list of ConvTurns."""
    sensitive = any(t.sensitive for t in turns)
    fm: dict = {
        "source": source,
        "type": "conversation",
        "domain": domain or "unknown",
        "confidence": "medium",
        "sensitive": sensitive,
        "imported_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if project:
        fm["project"] = project

    lines = ["---", yaml.dump(fm, default_flow_style=False).rstrip(), "---", ""]

    session_ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    heading = f"## {project}" if project else f"## Session {session_ts}"
    lines.append(heading)
    lines.append(f"*{session_ts}*")
    lines.append("")

    for turn in turns:
        text = turn.content.strip().replace("\x00", "")
        if text:
            lines.append(f"**{turn.role}:** {text}")
            lines.append("")

    return "\n".join(lines).replace("\x00", "")


def write_to_raw_imports(
    home: Path,
    source: str,
    content: str,
    project: str | None = None,
) -> Path:
    """Append normalised markdown to raw/imports/<source>[/<project>]/YYYY-MM-DD.md."""
    today = datetime.date.today().strftime("%Y-%m-%d")
    if project:
        dest_dir = home / "raw" / "imports" / source / project
    else:
        dest_dir = home / "raw" / "imports" / source
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / f"{today}.md"
    with path.open("a") as f:
        f.write(content + "\n\n")
    return path
