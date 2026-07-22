"""HTTP routes for federation: sources CRUD, records log, merge trigger, export."""

from __future__ import annotations

import re as _re
from pathlib import Path as _Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

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
def get_sources():
    home = tawn_home()
    from tawn.federation.discovery import run_discovery
    run_discovery(home)
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
    return {"ok": True, "name": name}


@router.delete("/sources/{name}")
def remove_source(name: str):
    home = tawn_home()
    sources = [s for s in load_config(home) if s.name != name]
    save_config(home, sources)
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
    return merge_pending(tawn_home(), session)


@router.get("/conversations")
def list_conversations(source: str | None = None, project: str | None = None, limit: int = 100, session: Session = Depends(get_session)):
    """List all ingested conversation files, optionally filtered by source or project."""
    q = session.query(FederationRecord).filter(FederationRecord.status == "merged")
    if source:
        q = q.filter(FederationRecord.source == source)
    if project:
        q = q.filter(FederationRecord.project == project)
    records = q.order_by(FederationRecord.ingested_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "source": r.source,
            "source_path": r.source_path,
            "project": r.project,
            "domain": r.domain,
            "ingested_at": r.ingested_at.isoformat() if r.ingested_at else None,
        }
        for r in records
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
                    name = block.get("name", "?")
                    inp = block.get("input", {})
                    inp_str = _json.dumps(inp, ensure_ascii=False)[:200] if inp else ""
                    parts.append(f"`[tool: {name}]`{' — ' + inp_str if inp_str else ''}")
                elif btype == "tool_result":
                    inner = block.get("content", "")
                    t = _extract_text(inner).strip()[:300]
                    if t:
                        parts.append(f"*tool result:* {t}")
                # skip image, document, etc.
            return "\n\n".join(p for p in parts if p.strip())
        return ""

    try:
        if path.suffix.lower() == ".jsonl":
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
                    if not content or _NOISE.search(content):
                        continue
                    # Skip lines that are mostly UUIDs
                    uuid_pat = _re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
                    uuid_chars = sum(len(m.group()) for m in uuid_pat.finditer(content))
                    if uuid_chars > len(content) * 0.3:
                        continue
                    ts = obj.get("timestamp") or ""
                    norm_role = "user" if role in ("user", "human") else "assistant"
                    turns.append({"role": norm_role, "content": content, "ts": ts})
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
                            turns.append({"role": cur_role, "content": c, "ts": ""})
                    cur_role = m.group(1).lower()
                    cur_lines = [m.group(2).strip()]
                elif cur_role:
                    cur_lines.append(line)
            if cur_role and cur_lines:
                c = "\n".join(cur_lines).strip()
                if c and not _NOISE.search(c):
                    turns.append({"role": cur_role, "content": c, "ts": ""})
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
