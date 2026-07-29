"""The standard agent toolset — files, search, network, shell.

These are the tools any capable agent needs. In Tawn every one of them routes
through the capability layer on *each call*: `read_file` refuses a path outside
the `read:` grants, `write_file` refuses one outside `write:`, `fetch_url` needs
`net: true` and `run_command` needs `shell: true`.

That per-call check is the point. A built-in tool that skipped it would be a way
around the grant model rather than an expression of it, and it would be the
first thing a prompt-injected model reached for.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from tawn.capability.grants import Grants, path_allowed
from tawn.model.types import ToolSpec

#: Caps on what a single call may return, so one tool call cannot blow the
#: model's context or stall a turn.
MAX_READ_BYTES = 200_000
MAX_RESULTS = 200
MAX_OUTPUT_CHARS = 20_000
COMMAND_TIMEOUT = 60

_DENIED_READ = "denied: {path} is not under a granted `read:` path in ~/.tawn/grants.yaml"
_DENIED_WRITE = "denied: {path} is not under a granted `write:` path in ~/.tawn/grants.yaml"


def _spec(name, description, properties, required, caps,
          untrusted=False, side_effecting=False):
    return ToolSpec(
        name=name,
        description=description,
        parameters={
            "type": "object",
            "properties": properties,
            "required": required,
        },
        source="tawn:builtin",
        capabilities=caps,
        returns_untrusted=untrusted,
        side_effecting=side_effecting,
    )


def builtin_tools(grants: Grants) -> list[tuple[ToolSpec, Callable[..., str]]]:
    """The built-ins whose capabilities the current grants can back."""

    # ── files ────────────────────────────────────────────────────────────
    def read_file(path: str, max_bytes: int = MAX_READ_BYTES) -> str:
        p = Path(path).expanduser()
        if not path_allowed(grants, p, "read"):
            return _DENIED_READ.format(path=p)
        if not p.is_file():
            return f"no such file: {p}"
        try:
            return p.read_text(errors="replace")[: min(max_bytes, MAX_READ_BYTES)]
        except UnicodeDecodeError:
            # Not plain text — a PDF, Word file or spreadsheet. Route it
            # through the parser rather than returning mojibake.
            return read_document(path)
        except OSError as exc:
            return f"could not read {p}: {exc}"

    def read_document(path: str, use_ocr: bool = True) -> str:
        """Any document format — PDF, Word, Excel, slides, EPUB, images."""
        from tawn.parsing import ParseError, parse_file

        p = Path(path).expanduser()
        if not path_allowed(grants, p, "read"):
            return _DENIED_READ.format(path=p)
        try:
            doc = parse_file(p, use_ocr=use_ocr)
        except ParseError as exc:
            return str(exc)
        header = f"[{doc.format}, {doc.chars} chars"
        if doc.warnings:
            header += "; " + "; ".join(doc.warnings)
        return f"{header}]\n\n{doc.text}"

    def list_dir(path: str) -> str:
        p = Path(path).expanduser()
        if not path_allowed(grants, p, "read"):
            return _DENIED_READ.format(path=p)
        if not p.is_dir():
            return f"not a directory: {p}"
        try:
            entries = sorted(p.iterdir())[:MAX_RESULTS]
        except OSError as exc:
            return f"could not list {p}: {exc}"
        return "\n".join(f"{'d' if e.is_dir() else 'f'} {e.name}" for e in entries) or "(empty)"

    def search_files(pattern: str, path: str, glob: str = "*") -> str:
        """Literal substring search — deliberately not a regex.

        A model-supplied regex can backtrack catastrophically over a large
        tree, and substring search is what these calls almost always want.
        """
        root = Path(path).expanduser()
        if not path_allowed(grants, root, "read"):
            return _DENIED_READ.format(path=root)
        if not root.is_dir():
            return f"not a directory: {root}"
        hits: list[str] = []
        try:
            for f in root.rglob(glob):
                if len(hits) >= MAX_RESULTS:
                    break
                if not f.is_file() or not path_allowed(grants, f, "read"):
                    continue
                try:
                    for n, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
                        if pattern in line:
                            hits.append(f"{f}:{n}: {line.strip()[:200]}")
                            if len(hits) >= MAX_RESULTS:
                                break
                except OSError:
                    continue
        except OSError as exc:
            return f"search failed: {exc}"
        return "\n".join(hits) or f"no matches for {pattern!r}"

    def write_file(path: str, content: str) -> str:
        p = Path(path).expanduser()
        if not path_allowed(grants, p, "write"):
            return _DENIED_WRITE.format(path=p)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        except OSError as exc:
            return f"could not write {p}: {exc}"
        return f"wrote {len(content)} chars to {p}"

    def edit_file(path: str, old: str, new: str) -> str:
        p = Path(path).expanduser()
        if not path_allowed(grants, p, "write"):
            return _DENIED_WRITE.format(path=p)
        if not p.is_file():
            return f"no such file: {p}"
        try:
            text = p.read_text()
        except OSError as exc:
            return f"could not read {p}: {exc}"
        count = text.count(old)
        if count == 0:
            return "no match for the text to replace — nothing changed"
        if count > 1:
            # Replacing an ambiguous match is how an edit silently corrupts a
            # file, so it is refused rather than guessed.
            return f"{count} matches — make the text unique; nothing changed"
        try:
            p.write_text(text.replace(old, new, 1))
        except OSError as exc:
            return f"could not write {p}: {exc}"
        return f"edited {p}"

    # ── network ──────────────────────────────────────────────────────────
    def fetch_url(url: str) -> str:
        if not grants.net:
            return "denied: network access is off — set `net: true` in ~/.tawn/grants.yaml"
        try:
            import httpx

            resp = httpx.get(url, timeout=30, follow_redirects=True)
            resp.raise_for_status()
        except Exception as exc:
            return f"fetch failed: {exc}"
        return resp.text[:MAX_OUTPUT_CHARS]

    # ── shell ────────────────────────────────────────────────────────────
    def run_command(command: str, cwd: str | None = None) -> str:
        if not grants.shell:
            return "denied: shell access is off — set `shell: true` in ~/.tawn/grants.yaml"
        workdir = Path(cwd).expanduser() if cwd else None
        if workdir is not None and not path_allowed(grants, workdir, "read"):
            return _DENIED_READ.format(path=workdir)
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=COMMAND_TIMEOUT,
                cwd=str(workdir) if workdir else None,
            )
        except subprocess.TimeoutExpired:
            return f"timed out after {COMMAND_TIMEOUT}s"
        except Exception as exc:
            return f"could not run: {exc}"
        out = (proc.stdout + proc.stderr)[:MAX_OUTPUT_CHARS]
        return f"exit {proc.returncode}\n{out}"

    catalogue: list[tuple[ToolSpec, Callable[..., str]]] = [
        (
            _spec(
                "read_file",
                "Read a text file the user has granted access to.",
                {"path": {"type": "string"}, "max_bytes": {"type": "integer"}},
                ["path"],
                ["read"],
                untrusted=True,
            ),
            read_file,
        ),
        (
            _spec(
                "read_document",
                "Read any document — PDF, Word, Excel, PowerPoint, EPUB, "
                "OpenDocument, or a scanned image via OCR. Use this rather "
                "than read_file for anything that is not plain text.",
                {
                    "path": {"type": "string"},
                    "use_ocr": {
                        "type": "boolean",
                        "description": "OCR scanned pages. Local and free. Default true.",
                    },
                },
                ["path"],
                ["read"],
                untrusted=True,
            ),
            read_document,
        ),
        (
            _spec(
                "list_dir",
                "List the contents of a granted directory.",
                {"path": {"type": "string"}},
                ["path"],
                ["read"],
                untrusted=True,
            ),
            list_dir,
        ),
        (
            _spec(
                "search_files",
                "Find a literal string in files under a granted directory.",
                {
                    "pattern": {"type": "string", "description": "Literal text, not a regex."},
                    "path": {"type": "string"},
                    "glob": {"type": "string", "description": "e.g. '*.py'. Default '*'."},
                },
                ["pattern", "path"],
                ["read"],
                untrusted=True,
            ),
            search_files,
        ),
        (
            _spec(
                "write_file",
                "Write a file inside a granted writable directory.",
                {"path": {"type": "string"}, "content": {"type": "string"}},
                ["path", "content"],
                ["write"],
                side_effecting=True,
            ),
            write_file,
        ),
        (
            _spec(
                "edit_file",
                "Replace a unique piece of text in a granted writable file.",
                {
                    "path": {"type": "string"},
                    "old": {"type": "string", "description": "Must appear exactly once."},
                    "new": {"type": "string"},
                },
                ["path", "old", "new"],
                ["write"],
                side_effecting=True,
            ),
            edit_file,
        ),
        (
            _spec(
                "fetch_url",
                "Fetch a URL and return its body.",
                {"url": {"type": "string"}},
                ["url"],
                ["net"],
                untrusted=True, side_effecting=True,
            ),
            fetch_url,
        ),
        (
            _spec(
                "run_command",
                "Run a shell command and return its output.",
                {"command": {"type": "string"}, "cwd": {"type": "string"}},
                ["command"],
                ["shell"],
                untrusted=True, side_effecting=True,
            ),
            run_command,
        ),
    ]

    # A tool whose capability no grant backs is not offered at all. Offering it
    # and having every call return "denied" wastes turns and teaches the model
    # that refusals are noise.
    from tawn.capability.grants import capability_allowed

    return [
        (spec, impl)
        for spec, impl in catalogue
        if all(capability_allowed(grants, c) for c in spec.capabilities)
    ]
