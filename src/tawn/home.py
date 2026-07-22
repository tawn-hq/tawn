"""Tawn home directory: TAWN_HOME resolution and skeleton creation.

Spec: design spec §3.2 canonical store; §14 stage 0.
"""

import os
from pathlib import Path

#: Directories of the canonical store (design spec §3.2 + later stages' homes).
SKELETON = [
    "raw/identity",
    "raw/vault",
    "raw/agent-notes",
    "raw/imports",
    "raw/review-queue",
    "wiki",
    "wiki/.staging",
    "domains",
    "federation/inbox",
    "federation/adapters",
    "federation/exports",
    "failures",
    "handoffs",
    "personality",
    "history",
]

_CONFIG_STUB = """\
# ~/.tawn/config.yaml — Tawn user preferences
# Edit with: tawn config set <key> <value>
# View all:  tawn config list
theme: system
model: auto
web_port: 8787
compile_interval_minutes: 5
federation_merge_interval_minutes: 5
memory_max_mb: null
cpu_weight: 50
db_pool_size: 2
lazy_compile: true
"""

_MCP_SERVERS_STUB = """\
# ~/.tawn/mcp_servers.yaml
# Add external MCP servers Tawn should be able to call.
# Enabled by Stage 9 (MCP Manager). Format frozen here.
servers: {}

# Example (uncomment to enable in Stage 9):
#   github:
#     command: npx
#     args: ["-y", "@modelcontextprotocol/server-github"]
#     env:
#       GITHUB_TOKEN: "${GITHUB_TOKEN}"
#     scopes: [read_issues, read_prs]
"""


def tawn_home() -> Path:
    """The Tawn home; TAWN_HOME env overrides ~/.tawn (tests rely on this)."""
    return Path(os.environ.get("TAWN_HOME", "~/.tawn")).expanduser().resolve()


def init_home(home: Path) -> list[Path]:
    """Create the skeleton idempotently. Returns newly created dirs only."""
    created: list[Path] = []
    for rel in SKELETON:
        d = home / rel
        if not d.is_dir():
            d.mkdir(parents=True)
            created.append(d)
    stub = home / "mcp_servers.yaml"
    if not stub.exists():
        stub.write_text(_MCP_SERVERS_STUB)
        stub.chmod(0o600)
    cfg_stub = home / "config.yaml"
    if not cfg_stub.exists():
        cfg_stub.write_text(_CONFIG_STUB)
        cfg_stub.chmod(0o600)
    return created
