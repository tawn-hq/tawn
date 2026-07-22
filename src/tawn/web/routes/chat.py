"""Chat routes — SSE streaming through Router.stream(), same as CLI."""

import json
import re

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from tawn.home import tawn_home
from tawn.model.identity import with_baseline
from tawn.model.router import default_router, usable_models
from tawn.model.types import Message
from tawn.history import Session as HistorySession

router = APIRouter()

_ACTION_RE = re.compile(r"\[ACTION:([^\]]+)\]")


def _parse_action(raw: str) -> dict | None:
    """Parse an ACTION marker into a structured dict."""
    parts = raw.split(":", 1)
    kind = parts[0].strip()
    arg = parts[1].strip() if len(parts) > 1 else ""
    if kind == "grant_read":
        return {"kind": "grant_read", "path": arg, "label": f"Grant read access to {arg}"}
    if kind == "create_domain":
        name, _, desc = arg.partition("|")
        return {"kind": "create_domain", "name": name.strip(), "description": desc.strip(),
                "label": f"Create domain: {name.strip()}"}
    if kind == "compile":
        return {"kind": "compile", "label": "Trigger memory compilation"}
    if kind == "federation_scan":
        return {"kind": "federation_scan", "label": "Scan + merge federation sources"}
    return None


@router.get("/models")
def chat_models():
    return usable_models(tawn_home())


class ChatBody(BaseModel):
    history: list[dict]
    sensitive: bool = False
    target: str | None = None
    session_id: str | None = None  # client passes to continue existing session


def _recall_context(query: str, home) -> str | None:
    """Inject top recalled chunks as context. Returns formatted string or None."""
    try:
        from tawn.memory.recall import recall as do_recall
        results = do_recall(query, top_k=5, home=home, format="snippets")
        chunks = results.get("chunks", [])
        if not chunks:
            return None
        parts = []
        for c in chunks:
            src = c.get("source", "")
            domain = c.get("domain") or ""
            content = (c.get("content") or "").strip()[:600]
            label = f"[{domain}] {src}" if domain else src
            parts.append(f"— {label}:\n{content}")
        return "Relevant context from your memory:\n\n" + "\n\n".join(parts)
    except Exception:
        return None


@router.post("/stream")
def chat_stream(body: ChatBody):
    home = tawn_home()
    user_msgs = [m for m in body.history if m["role"] == "user"]

    # Inject recall context from compiled memory for the last user message
    context_injection: str | None = None
    if user_msgs:
        last_q = user_msgs[-1]["content"][:300]
        context_injection = _recall_context(last_q, home)

    raw_msgs = [Message(role=m["role"], content=m["content"]) for m in body.history]
    if context_injection and raw_msgs:
        # Prepend context as a system-style injected turn before the last user msg
        inject_msg = Message(role="user", content=f"[MEMORY CONTEXT — use this to inform your answer]\n{context_injection}\n\n[USER MESSAGE]\n{user_msgs[-1]['content']}")
        raw_msgs = raw_msgs[:-1] + [inject_msg]

    msgs = with_baseline(raw_msgs, home)
    r = default_router(home, target=body.target)
    hist = HistorySession(home, session_id=body.session_id)

    # derive title from first user message (first 60 chars)
    title = user_msgs[0]["content"][:60].strip() if user_msgs else "chat"

    # save the last user turn
    if user_msgs:
        last_user = user_msgs[-1]["content"]
        hist.append("user", last_user)

    def events():
        acc = ""
        model_used = ""
        tokens_in = 0
        tokens_out = 0
        emitted_actions: set[str] = set()
        yield f"data: {json.dumps({'type': 'session', 'session_id': hist.session_id, 'title': title})}\n\n"
        for chunk in r.stream(msgs, sensitive=body.sensitive):
            if chunk.error:
                yield f"data: {json.dumps({'type': 'error', 'message': chunk.error})}\n\n"
                return
            if chunk.done:
                # Scan full accumulated text for any action markers not yet emitted
                for m in _ACTION_RE.finditer(acc):
                    raw = m.group(1)
                    if raw not in emitted_actions:
                        action = _parse_action(raw)
                        if action:
                            emitted_actions.add(raw)
                            yield f"data: {json.dumps({'type': 'action', 'action': action})}\n\n"
                # Store response with markers stripped
                clean = _ACTION_RE.sub("", acc).strip()
                hist.append("assistant", clean, model=model_used, tokens_in=tokens_in, tokens_out=tokens_out)
                yield f"data: {json.dumps({'type': 'done', 'tokens_in': chunk.tokens_in, 'tokens_out': chunk.tokens_out})}\n\n"
                return
            text = chunk.text or ""
            acc += text
            model_used = getattr(chunk, "model", "") or model_used
            tokens_in = getattr(chunk, "tokens_in", 0) or tokens_in
            tokens_out = getattr(chunk, "tokens_out", 0) or tokens_out
            # Emit action events as they appear mid-stream, suppress marker text
            clean_text = text
            for m in _ACTION_RE.finditer(acc):
                raw = m.group(1)
                if raw not in emitted_actions:
                    action = _parse_action(raw)
                    if action:
                        emitted_actions.add(raw)
                        yield f"data: {json.dumps({'type': 'action', 'action': action})}\n\n"
                        clean_text = clean_text.replace(f"[ACTION:{raw}]", "")
            if clean_text.strip() or not _ACTION_RE.search(text):
                yield f"data: {json.dumps({'type': 'chunk', 'text': clean_text})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


class ActionBody(BaseModel):
    kind: str
    path: str | None = None
    name: str | None = None
    description: str | None = None


@router.post("/action")
def execute_action(body: ActionBody):
    """Execute a user-approved in-chat action."""
    home = tawn_home()

    if body.kind == "grant_read":
        if not body.path:
            return {"ok": False, "error": "path required"}
        import yaml as _yaml
        from pathlib import Path as _P
        from tawn.capability.grants import Grants
        p = _P(body.path).expanduser().resolve()
        if not p.exists():
            # Try common case-insensitive fix (Linux paths are case-sensitive)
            # Return informative error rather than silently granting a ghost path
            return {"ok": False, "error": f"path not found: {p}\nCheck the path exists and try again."}
        grants_path = home / "grants.yaml"
        grants = Grants.load(grants_path)
        existing = [str(r) for r in grants.read]
        if str(p) not in existing:
            existing.append(str(p))
            # Write back preserving other fields
            data = _yaml.safe_load(grants_path.read_text()) if grants_path.exists() else {}
            data = data or {}
            data["read"] = existing
            grants_path.write_text(_yaml.dump(data, default_flow_style=False))
            try:
                from tawn.capability.audit import AuditLog
                AuditLog(home / "audit.jsonl").record("grant.confirm (chat)", str(grants_path), True)
            except Exception:
                pass
        return {"ok": True, "message": f"Read access granted to {p}"}

    if body.kind == "create_domain":
        if not body.name or not body.description:
            return {"ok": False, "error": "name and description required"}
        from tawn.domains.creation import generate_domain_source, has_usable_model
        from tawn.domains.registry import _load_local_domain, enable
        if not has_usable_model(home):
            return {"ok": False, "error": "no model configured"}
        from tawn.model.router import default_router
        source = generate_domain_source(body.description, default_router(home))
        folder = home / "domains" / body.name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "domain.py").write_text(source)
        spec = _load_local_domain(folder)
        error = None if spec else "generated domain.py failed to import"
        if spec:
            enable(body.name, home)
        return {"ok": spec is not None, "name": body.name, "error": error, "source": source[:200]}

    if body.kind == "compile":
        from tawn.db import make_engine, session as db_session
        from tawn.compiler.compiler import run_compile
        engine = make_engine()
        with db_session(engine) as s:
            result = run_compile(home, s)
        return {"ok": result.ok, "chunks_added": result.chunks_added, "error": result.error}

    if body.kind == "federation_scan":
        from tawn.db import make_engine, session as db_session
        from tawn.federation.merge import scan_all_sources, merge_pending
        engine = make_engine()
        with db_session(engine) as s:
            ingested = scan_all_sources(home, s)
            result = merge_pending(home, s)
        return {"ok": True, "ingested": ingested, "merged": result.get("merged", 0)}

    return {"ok": False, "error": f"unknown action kind: {body.kind}"}
