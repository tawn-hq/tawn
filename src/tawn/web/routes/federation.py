"""HTTP routes for federation: sources CRUD, records log, merge trigger, export."""

from __future__ import annotations

import re as _re
from pathlib import Path as _Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from tawn.capability.audit import AuditLog
from tawn.db import get_session
from tawn.federation.config import FedSource, load_config, save_config
from tawn.federation.exporter import export as do_export
from tawn.federation.merge import merge_pending
from tawn.federation.schema import FederationRecord
from tawn.home import tawn_home

router = APIRouter(tags=["federation"])


class AddSourceBody(BaseModel):
    path: str
    name: str = ""
    format: str = "auto"


@router.get("/sources")
def get_sources(session: Session = Depends(get_session)):
    home = tawn_home()
    from tawn.federation.discovery import run_discovery
    newly_added = run_discovery(home)
    if newly_added > 0:
        # A freshly auto-detected source (e.g. a CLI tool used before Tawn
        # was ever installed) has real pre-existing history on disk that the
        # watcher — which only reacts to future file-change events — will
        # never see on its own. Backfill it now instead of waiting for the
        # next full server restart (the only other place this scan runs).
        newly_added_names = ", ".join(s.name for s in load_config(home)[-newly_added:])
        AuditLog(home / "audit.log").record(
            "federation.source_discovered", newly_added_names, ok=True,
            detail=f"{newly_added} new source(s) auto-detected", actor="system",
        )
        from tawn.federation.merge import scan_all_sources, merge_pending
        n = scan_all_sources(home, session)
        if n > 0:
            merge_pending(home, session, actor="system")
    sources = load_config(home)
    return [
        {
            "name": s.name,
            "path": s.path,
            "adapter": s.adapter,
            "format": s.format,
            "added": s.added,
            "auto_detected": s.auto_detected,
        }
        for s in sources
    ]


@router.post("/sources")
def add_source(body: AddSourceBody):
    home = tawn_home()
    existing = load_config(home)
    name = body.name.strip() or _re.sub(r"[^a-z0-9]+", "-", _Path(body.path).expanduser().name.lower()).strip("-") or "source"
    existing_names = {s.name for s in existing}
    base, i = name, 1
    while name in existing_names:
        name = f"{base}-{i}"; i += 1
    new_source = FedSource(
        name=name,
        path=body.path,
        adapter="generic",
        format=body.format,
        auto_detected=False,
    )
    save_config(home, existing + [new_source])
    AuditLog(home / "audit.log").record(
        "federation.source_add", name, ok=True, detail=body.path, actor="web",
    )
    return {"ok": True, "name": name}


@router.delete("/sources/{name}")
def remove_source(name: str):
    home = tawn_home()
    sources = [s for s in load_config(home) if s.name != name]
    save_config(home, sources)
    AuditLog(home / "audit.log").record(
        "federation.source_remove", name, ok=True, actor="web",
    )
    return {"ok": True}


@router.get("/records")
def get_records(limit: int = 50, session: Session = Depends(get_session)):
    records = (
        session.query(FederationRecord)
        .order_by(FederationRecord.ingested_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "source": r.source,
            "source_path": r.source_path,
            "fingerprint": r.fingerprint,
            "status": r.status,
            "domain": r.domain,
            "project": r.project,
            "ingested_at": r.ingested_at.isoformat() if r.ingested_at else None,
            "merged_at": r.merged_at.isoformat() if r.merged_at else None,
            "error": r.error,
        }
        for r in records
    ]


@router.post("/merge")
def trigger_merge(session: Session = Depends(get_session)):
    return merge_pending(tawn_home(), session, actor="web")


def _conv_kind(source_path: str, source: str = "") -> str:
    """Classify a federation record path into a conversation kind."""
    p = source_path.lower()
    if "/memory/" in p:
        return "memory"
    if "/subagents/" in p or "/tool-results/" in p or "/scratchpad" in p:
        return "subagent"
    if p.endswith(".jsonl"):
        return "session"
    if p.endswith(".md"):
        return "note"
    # Gemini CLI's local logs.json (~/.gemini/tmp/<project>/logs.json) is a
    # real per-project session log, just not named .jsonl like every other
    # adapter's format — without this it always falls through to "other"
    # and the UI's default kind=session filter hides it entirely.
    if source == "gemini-cli" and p.endswith(".json"):
        return "session"
    return "other"


@router.get("/conversations")
def list_conversations(
    source: str | None = None,
    project: str | None = None,
    kind: str | None = None,   # "session" | "memory" | "subagent" | "note" — default: session only
    limit: int = 100,
    session: Session = Depends(get_session),
):
    """List ingested conversations. By default returns only user sessions (kind=session)."""
    q = session.query(FederationRecord).filter(FederationRecord.status == "merged")
    if source:
        q = q.filter(FederationRecord.source == source)
    if project:
        q = q.filter(FederationRecord.project == project)
    records = q.order_by(FederationRecord.ingested_at.desc()).limit(limit * 4).all()

    # Filter by kind — default to sessions only (no subagent noise)
    want_kind = kind or "session"
    filtered = [r for r in records if _conv_kind(r.source_path, r.source) == want_kind][:limit]

    return [
        {
            "id": r.id,
            "source": r.source,
            "source_path": r.source_path,
            "project": r.project,
            "domain": r.domain,
            "kind": _conv_kind(r.source_path, r.source),
            "ingested_at": r.ingested_at.isoformat() if r.ingested_at else None,
        }
        for r in filtered
    ]


@router.get("/conversations/{record_id}")
def get_conversation(record_id: int, session: Session = Depends(get_session)):
    """Return full parsed conversation turns for a federation record."""
    import json as _json
    record = session.query(FederationRecord).filter(FederationRecord.id == record_id).first()
    if not record:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="record not found")

    path = _Path(record.source_path)
    if not path.exists():
        return {"id": record_id, "source": record.source, "project": record.project, "turns": [], "error": "source file not found"}

    turns = []
    _NOISE = _re.compile(
        r"\[SYSTEM NOTIFICATION\]|<task-notification>|<output-file>|<system-reminder>|<command-name>",
        _re.IGNORECASE,
    )

    def _extract_text(content) -> str:
        """Extract readable text from Claude Code content (string, list of blocks, or full API response dict)."""
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            # Full API response object — dig into its content array
            inner = content.get("content")
            if inner is not None:
                return _extract_text(inner)
            # Some entries store message text directly
            return content.get("text") or content.get("message") or ""
        if isinstance(content, list):
            parts = []
            for block in content:
                if not isinstance(block, dict):
                    if isinstance(block, str):
                        parts.append(block)
                    continue
                btype = block.get("type", "")
                if btype == "text":
                    t = block.get("text", "").strip()
                    if t:
                        parts.append(t)
                elif btype == "thinking":
                    t = block.get("thinking", "").strip()
                    if t:
                        parts.append(f"💭 *thinking*\n{t}")
                elif btype == "tool_use":
                    tname = block.get("name", "?")
                    inp = block.get("input", {}) or {}
                    # Render tool calls in human-readable form
                    if tname == "Bash":
                        cmd = (inp.get("command") or "").strip()[:120]
                        parts.append(f"🔧 **ran:** `{cmd}`")
                    elif tname in ("Read", "Write", "Edit"):
                        fp = inp.get("file_path", "")
                        parts.append(f"📄 **{tname.lower()}:** `{fp}`")
                    elif tname == "WebFetch":
                        url = inp.get("url", "")[:100]
                        parts.append(f"🌐 **fetched:** {url}")
                    elif tname == "WebSearch":
                        q2 = inp.get("query", "")[:80]
                        parts.append(f"🔍 **searched:** {q2}")
                    elif tname in ("Agent", "TaskCreate", "TaskUpdate"):
                        desc = inp.get("description") or inp.get("subject") or ""
                        parts.append(f"🤖 **{tname}:** {desc[:80]}")
                    else:
                        # Generic: show tool name + first meaningful value
                        first_val = next(iter(inp.values()), "") if inp else ""
                        short = str(first_val)[:80] if first_val else ""
                        parts.append(f"🔧 **{tname}**" + (f": {short}" if short else ""))
                elif btype == "tool_result":
                    # Skip tool results — they're noisy and usually not user-readable
                    pass
                # skip image, document, etc.
            return "\n\n".join(p for p in parts if p.strip())
        return ""

    _uuid_pat = _re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

    def _mostly_uuid(text: str) -> bool:
        uuid_chars = sum(len(m.group()) for m in _uuid_pat.finditer(text))
        return uuid_chars > len(text) * 0.3

    try:
        if record.source == "codex":
            # Real ~/.codex/sessions/**/rollout-*.jsonl envelope — see
            # federation/adapters/codex.py for the format this mirrors.
            # "developer" role lines are Codex's injected instructions, not
            # a real turn — skipped like Claude Code's own noise filtering.
            # "turn_context" lines carry the active model; it can change
            # mid-session, so track the latest seen and stamp it on turns.
            current_model = None
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = _json.loads(line)
                    if obj.get("type") == "turn_context":
                        m = obj.get("payload", {}).get("model")
                        if m:
                            current_model = m
                        continue
                    if obj.get("type") != "response_item":
                        continue
                    payload = obj.get("payload", {})
                    if payload.get("type") != "message":
                        continue
                    role = payload.get("role", "")
                    if role not in ("user", "assistant"):
                        continue
                    blocks = payload.get("content", [])
                    content = " ".join(
                        b.get("text", "") for b in blocks
                        if isinstance(b, dict) and b.get("text")
                    ).strip()
                    if not content or _NOISE.search(content) or _mostly_uuid(content):
                        continue
                    turns.append({
                        "role": role, "content": content, "ts": obj.get("timestamp") or "",
                        "model": current_model if role == "assistant" else None,
                    })
                except Exception:
                    continue
        elif record.source == "gemini-cli" and path.name == "logs.json":
            # ~/.gemini/tmp/<project>/logs.json — flat array, see
            # federation/adapters/gemini_cli.py. Only "user" entries have
            # been observed in practice (a prompt log, not a full transcript,
            # so no model info here — that only lives in chats/*.jsonl).
            try:
                data = _json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                data = []
            for entry in data if isinstance(data, list) else []:
                if not isinstance(entry, dict):
                    continue
                raw_type = entry.get("type", "")
                role = "user" if raw_type == "user" else "assistant" if raw_type in ("gemini", "model") else None
                if role is None:
                    continue
                content = str(entry.get("message", "")).strip()
                if not content or _NOISE.search(content) or _mostly_uuid(content):
                    continue
                turns.append({"role": role, "content": content, "ts": entry.get("timestamp") or "", "model": None})
        elif record.source == "gemini-cli":
            # ~/.gemini/tmp/<project>/chats/session-*.jsonl — the full-duplex
            # transcript. First line is a header; "$set" patch lines and
            # "error"/"info" CLI-noise lines are skipped.
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = _json.loads(line)
                    if "$set" in obj or "type" not in obj:
                        continue
                    raw_type = obj.get("type")
                    if raw_type == "user":
                        blocks = obj.get("content", [])
                        content = " ".join(
                            b.get("text", "") for b in blocks
                            if isinstance(b, dict) and b.get("text")
                        ).strip()
                        model = None
                    elif raw_type == "gemini":
                        content = str(obj.get("content", "")).strip()
                        model = obj.get("model")
                    else:
                        continue
                    if not content or _NOISE.search(content) or _mostly_uuid(content):
                        continue
                    role = "user" if raw_type == "user" else "assistant"
                    turns.append({"role": role, "content": content, "ts": obj.get("timestamp") or "", "model": model})
                except Exception:
                    continue
        elif path.suffix.lower() == ".jsonl":
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = _json.loads(line)
                    role = (obj.get("role") or obj.get("type") or "").lower()
                    if role not in ("user", "assistant", "human", "ai"):
                        continue
                    raw_content = obj.get("content") or obj.get("message") or ""
                    content = _extract_text(raw_content).strip()
                    if not content or _NOISE.search(content) or _mostly_uuid(content):
                        continue
                    ts = obj.get("timestamp") or ""
                    norm_role = "user" if role in ("user", "human") else "assistant"
                    # Claude Code envelope nests model under message.model on
                    # assistant turns; absent elsewhere (older flat format).
                    msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
                    model = msg.get("model") if norm_role == "assistant" else None
                    turns.append({"role": norm_role, "content": content, "ts": ts, "model": model})
                except Exception:
                    continue
        elif path.suffix.lower() == ".md":
            import re as _re2
            text = path.read_text(encoding="utf-8", errors="replace")
            role_re = _re2.compile(r"^\*\*(user|assistant|human|ai)\*\*:\s*(.+)", _re2.IGNORECASE)
            cur_role = ""
            cur_lines: list[str] = []
            for line in text.splitlines():
                m = role_re.match(line.strip())
                if m:
                    if cur_role and cur_lines:
                        c = "\n".join(cur_lines).strip()
                        if c and not _NOISE.search(c):
                            turns.append({"role": cur_role, "content": c, "ts": "", "model": None})
                    cur_role = m.group(1).lower()
                    cur_lines = [m.group(2).strip()]
                elif cur_role:
                    cur_lines.append(line)
            if cur_role and cur_lines:
                c = "\n".join(cur_lines).strip()
                if c and not _NOISE.search(c):
                    turns.append({"role": cur_role, "content": c, "ts": "", "model": None})
    except Exception as exc:
        return {"id": record_id, "source": record.source, "project": record.project, "turns": [], "error": str(exc)}

    return {
        "id": record_id,
        "source": record.source,
        "project": record.project,
        "domain": record.domain,
        "source_path": record.source_path,
        "turns": turns,
    }
