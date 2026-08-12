# Tawn — the twin you own

> **taw (ת) + own** — Local-first personal digital twin. Your data, your machine, your intelligence.

Tawn is a self-hosted memory and context core that unifies your work, wealth, research, and academic life into one searchable brain — shared across every AI agent you use (Claude Code, Cursor, Gemini CLI, and others).

**Why it exists.** Every assistant remembers you now — inside itself, on the vendor's servers, for as long as you keep paying. What you taught Claude is invisible to Cursor. None of those stores index the repositories and notes your work actually lives in, and none records what another agent just changed. That gap isn't an oversight someone will fix: memory is what makes a vendor's product sticky, so interoperability runs against their interest. Tawn is the shared substrate they have no reason to build — one memory, on your machine, that every tool can read.

```
pip install tawn
tawn init
tawn web start    # opens the web dashboard at http://tawn:8787
```

## What it does

- **Memory federation** — indexes conversations from Claude, ChatGPT, Gemini, Obsidian, and local files into one semantic store
- **Domain modules** — Work, Wealth (read-only), Research, and Academic — each with its own compiled wiki and entity graph
- **Multi-provider model routing** — Anthropic, OpenAI, Gemini, DeepSeek, OpenRouter, Ollama; local by default, cloud when needed
- **MCP server** — any MCP-compatible agent gets `recall`, `note`, and `brief` verbs against your twin's memory
- **Web dashboard** — streaming chat, memory browser, audit log, settings — at `tawn:8787`
- **Capability grants** — deny-all filesystem access by default; every read and write is audited

## Quick start

### Requirements

- Python 3.12+
- PostgreSQL (for memory and federation tables)
- Node.js 18+ (only needed if installing from source)

### Install

```bash
# fast core install (add providers when needed)
pipx install tawn

# or install everything at once
pipx install "tawn[full]"

# individual provider extras
pip install "tawn[anthropic]"   # Claude
pip install "tawn[openai]"      # OpenAI / OpenRouter
pip install "tawn[gemini]"      # Google Gemini
pip install "tawn[ollama]"      # local models
pip install "tawn[vectors]"     # pgvector for semantic search
pip install "tawn[mcp]"         # MCP server
```

### Setup

```bash
tawn init                  # creates ~/.tawn/
tawn db setup              # initialises PostgreSQL
tawn web start             # starts the web server at tawn:8787
```

Configure model providers:

```bash
tawn setup                 # interactive wizard — sets API keys, DB, local model
```

Or set keys directly:

```bash
# keys are stored in the OS keyring, never in files
tawn setup                 # interactive
```

### MCP integration (Claude Code)

Add to your `~/.claude/claude.json`:

```json
{
  "mcpServers": {
    "tawn": {
      "command": "tawn",
      "args": ["mcp"]
    }
  }
}
```

Then from any Claude session: `tawn.recall("…")`, `tawn.note("…")`, `tawn.brief("work")`.

## Domain modules

| Domain | What it tracks |
|--------|---------------|
| **work** | Tasks, projects, decisions — per employer |
| **wealth** | Portfolio, net worth, holdings — **read-only, never trades** |
| **research** | Papers, experiments, entity graph, morning brief |
| **academic** | Applications, deadlines, proposal drafts |

Extend with your own domain:

```bash
tawn domain add health     # scaffolds a new domain plugin
```

## CLI reference

```
tawn                       # chat with your twin
tawn note "…"              # append a note to today's raw file
tawn recall "query"        # semantic search over compiled memory
tawn brief work            # daily summary for a domain
tawn compile               # compile raw/ into wiki + vectors
tawn federation sources    # list federated AI tool sources
tawn federation merge      # ingest pending federation records
tawn web start/stop/status # web server control
tawn update                # check and install latest release
tawn config list           # view all settings
```

## Architecture

```
~/.tawn/
├── raw/          # immutable ingested sources
├── wiki/         # compiled markdown knowledge
├── federation/   # AI tool exports + adapters
├── grants.yaml   # capability grants (deny-all default)
└── audit.log     # every write, every cross-domain action
```

API server binds to `127.0.0.1` only. Wealth core is read-only. No withdrawal credentials ever stored.

## License

MIT — see [LICENSE](LICENSE).
