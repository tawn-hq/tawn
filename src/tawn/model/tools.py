"""The tool registry — everything the model may call, and the gate in front of it.

Four sources reduce to one `ToolSpec` list:

  tawn          recall / note / brief, Tawn's own memory verbs
  tawn:manage   self-configuration — propose only, never enable
  mcp:<server>  tools discovered on a granted, enabled MCP server
  local:<tool>  generated tools the user has reviewed and enabled

Capability checks live here rather than in a provider adapter, so there is one
place to read when asking "what could this model actually do".
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from tawn.capability.grants import Grants
from tawn.model.types import ToolCall, ToolResult, ToolSpec

#: Management tools the model may call. Every one stages a *disabled* artifact.
#: Nothing that flips enabled state appears here, and `_assert_no_enable`
#: enforces that at build time — a model able to enable what it just created
#: could grant itself a capability inside a single turn, which would make the
#: disabled-by-default rule decorative.
MANAGE_SOURCE = "tawn:manage"

_FORBIDDEN_MANAGE = ("enable", "disable", "grant")


class ToolRegistry:
    """The set of tools available for one turn, with their implementations."""

    def __init__(self, home: Path):
        self.home = Path(home)
        self._specs: dict[str, ToolSpec] = {}
        self._impls: dict[str, Callable[..., str]] = {}

    # ── assembly ─────────────────────────────────────────────────────────
    @classmethod
    def build(cls, home: Path, grants: Grants | None = None) -> "ToolRegistry":
        home = Path(home)
        grants = grants if grants is not None else Grants.load(home / "grants.yaml")
        reg = cls(home)
        reg._add_verbs()
        reg._add_builtins(grants)
        reg._add_manage()
        reg._add_mcp(grants)
        reg._add_generated(grants)
        _assert_no_enable(reg)
        return reg

    def register(
        self, spec: ToolSpec, impl: Callable[..., str] | None = None
    ) -> None:
        self._specs[spec.name] = spec
        if impl is not None:
            self._impls[spec.name] = impl

    def specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def names(self) -> set[str]:
        return set(self._specs)

    def __len__(self) -> int:
        return len(self._specs)

    # ── sources ──────────────────────────────────────────────────────────
    def _add_verbs(self) -> None:
        from tawn.model.verbs import verb_tools

        for spec, impl in verb_tools():
            self.register(spec, impl)

    def _add_builtins(self, grants: Grants) -> None:
        from tawn.model.builtins import builtin_tools
        from tawn.model.extras import extra_tools

        for spec, impl in builtin_tools(grants):
            self.register(spec, impl)
        for spec, impl in extra_tools(self.home, grants):
            self.register(spec, impl)

    def _add_manage(self) -> None:
        from tawn.model.verbs import manage_tools

        for spec, impl in manage_tools(self.home):
            self.register(spec, impl)

    def _add_mcp(self, grants: Grants) -> None:
        from tawn.mcp.catalog import cached_tools
        from tawn.mcp.registry import load_servers

        granted = set(grants.mcp or [])
        for server in load_servers(self.home):
            # Both gates, deliberately. The grant is the user's security
            # decision and `enabled` their convenience one; collapsing them
            # would mean disabling a server temporarily also discarded the
            # security decision.
            if not server.enabled or server.name not in granted:
                continue
            for tool in cached_tools(self.home, server.name):
                name = f"{server.name}__{tool['name']}"
                self.register(
                    ToolSpec(
                        name=name,
                        description=tool.get("description", ""),
                        parameters=tool.get("parameters")
                        or {"type": "object", "properties": {}},
                        source=f"mcp:{server.name}",
                        capabilities=["net"],
                        # A third-party server's return value is somebody
                        # else's text, and what it does is somebody else's
                        # code. Both untrusted by definition.
                        returns_untrusted=True,
                        side_effecting=True,
                    ),
                    _mcp_impl(server, tool["name"]),
                )

    def _add_generated(self, grants: Grants) -> None:
        try:
            from tawn.tools.loader import load_tools
        except ImportError:  # Phase E not present
            return
        for spec, impl in load_tools(self.home, grants):
            self.register(spec, impl)

    # ── execution ────────────────────────────────────────────────────────
    def execute(self, call: ToolCall) -> ToolResult:
        """Run a tool. Errors become results, not exceptions.

        A raised exception would end the agent loop; an error *result* is fed
        back to the model, which can often recover by calling something else.
        """
        from tawn.capability.audit import AuditLog, audit_path

        spec = self._specs.get(call.name)
        if spec is None:
            return ToolResult(
                id=call.id, content=f"no such tool: {call.name}", is_error=True
            )
        impl = self._impls.get(call.name)
        if impl is None:
            return ToolResult(
                id=call.id, content=f"tool not executable: {call.name}", is_error=True
            )

        ok = True
        try:
            content = str(impl(**(call.arguments or {})))
        except Exception as exc:
            ok = False
            content = f"{type(exc).__name__}: {exc}"

        try:
            AuditLog(audit_path(self.home)).record(
                op="tool.call",
                target=call.name,
                ok=ok,
                # Keys only. Arguments routinely carry secrets and file
                # contents, and an audit log is not the place for either.
                detail=f"args={sorted((call.arguments or {}).keys())}",
                actor="model",
            )
        except Exception:
            pass

        return ToolResult(id=call.id, content=content, is_error=not ok)


def _mcp_impl(server, tool_name: str) -> Callable[..., str]:
    def _run(**kwargs) -> str:
        from tawn.mcp.client import connect

        session = connect(server)
        try:
            return session.call_tool(tool_name, kwargs)
        finally:
            session.close()

    return _run


def _assert_no_enable(reg: "ToolRegistry") -> None:
    """No management tool may flip enabled state or edit grants."""
    for spec in reg.specs():
        if spec.source != MANAGE_SOURCE:
            continue
        if any(word in spec.name for word in _FORBIDDEN_MANAGE):
            raise RuntimeError(
                f"management tool '{spec.name}' would let a model grant itself "
                "a capability; staging is delegable, enabling is not"
            )
