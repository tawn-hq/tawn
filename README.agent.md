# Tawn — Personal Digital Twin

> **Tawn = taw + own.** *The twin you own.*
> A local-first, agent-agnostic context core for one person's work, wealth, research, and academic life. The name is deliberate: **taw** (ת) — *the mark, the bookend, the twin* — the last letter of the Semitic abjad answering aleph's first, and the user's own initial (T); **+ own** — your data, your machine, your intelligence, owned by you. *taw / two / twin*, and now yours.
>
> **This file is the canonical instruction surface.** Any agent (Claude Code, Antigravity, Gemini CLI, Cursor, Cline, Codex) that reads `AGENTS.md` should read *this*. It is portable by design: no agent owns it, every agent uses it.
>
> **Humans installing Tawn:** see [`INSTALL.md`](INSTALL.md).

---

## 0. TL;DR for an agent reading this cold

You are operating as a surface of **Tawn**, the user's personal digital twin. Before acting:

1. **Load identity** from §1 — who the user is and what they're working on.
2. **Consult the memory core** (§3) — the shared brain lives in `~/.tawn/` and the Obsidian vault. Prefer it over re-asking.
3. **Stay in your domain lane** (§4) — work, wealth, research, or academic.
4. **Obey the governance rules** (§8) — read-only on money, human-in-loop on anything that sends, submits, or spends.
5. **Write back** what you learn (§3.4) so the next agent inherits it.

---

## 1. Identity — the contextual memory seed

This section is the user's standing context. Keep it short, true, and current. Stale context is worse than none.

> **Maintenance rule:** this block is edited by a human (or a supervised agent) only. It is the one place the twin is allowed to assert "facts about me."

---

## 2. Architecture overview

Tawn is **seven layers**. Data flows up; requests flow down; each layer only talks to its neighbours.

```
┌─────────────────────────────────────────────────────────────┐
│  7. INTERFACE      CLI (tawn) · web dashboard · Telegram     │
├─────────────────────────────────────────────────────────────┤
│  6. ORCHESTRATION  router agent → domain sub-agents → tools   │
├─────────────────────────────────────────────────────────────┤
│  5. DOMAINS        💼 work · 💰 wealth · 🔬 research · 🎓 academic│
│                    + pluggable: drop in a 5th anytime (§4 ➕)     │
├─────────────────────────────────────────────────────────────┤
│  4. MEMORY CORE    contextual · knowledge(wiki) · operational │
│                    + entity graph + MEMORY FEDERATION (§3)    │
├─────────────────────────────────────────────────────────────┤
│  3. DATA           SQLite/Postgres · vectors · markdown · enc │
├─────────────────────────────────────────────────────────────┤
│  2. INTEGRATION    MCP: Gmail·Cal·Drive·GitHub·Zotero·NGX·CSV │
├─────────────────────────────────────────────────────────────┤
│  1. INFRA          Ollama (local) + cloud BYOK router         │
│                    systemd · encryption · audit log · backup  │
└─────────────────────────────────────────────────────────────┘
```

**Model strategy (hybrid):** local model (Qwen/Llama via Ollama) handles routine/private work; the hard ~20% routes to a frontier model via your own key. Sovereign by default, powerful when it matters.

---

## 3. Memory Federation — the heart of Tawn

This is what makes Tawn *yours* and not just another assistant. It unifies **Obsidian** + every agent's local memory into one core, then projects that core back out so all agents share one brain.

### 3.1 Sources — what gets federated

| Source | What it holds | Location | Sync |
|---|---|---|---|
| **Obsidian vault** | Notes, research, wiki, daily logs | `~/Obsidian/Tawn/` (markdown) | **live** (bi-directional) |
| **Claude Code** | Project rules, decisions | `CLAUDE.md`, `~/.claude/` | **live** read + write |
| **Antigravity** | Rules, skills, workflows | `.agents/rules,skills,workflows/`, `~/.gemini/config/skills/` | **live** read + write |
| **Gemini CLI (agy)** | Instructions, skills | `AGENTS.md`, `~/.gemini/` | **live** |
| **Cursor / Cline / Copilot** | Editor rules | `.cursor/rules/`, `.clinerules`, `AGENTS.md` | **live** |
| **AI cloud app memories** | Chat-derived memory from all major models (claude.ai, ChatGPT/OpenAI, Gemini app, …) | cloud | **export → ingest** (periodic) |
| **Local files / repos** | Code, papers, statements | filesystem | **indexed** (read-only) |

> **Honesty boundary:** local agent files are *live-federatable* — Tawn reads and writes them. Cloud app memories (claude.ai, Gemini app) are **not on disk**, so they are exported on a schedule and ingested. The twin treats them as snapshots, not live state.

### 3.2 Canonical store — one source of truth

```
~/.tawn/
├── core.db                 # SQLite — structured: accounts, tasks, entities, snapshots
├── vectors/                # embeddings for semantic search (RAG)
├── wiki/                   # compiled markdown knowledge (Karpathy LLM-Wiki pattern)
│   ├── people/  topics/  projects/  decisions/
├── domains/                # pluggable life-areas — add a 5th anytime (§4 ➕)
│   ├── work/  wealth/  research/  academic/   # the first four, shipped
│   └── <your-next-domain>/                    # health, scholarship, creative…
├── raw/                    # immutable ingested sources (never edited)
├── federation/
│   ├── inbox/              # exported cloud memories land here for ingest
│   ├── adapters/           # per-agent read/write mappers
│   └── AGENTS.canonical.md # the master instruction surface (this file's runtime twin)
├── config.yaml             # accounts, vault path, model routing (git-ignored)
├── grants.yaml             # capability grants — deny-all default (git-ignored, integrity-checked)
├── grants.yaml.sha256      # integrity sidecar; refresh via `tawn grant confirm`
└── audit.log               # every write + every cross-domain action
```

### 3.3 The federation loop (runs on a `systemd` timer)

```
  cloud exports ─┐
                 ▼
  [ ingest ] → raw/ ──► [ compile ] → wiki/ + vectors/ + core.db
                 ▲                              │
  local agent ───┘                              ▼
  memory files                         [ project ] → write canonical
                                        AGENTS.md + per-agent adapters
                                        back into each tool's location
```

1. **Ingest** — pull from every source in §3.1 into immutable `raw/`.
2. **Compile** — an agent compiles raw sources into the cross-referenced `wiki/`, refreshes vectors, and updates structured rows in `core.db`. (Each new source is cross-linked against everything already there, so the 50th note sharpens the 1st.)
3. **Project** — regenerate the canonical `AGENTS.md` and write tool-specific adapters (`CLAUDE.md`, `.agents/rules/tawn.md`, `.cursor/rules/tawn.mdc`, …) so **every agent sees the same brain**.

### 3.4 Write-back contract (so agents feed the twin)

When any agent learns something durable (a decision, a new entity, a fact), it appends a structured note to `~/.tawn/raw/agent-notes/<date>.md`:

```md
---
type: decision | fact | entity | task
domain: work | wealth | research | academic
confidence: high | medium | low
source: <agent name + session>
---
<one-paragraph statement in the user's voice>
```

The next federation pass compiles it into the wiki and graph. **Agents never write directly to `wiki/` or `core.db`** — only to `raw/`, which the compile step validates.

---

## 4. Domain modules

Each domain is a focused agent with its own tools and views. All read/write the shared core. The payoff is cross-domain: a **PhD proposal** (academic) pulls evidence from **papers** (research) and **shipped systems** (work), while the **funding plan** reads your **runway** (wealth).

### 💼 Work
- Task & meeting capture, auto-tagged by employer (DBA / Obscura / Certin).
- Project context memory: decisions, blockers, threads — survives across sessions.
- Code/repo context via GitHub MCP.
- Weekly review: what moved, what's stuck.

### 💰 Wealth — *read-only, always*
- Aggregate NGX + USD + land + cash into one net-worth view.
- Allocation-drift alerts vs the blueprint's target split.
- NGX dividend-date + earnings reminders; FX moves.
- **The core never holds withdrawal-capable credentials and never auto-trades.**
  Acting on money is possible only through an opt-in, user-installed integration
  (§4 plug-in contract) with `requires_human_gate: true`, an explicit grant, and
  per-action confirmation. A fresh install is fully read-only.

### 🔬 Research
- Literature ingest → compiled wiki with backlinks (reuse ClauseWise/AfriVTON RAG stacks).
- Idea cross-referencing & contradiction flagging.
- Experiment/result logs tied to projects.
- Morning brief: relevant new arXiv + citations.

### 🎓 Academic (MSc / PhD)
- Application + deadline tracker per program.
- Supervisor / lab / funding dossiers.
- Proposal & SOP drafting grounded in real work + research.
- Zotero-linked reading list → feeds the Research module.

### ➕ Extending Tawn — the domain plug-in contract

The four domains above are the **first four registered plug-ins, not a fixed set.** Tawn is open by design: add a fifth — health, scholarship, creative, relationships, fitness, anything — by dropping a folder. No core rewrite, no schema migration of the others.

A domain is a self-contained directory:

```
~/.tawn/domains/<name>/
├── manifest.yaml      # identity + how it registers
├── agent.md          # the domain agent's instructions (loaded as a Skill)
├── schema.sql        # OPTIONAL — domain-specific tables
├── tools/            # OPTIONAL — MCP tools / scripts the agent may call
└── views/            # OPTIONAL — dashboard cards
```

`manifest.yaml` is the whole contract:

```yaml
name: health
icon: "🩺"
color: "#EF4444"
description: "Fitness, sleep, nutrition, medical tracking."
scopes:
  read:  [health.*]
  write: [health.notes]        # everything else read-only by default
requires_human_gate: false     # true if it can send / spend / submit
feeds: [research]              # OPTIONAL cross-domain links into the graph
```

**Registration is automatic.** On startup the orchestrator discovers every `domains/*/manifest.yaml`; the entity graph gains the new `domain` tag; and the federation loop (§3.3) begins compiling the domain's notes into `wiki/` and `core.db`. The three interface verbs (§6) work immediately — `recall("…","health")`, `note(...)`, `brief("health")` — because they take the domain as a parameter, so a new domain plugs into the same contract with zero rewiring.

Scaffold one in seconds:

```
tawn domain add health      # creates the folder + a starter manifest.yaml + agent.md
tawn domain list            # show registered domains
tawn domain disable health  # mute without deleting
```

**Inherited governance (a new domain cannot opt out):**
- Read-only unless it explicitly declares `write` scopes.
- It **cannot** widen another domain's permissions or touch the wealth withdrawal boundary.
- Anything that sends, spends, or submits must set `requires_human_gate: true`.
- Its writes land in `audit.log` like every other domain.

> The point: your twin grows with your life. The first four cover today; the plug-in contract means year-three Tawn can hold domains you haven't thought of yet — without ever rebuilding the core.

---

## 5. Entity graph — why one twin beats separate tools

`core.db` holds a lightweight graph so a single real-world thing is one node across domains:

```
person:"Testimony Adekoya"  ──collaborator──► project:"NaijaReview"   (work)
                            ──co-author─────► paper:"AfriVTON-Bench"  (research)
                            ──contact───────► thread:"CV help"        (academic)
topic:"RAG"                 ──appears_in────► [ClauseWise, morning-brief, PhD-SOP]
```

Tables (start minimal, grow later):

```sql
entities(id, type, name, aliases_json, domains_json)
edges(src_id, rel, dst_id, weight, asof)
notes(id, entity_id, body, domain, source, confidence, asof)
snapshots(id, domain, asof, state_json)   -- e.g. net-worth state per sync
```

---

## 6. Agent interface contract — the portable part

Any agent uses Tawn through three verbs. Implement once (FastAPI over `core.db` + `vectors/`, bound to `127.0.0.1`), expose as MCP tools:

| Verb | Meaning | Example |
|---|---|---|
| `tawn.recall(query, domain?)` | semantic + structured read from the core | `recall("my NGX banking exposure", "wealth")` |
| `tawn.note(payload)` | write-back to `raw/` (see §3.4) | log a decision after a work session |
| `tawn.brief(domain)` | compiled daily/weekly summary | `brief("research")` → today's arXiv + open threads |

Because these are MCP tools and the instructions live in `AGENTS.md`, the **same contract works in Claude Code, Antigravity, Gemini CLI, Cursor, and Cline** with zero per-tool rewriting.

---

## 7. Build sequence — starting today

| Stage | Ship | Effort |
|---|---|---|
| **0 · shipped** | `~/.tawn/` skeleton + deny-all `grants.yaml` (integrity-checked) + FS-mediation layer + audit log + `tawn init` / `tawn grant` CLI | done |
| **1** | Wealth v0: aggregator → `core.db` snapshots → local dashboard + Ollama analyst (read-only) | weekend |
| **2** | Memory core: Obsidian live sync + `wiki/` compile + vectors + entity graph | 1–2 wks |
| **3** | Federation loop: ingest agent memories + cloud-export inbox + project canonical out | 1–2 wks |
| **4** | Research module (reuse existing RAG) → highest ROI after wealth | 1–2 wks |
| **5** | Work module + MCP (Gmail/Cal/GitHub/Slack), project-tagged capture | 2 wks |
| **6** | Academic module (deadlines, dossiers, proposal drafting) | 1 wk |
| **7** | Orchestration router + extra surfaces (web → Telegram) | ongoing |

> **Today's concrete first move:** create `~/.tawn/`, drop this file in as the canonical `AGENTS.md`, and point Claude Code + Antigravity at it. Tawn is "alive" the moment two agents read the same brain.

---

## 8. Governance — non-negotiable

- **Local-first & encrypted at rest.** `config.yaml` and `core.db` never enter git; secrets live in an isolated store, never in a model's context or a plaintext config.
- **Wealth core is read-only.** No withdrawal credentials, no auto-trading in the
  core — ever. Execute/spend exists only as an opt-in, gated, audited third-party
  integration, never bundled or on by default.
- **Human-in-the-loop gate** on anything that sends a message, submits an application, or spends money.
- **Audit everything.** Every write to the core and every cross-domain action lands in `audit.log`.
- **API bound to `127.0.0.1`.** The twin is never exposed to the network.
- **Staleness is failure.** The federation loop must run on schedule; a twin that drifts misleads every agent that trusts it.

---

## 9. Prior art Tawn stands on (don't rebuild plumbing)

- **Ollama / Jan.ai** — local model runtime.
- **Goose (MCP-native agent runtime)** — orchestration + integration.
- **Karpathy LLM-Wiki pattern / claude-obsidian** — the `wiki/` knowledge layer.
- **Khoj** — self-hostable research second-brain (Research module reference).
- **AGENTS.md standard + `npx skills`** — the cross-agent instruction surface that makes federation portable.

What's *yours*: the four-domain life twin + the entity graph + the memory-federation loop. Nobody ships that as one system — that's the build.

---

*Tawn v0 spec. Edit §1 by hand; let the federation loop maintain the rest. ℵ → ת*
