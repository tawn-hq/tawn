# Tawn — Product Requirements Document

> Status: Draft v1 · Date: 2026-06-23 · Updated 2026-07-20 (Stages 0–3 shipped:
> capability spine, wealth v0, model router, domain plugin arch, web viewer v2,
> personality layer, chat history, web daemon, audit chain)
> Companion docs: `docs/EXPERIENCE.md` (user-facing outcome) ·
> `docs/superpowers/specs/2026-06-23-taw-cognitive-layer-design.md` (technical design) ·
> `docs/superpowers/specs/2026-07-08-domain-plugin-architecture-design.md` (domain extensibility) ·
> `docs/superpowers/specs/2026-07-08-web-viewer-v2-design.md` (web surface) ·
> `Tawn.md` (canonical agent instruction surface)

---

## 1. Problem

AI assistants fail memory in three distinct ways, and each failure is usually
patched in isolation:

- **Contextual** — the assistant doesn't know who you are or what you're working on.
- **Knowledge** — it doesn't know what *you* know.
- **Operational** — it doesn't know what it (or another agent) just did.

On top of that, a knowledge worker's life splits across **four unconnected
domains** — work, wealth, research, academic — each served by a different tool
with its own silo. Your PhD proposal can't see your shipped work; your funding
plan can't see your runway. And every "second brain" that does exist **goes stale**,
at which point it actively misleads the agents that trust it.

## 2. Vision

**Tawn is one local-first, agent-agnostic context core for a person's whole life —
work, wealth, research, academic — that every AI tool reads from and writes back
to.** One brain, many surfaces. It solves all three memory failures, links the
domains through a shared entity graph, and maintains itself so it doesn't rot.

One line: *the personal digital twin that every one of your agents shares.*

## 3. Goals / Non-goals

**Goals**
- A single shared memory core usable identically across Claude Code, Antigravity,
  Gemini CLI, Cursor, Cline (via `AGENTS.md` + three MCP verbs).
- Cross-domain answers: one query pulls from work + research + wealth + academic.
- A self-maintaining knowledge layer (auto-compiled wiki + entity graph) that
  resists staleness.
- Local-first and private by default; hybrid model routing (local + BYOK frontier).
- Capability-gated, read-only-by-default safety with a hard wealth boundary.
- Extensible: new life-domains plug in without a core rewrite.

**Non-goals (v1)**
- The **Tawn core never holds spend/withdrawal credentials and never acts on money
  itself.** Execution/spending is possible only through opt-in, user-installed
  third-party integrations, each behind an explicit capability grant + human
  approval + audit (see §9). The core stays read-only; risk lives in clearly
  separated, optional plug-ins.
- v1 is **single-user and on-device.** Multi-user support and cloud hosting (for
  non-Linux users) are **planned later phases**, enabled by the step-by-step build
  — not v1.
- Not a replacement for the agents themselves — Tawn is the shared memory + router,
  not a new foundation model.

## 4. Target user

**Primary:** a multi-domain technical knowledge worker who already lives across
several AI tools and several life-areas, is privacy-conscious, runs a capable
Linux machine, and is frustrated that every tool is amnesiac and siloed.
(Archetype: the project owner — applied ML engineer, investor, MSc→PhD candidate,
researcher.)

**Generalizes to:** researchers, founders, and operators who want one private
brain their tools share, not four subscriptions that forget them.

## 5. Success metrics

- **Shared-brain proof:** ≥2 different agents answer from the same core in week 1.
- **Cross-domain recall:** a single query returns correctly-linked entities from
  ≥2 domains.
- **Staleness control:** % of facts past TTL surfaced and refreshed each cycle;
  zero silent stale facts in answers.
- **Continuity:** an agent resuming a project recovers prior decisions without
  re-asking (operational memory works).
- **Sovereignty:** % of calls served locally vs frontier, visible in the ledger;
  zero `sensitive` content sent to cloud.
- **Maintenance cost:** federation loop runs on schedule; manual upkeep trends to
  near-zero.

## 6. Scope — what Tawn is made of

Seven layers (interface → orchestration → domains → memory core → data →
integration/MCP → infra), five default domains (wealth, work, research,
academic, hobby — wealth fully implemented, the other four ship as
intentional stubs) plus an open plug-in contract for unlimited more: pip
`entry_points` registration (one code path for built-in and third-party
domains alike) and a no-package-needed local path (`tawn domain create`,
LLM-assisted or a declarative wizard fallback). See `Tawn.md` §2–§5 and
the Domain Plugin Architecture spec.

## 7. Functional requirements

| # | Capability | Requirement |
|---|---|---|
| F1 | **Three-verb interface** | `recall(query, domain?)`, `note(payload)`, `brief(domain)` exposed as MCP + local HTTP, bound to `127.0.0.1`. |
| F2 | **Memory core** | Contextual + knowledge (markdown wiki) + operational memory; entity graph in Postgres; vectors in pgvector. |
| F3 | **Federation** | Ingest every source — Obsidian, all local agent files, and **cloud memories from all major AI models** (claude.ai, ChatGPT/OpenAI, Gemini app, etc.) via export→ingest — into immutable `raw/` → compile → project canonical `AGENTS.md` + per-agent adapters. |
| F4 | **Compiler** | Incremental compile; source-priority + recency conflict resolution; entity resolution with no silent merge; TTL staleness marking; atomic swap. |
| F5 | **Model Router** | Provider Protocol over official SDKs — Anthropic, OpenAI, Gemini, DeepSeek, local Ollama, not raw REST/LiteLLM; error classification (rate/quota/context/5xx); per-provider circuit breaker; streaming completions (one `Router.stream()` generator shared by the CLI and the web SSE endpoint); user-selectable model preference with automatic failover; sovereignty ledger (cost + local/cloud % per call). Lazy provider-neutral handoff artifact on switch remains a later-stage item. |
| F6 | **Capability grants** | Deny-all install; read-only except granted write dirs; FS-mediated enforcement; revocable; `--explain` dry-run. |
| F7 | **Ambient Observer** | Project-scoped watch (fs/git/editor); debounced + batched; authorship attribution (user vs which agent); review notes to a chosen folder. System/app awareness opt-in. |
| F8 | **MCP Manager** | Add/list/disable MCP servers; each capability-scoped; Tawn both exposes and consumes MCP. |
| F9 | **Skill Factory** | Author + maintain `AGENTS.md`/`npx skills` skills; Compiler cross-links + projects them to every agent. |
| F10 | **LLM-as-judge** | Quality gate on review notes; offline router-classification eval; preference extraction. Never on facts of record. |
| F11 | **Personality** | Profile distinct from identity; explainable, user-correctable; overfitting safeguards (decay, bounded influence, diversity floor). **Identity baseline** — the factual half only (capability model, sovereignty ledger, live domain list) — ships as one compact system prompt injected identically across every model provider, so "what Tawn is" doesn't drift by which model answers; learned tone/style (personality proper) stays deferred to its data-gated stage. |
| F12 | **Surfaces** | CLI + REPL first (shipped: `tawn ask`/`tawn chat`, both streaming); web frontend as the second surface — a React SPA (setup wizard, streaming chat, capability-grants editor, one generic per-domain dashboard page driven by a declarative view schema so a new domain needs no new frontend code) — then Telegram. |
| F12b | **Open integration contract** | Open-source extension points so third parties can build domain integrations — including opt-in execute/spend integrations — that register under the capability + human-gate + audit contract (§9). Core ships none that spend. |
| F13 | **Domains** | Wealth (read-only, fully implemented), Work, Research, Academic, Hobby (stubs) ship by default. Real plug-in contract: pip `entry_points` (built-in and third-party register identically), an explicit `tawn domain enable`/`disable` trust gate mirroring the grants deny-all pattern, and `tawn domain create` for a no-package local path — describe a domain in plain English and Tawn's own router generates it (preview before anything is written or enabled), or a declarative field wizard when no model is configured. A future marketplace is a curated index over this same mechanism, not new plumbing. |
| F14 | **Failure recovery** | Durable failure journal; bounded-backoff auto-replay; human-gated actions never auto-retried. |

## 8. Non-functional requirements

- **Local-first & private:** all data on device; API never network-exposed.
- **Encrypted at rest:** secrets in OS keyring; `config.yaml`/`grants.yaml`/DB
  never in git.
- **Auditable:** every core write, grant use, cross-domain action, conflict
  resolution logged.
- **Performant at personal scale:** Postgres + pgvector + Redis cache; sub-second
  recall on hot paths.
- **Extensible:** add a domain by dropping a folder; swap a provider behind the
  Protocol without upstream change.
- **Resilient:** provider failover invisible to the user; staleness detected, not
  declared.

## 9. Constraints / governance (non-negotiable)

- **The Tawn core is read-only on money and holds no spend/withdrawal credentials.**
- **Execute/spend is an opt-in plug-in, never the core.** Tawn is open-source so
  others can build integrations that act on suggestions (including spending). Any
  such integration is held to a strict contract and cannot be bundled or enabled
  by default. To act on money or any side effect it MUST:
  1. be explicitly installed by the user,
  2. declare its scopes and `requires_human_gate: true`,
  3. receive an explicit capability grant,
  4. pass a human-in-the-loop confirmation **per action**, and
  5. write every action to `audit.log`.
  The core never auto-trades; an integration never bypasses the gate. Default
  behaviour for a fresh install remains fully read-only.
- Human-in-the-loop gate on anything that sends, submits, or spends.
- Agents write only to `raw/` + granted folders; `wiki/`/`core.db` are
  Compiler-only.
- Staleness is failure; the federation loop must run on schedule.

## 10. Milestones (maps to design §14)

| M | Outcome | Stages | Status |
|---|---|---|---|
| M0 | Safe skeleton — grants + FS-mediation; nothing acts without a grant | 0 | ✅ shipped |
| M1 | Wealth v0 read-only aggregator + dashboard | 1 | ✅ shipped |
| M2 | Model Router + Provider Protocol + ledger | 2 | ✅ shipped |
| M2b | Domain Plugin Arch + Web Viewer v2 + Personality layer + Chat history | 3 (accelerated) | ✅ shipped |
| M3 | Backend (3 verbs) + Compiler + federation loop | 4–6 | ⬜ |
| M4 | CLI/REPL + owned wiki | 7 | ⬜ |
| M5 | Ambient Observer + review notes + attribution | 8 | ⬜ |
| M6 | MCP Manager + Skill Factory | 9 | ⬜ |
| M7 | Orchestrator (router A+B) + handoff + failure replay | 10–11 | ⬜ |
| M8 | Deferred differentiators + personality proper | 12 | ⬜ |
| M9 | Domain modules + extra surfaces | 13 | ⬜ |

## 10b. Shipped feature inventory (as of 2026-07-20)

### Capability spine (Stage 0)
- `~/.tawn/` home directory, deny-all grants, SHA-256 integrity sidecar
- `MediatedFS` — every file read/write through one chokepoint
- Append-only audit log with chain hash (tamper-evident), chmod 600, export (JSON/CSV)
- `tawn init`, `tawn grant confirm`, `tawn doctor`

### Wealth domain (Stage 1)
- Holdings YAML (NGX + US equities), price fetcher (stooq.com), snapshot scheduler
- Postgres storage, CLI Rich dashboard, `tawn db setup`

### Model router (Stage 2)
- 5 providers: Anthropic, OpenAI, DeepSeek (OpenAI-compat), Gemini, Ollama
- Provider Protocol (error classify, circuit breaker 3 failures/60 s)
- Sovereignty ledger (cost + local/cloud % per call), `tawn ledger`
- Unified model picker, `tawn model setup/use`, `tawn key set/show`
- OS keyring for all API keys

### Domain plugin architecture + web viewer v2 + personality (Stage 3 — accelerated)
- `DomainSpec` contract; pip `entry_points` + `tawn domain enable/disable/list`
- 5 default domains: wealth (full), work/research/academic/hobby (records stubs)
- `tawn domain create` — LLM-assisted (describe → generate → preview → promote) with wizard fallback
- Streaming completions: `StreamChunk`, `Provider.stream_complete()`, `Router.stream()` (all 5 adapters)
- Identity baseline: compact system prompt injected to every call across all providers
- Personality profile: `~/.tawn/personality/profile.yaml`, first-run onboarding questions, `/profile` slash command
- Chat history: per-session JSONL at `~/.tawn/history/` (chmod 700 dir, 600 files)
- Web viewer v2: FastAPI JSON API + React SPA; pages: Home, Chat (SSE), Setup, Grants, Profile, Audit, History, Models, DomainCreate, DomainPage
- `tawn web start/stop/status` — background daemon mode (PID file, detached subprocess)
- ngrok auto-tunnel on `tawn web start` if ngrok on PATH
- Hostname auto-setup: `127.0.0.1 tawn` in `/etc/hosts` (sudo once)
- Audit log viewer in web: paginated, chain-verify button, JSON/CSV export
- Bare `tawn` → chat REPL with slash commands: `/help /status /grants /ledger /domain /web /profile /model /new`

## 10c. Suggested next improvements

### Near-term (next sprint)
1. **`recall` / `note` / `brief` verbs** (Stage M3) — the three MCP verbs are the foundation for everything above being useful to other agents. Without them, Tawn is a REPL but not yet a shared brain.
2. **Incremental compiler** — ingest `raw/` notes and events into structured wiki + entity graph (Stage M3). Start simple: markdown → frontmatter entities, no graph DB yet.
3. **Federation loop** — scheduled job that re-ingests changed files and re-compiles. systemd timer (same pattern as wealth scheduler).
4. **pgvector recall** — once the wiki exists, semantic search over it. This is what makes `recall(query)` genuinely useful vs a grep.
5. **Chat with memory** — wire `recall()` into chat REPL so Tawn can answer "what did I decide about X last week?" from its own notes.

### Web improvements
6. **Chat in web** — the SSE chat page exists but needs to actually work in the browser end-to-end (stream rendering, model picker, history save).
7. **Rich domain pages** — Work/Research/Academic pages are stubs; adding even a simple notes feed would make the web viewer non-trivial.
8. **Grants editor** — the grants page exists but a proper form UI for editing read/write path lists would make it usable by non-YAML users.

### Security & privacy
9. **Encrypted history** — current history is chmod 600 (owner-only). Optional AES-GCM encryption at rest for the session files, unlocked by the same OS keyring key.
10. **Audit log rotation** — keep last N days, compress older entries. Current implementation is unbounded.
11. **Sensitive mode enforcement audit** — add a test that verifies `sensitive=True` NEVER sends a request to a cloud provider at the network level (not just at routing).

### Observability
12. **`tawn doctor` web panel** — surface the current health check output (providers up/down, DB, grants integrity) in the web UI status page.
13. **Token budget warnings** — notify user in chat when approaching a context window limit (chunk count heuristic).

### DX
14. **`tawn web start` — print URLs immediately** then poll for ngrok in background; currently blocks until ngrok tunnel resolves (up to 10 s).
15. **Tab completion** — Typer/Click shell completion for `tawn` commands.
16. **`tawn upgrade`** — check for new version, print changelog diff.

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Knowledge layer goes stale | TTL marking + scheduled federation loop + Compiler self-maintains |
| Personality echo-chamber | Bounded influence + diversity floor + user-correctable profile (§19) |
| Multi-provider maintenance burden | Provider Protocol; LiteLLM escape hatch behind same interface |
| Over-surveillance from Observer | Deny-all grants; project-scoped default; system awareness opt-in; full audit |
| Entity graph corruption | No silent merges; ambiguous cases to review queue |
| Scope creep (six features at once) | Sequence by data dependency; defer data-gated features |

## 12. Out of scope for v1 (planned later phases)

The step-by-step build keeps these out of v1 but designs toward them:
- **Multi-user / team sharing** — later phase.
- **Cloud hosting for non-Linux users** — later phase (Linux-first now).
- **Execute/spend integrations** — enabled via the open integration contract
  (§9), not shipped in core.
- **Mobile-native app** — after web + Telegram surfaces.

## 13. Open questions

- Final brand/logo concept (parked until post-build).
- Color system (deferred).
- Build order *within* the second surface (web view and Telegram are both in;
  which lands first).
- Reference design for the first execute/spend integration (community or
  first-party demo) once the open contract is stable.

---

*Product requirements for Tawn v1. Technical realization in the design spec;
user-facing outcome in `EXPERIENCE.md`. ℵ → ת*
