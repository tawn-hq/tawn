"""Chat routes — SSE streaming through Router.stream(), same as CLI."""

import json
import re

from fastapi import APIRouter, File, Header, UploadFile
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
    # Ids from /api/chat/attach. The parsed text is fetched server-side and
    # injected for *this turn only*, so a document never rides along in the
    # history and get re-sent on every later turn.
    attachments: list[str] = []
    # Opt-in per turn. Off by default so an existing client sees exactly the
    # behaviour it had before tools existed.
    tools: bool = False


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


@router.post("/attach")
async def attach(file: UploadFile = File(...)):
    """Parse an uploaded document immediately and store its text.

    Parsing on attach rather than on send is what keeps chat responsive: the
    work happens once, while the user is still typing, instead of on every
    turn that carries the file.
    """
    from tawn.memory import attachments as att
    from tawn.parsing import ParseError

    data = await file.read()
    try:
        stored = att.ingest(tawn_home(), file.filename or "upload", data)
    except ParseError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"could not read that file: {exc}"}
    return {"ok": True, **stored.meta()}


@router.delete("/attach/{attach_id}")
def detach(attach_id: str):
    from tawn.memory import attachments as att

    return {"ok": att.remove(tawn_home(), attach_id)}


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

    # Both injections rewrite the final user turn, so they are composed in one
    # place. Building them separately meant whichever ran last discarded the
    # other's work.
    if raw_msgs and (context_injection or body.attachments):
        blocks: list[str] = []

        # Attachment text joins this turn only, never the stored history: a
        # 100k-character document re-sent on every later turn is what makes a
        # conversation stall with no reply.
        if body.attachments:
            from tawn.memory import attachments as att

            attached = att.context_block(home, body.attachments)
            if attached:
                blocks.append(f"[ATTACHED DOCUMENTS]\n{attached}")

        if context_injection:
            blocks.append(
                f"[MEMORY CONTEXT — use this to inform your answer]\n{context_injection}"
            )

        if blocks:
            last = raw_msgs[-1]
            raw_msgs = raw_msgs[:-1] + [
                Message(
                    role=last.role,
                    content="\n\n".join(blocks) + f"\n\n[USER MESSAGE]\n{last.content}",
                )
            ]

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

        # Tools run before streaming: a tool call is a structured request, and
        # the loop must see the whole response to know one was made. Results
        # are appended to the conversation, then the final answer streams as
        # usual — so the user still sees tokens arrive, just after any work.
        turn = list(msgs)
        if body.tools:
            try:
                from tawn.model.agent import run as run_agent
                from tawn.model.tools import ToolRegistry

                registry = ToolRegistry.build(home)
                if len(registry):
                    # The prompt already carries content Tawn did not author —
                    # an attached document, or chunks recalled from a corpus
                    # built out of granted paths. Either can contain text aimed
                    # at the model, so the turn starts restricted rather than
                    # waiting for a tool to fetch something hostile.
                    result = run_agent(
                        r, turn, registry, sensitive=body.sensitive,
                        tainted=bool(body.attachments or context_injection),
                    )
                    for entry in result.trace():
                        yield f"data: {json.dumps({'type': 'tool', 'tool': entry})}\n\n"
                    if result.tool_calls:
                        turn = turn + [
                            Message(
                                role="user",
                                content=(
                                    "[TOOL RESULTS — use these to answer]\n"
                                    + "\n\n".join(
                                        f"{e['name']}: {e['result']}"
                                        for e in result.trace()
                                    )
                                ),
                            )
                        ]
                    if result.withdrawn:
                        yield f"data: {json.dumps({'type': 'notice', 'message': 'read outside content — ' + ', '.join(sorted(result.withdrawn)) + ' withdrawn for this turn'})}\n\n"
                    if result.truncated:
                        yield f"data: {json.dumps({'type': 'notice', 'message': 'tool loop hit its iteration limit'})}\n\n"
            except Exception as exc:
                # Tool failure must not cost the user their answer.
                yield f"data: {json.dumps({'type': 'notice', 'message': f'tools unavailable: {exc}'})}\n\n"

        for chunk in r.stream(turn, sensitive=body.sensitive):
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
            # Re-confirm the integrity sidecar — every writer of grants.yaml
            # must do this or the very next load_verified() call (e.g. the
            # web UI's Grants tab) raises IntegrityError on a file this same
            # request just wrote.
            from tawn.capability.integrity import confirm as _integrity_confirm
            digest = _integrity_confirm(grants_path)
            try:
                from tawn.capability.audit import AuditLog, audit_path
                # This line has now been "fixed" in both directions: it once
                # wrote audit.jsonl (invisible to writers), then audit.log
                # (invisible to the reader). The split itself was the bug —
                # `audit_path()` is the single answer, and a test now fails
                # if anyone hardcodes either filename again.
                AuditLog(audit_path(home)).record("grant.confirm (chat)", str(grants_path), True, detail=digest, actor="chat")
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
            enable(body.name, home, actor="chat")
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
            result = merge_pending(home, s, actor="chat")
        return {"ok": True, "ingested": ingested, "merged": result.get("merged", 0)}

    return {"ok": False, "error": f"unknown action kind: {body.kind}"}
