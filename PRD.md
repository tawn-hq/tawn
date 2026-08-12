# Tawn — Product Requirements Document

> Status: Draft v2 · Date: 2026-06-23 · **Updated 2026-07-29** — v0.3.0 live on
> PyPI; Stages 0–10 shipped (capability spine, wealth v0, model router, domain
> plugins, web viewer v2, memory core, federation loop, memory legibility,
> observability, ambient observer, MCP manager + skill factory); 1,171 tests
> passing; security review REVIEW-2026-07-27 completed and remediated.
>
> **This revision adds the authority layer** — the chapter that takes Tawn from a
> memory layer to a memory *and authority* layer — plus durability requirements
> that were missing entirely.
>
> Companion docs: `docs/EXPERIENCE.md` (user-facing outcome) ·
> `docs/ROADMAP.md` (build stages, in priority order) ·
> `docs/REVIEW-2026-07-27.md` (security review) ·
> `docs/superpowers/specs/2026-06-23-taw-cognitive-layer-design.md` (technical design) ·
> `Tawn.md` (canonical agent instruction surface)
>
> Chain-bound work — value rails, wallets, on-chain identity — is **out of scope
> for this document** and specified separately as an optional layered package.

---

## 1. Problem

### Vendor memory is table stakes, and it is the wrong shape

**The premise of v1 of this document is obsolete and is corrected here.** v1 argued
that assistants fail memory in three ways — contextual, knowledge, operational.
Per-vendor memory has since shipped across Anthropic, OpenAI and Google, so "the
assistant does not remember you" is no longer true and is not the opportunity.

Those three categories remain the useful vocabulary (F2 is built on them), but the
claim has to change. Vendor memory covers **some contextual memory**, a **thin slice of
knowledge memory** — whatever was typed into a chat window — and **no operational
memory whatsoever**. Four structural failures follow, and none of them is an oversight
a vendor is likely to fix:

- **No shared substrate.** Each store is scoped to one vendor's surface. There is no
  export format another agent could consume, and no commercial incentive to create
  one — memory is what makes a vendor's product sticky, so interoperability is against
  their interest. Cross-agent context is therefore re-derived per tool per session, at
  direct token cost.
- **Not user-owned.** The store is hosted, coupled to a subscription, not fully
  inspectable and not portable. Memory the user cannot move or audit is not a
  foundation they can build on.
- **Wrong corpus.** These stores index conversation. A user's actual material —
  repositories, notes, documents, the session transcripts their own agents write to
  disk — sits outside them entirely.
- **No operational record.** Nothing records which agent mutated what. A second agent
  resuming a project has no account of the first agent's actions, and neither does the
  user.

On top of that, a knowledge worker's life splits across **four unconnected
domains** — work, wealth, research, academic — each served by a different tool
with its own silo. Your PhD proposal can't see your shipped work; your funding
plan can't see your runway. And every "second brain" that does exist **goes stale**,
at which point it actively misleads the agents that trust it.

### A failure of a different kind

**Everything above concerns what an agent knows. This one concerns what it may do, and
it has become the urgent problem since v1 of this document.** Agents no longer
just read — they act. They edit files, run commands, call tools, and increasingly
move money. The permission model available to them is all-or-nothing: a user either
trusts an agent with their machine or does not use it. There is no artifact stating
what an agent may do, no pre-flight decision, and no record afterwards of what
happened and under whose authority. **Memory without authority is half a product**:
knowing what you know is useless if you cannot govern what acts on it.

## 2. Vision

**Tawn is one local-first, agent-agnostic core for a person's whole life — work,
wealth, research, academic — that every AI tool reads from, writes back to, and
asks permission of.** One brain, many surfaces, one authority boundary.

It is the shared substrate no vendor has an incentive to build: user-owned rather than
hosted, indexing the user's real material rather than their chat history, recording
what every agent did as well as what it knows, and governing what they may do next. It
links the domains through a shared entity graph and maintains itself so it doesn't rot.

One line: *the personal digital twin that every one of your agents shares — and
answers to.*

## 3. Goals / Non-goals

**Goals**
- A single shared memory core usable identically across Claude Code, Antigravity,
  Gemini CLI, Cursor, Cline (via `AGENTS.md` + three MCP verbs).
- Cross-domain answers: one query pulls from work + research + wealth + academic.
- A self-maintaining knowledge layer (auto-compiled wiki + entity graph) that
  resists staleness.
- Local-first and private by default; hybrid model routing (local + BYOK frontier).
- **One authority boundary for every action class** — files, shell, network, tools,
  models, domains — decided before the action and provable after it.
- **Per-domain authority:** each domain carries its own envelope of what may act on
  it, within what limits.
- **A permission answer any agent can ask for**, not one Tawn alone consumes.
- **Durability:** the corpus survives losing the machine.
- Extensible: new life-domains and new action classes plug in without a core rewrite.

**Non-goals (v1)**
- The **Tawn core never holds spend/withdrawal credentials and never acts on money
  itself.** Execution/spending is possible only through opt-in, user-installed
  third-party integrations, each behind an explicit capability grant + human
  approval + audit (see §9). The core stays read-only; risk lives in clearly
  separated, optional plug-ins. **The authority layer strengthens rather than
  relaxes this** — it gives that contract a real policy engine and evidence trail
  to be held to, instead of documentation alone.
- **No chain, wallet, or token dependency in core.** Anything on-chain is an
  optional separate package; removing it costs no capability.
- **Domains are boundaries, not autonomous agents.** A domain has an identity, a
  budget and limits. It has no initiative and never acts on its own behalf.
- v1 is **single-user and on-device.** Multi-user support and cloud hosting are
  planned later phases, not v1.
- Not a replacement for the agents themselves — Tawn is the shared memory, router
  and authority boundary, not a new foundation model.

## 4. Target user

**Primary:** a multi-domain technical knowledge worker who already lives across
several AI tools and several life-areas, is privacy-conscious, runs a capable
Linux machine, and is frustrated that each tool's memory stops at that tool's
boundary — and that none of it is theirs to keep.
(Archetype: the project owner — applied ML engineer, investor, MSc→PhD candidate,
researcher.)

**Second, newly explicit:** anyone running agents that *act* — who needs a stated,
enforceable answer to "what is this thing allowed to do on my machine?" and a record
they can inspect afterwards.

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
- **Authority coverage:** every action class routes through one decision point;
  zero code paths reach user content without a policy check.
- **Provable history:** any past action can be shown with its decision, reason and
  actor; log integrity verifiable by someone other than the owner.
- **Recoverability:** a full restore onto a clean machine succeeds from backup
  alone, tested — not assumed.
- **External adoption:** measured PyPI installs, and ≥1 non-author contributor.

## 6. Scope — what Tawn is made of

Seven layers (interface → orchestration → domains → memory core → data →
integration/MCP → infra), five default domains (wealth, work, research,
academic, hobby) plus an open plug-in contract for unlimited more: pip
`entry_points` registration (one code path for built-in and third-party
domains alike) and a no-package-needed local path (`tawn domain create`,
LLM-assisted or a declarative wizard fallback).

**An eighth concern cuts across all of them: the authority layer.** It is not a
layer in the stack so much as a boundary every layer crosses — one policy decision
point, one evidence trail, one attribution model. It is the generalisation of the
capability spine that has been in the design since Stage 0.

## 7. Functional requirements

F1–F14 are stable identifiers, referenced from specs and the roadmap. F15–F21 are
new in this revision.

| # | Capability | Requirement |
|---|---|---|
| F1 | **Three-verb interface** | `recall(query, domain?)`, `note(payload)`, `brief(domain)` exposed as MCP + local HTTP, bound to `127.0.0.1`. |
| F2 | **Memory core** | Contextual + knowledge (markdown wiki) + operational memory; entity graph in Postgres; vectors in pgvector. |
| F3 | **Federation** | Ingest every source — Obsidian, all local agent files, and **cloud memories from all major AI models** (claude.ai, ChatGPT/OpenAI, Gemini app, etc.) via export→ingest — into immutable `raw/` → compile → project canonical `AGENTS.md` + per-agent adapters. |
| F4 | **Compiler** | Incremental compile; source-priority + recency conflict resolution; entity resolution with no silent merge; TTL staleness marking; atomic swap. Durability: interleaved commits so a long run stays visible and a failure cannot lose the batch. |
| F5 | **Model Router** | Provider Protocol over official SDKs — Anthropic, OpenAI, Gemini, DeepSeek, local Ollama, plus OpenRouter/Kimi/Qwen/Groq/Grok; error classification (rate/quota/context/5xx); per-provider circuit breaker; streaming completions shared by CLI and web SSE; user-selectable model preference with automatic failover; sovereignty ledger (cost + local/cloud % per call) with **unpriced calls marked unpriced, never counted as free**. |
| F6 | **Capability grants** | Deny-all install; read-only except granted write dirs; single-chokepoint enforcement; revocable; `--explain` dry-run; SHA-256 sidecar integrity with explicit `grant confirm`. |
| F7 | **Ambient Observer** | Project-scoped watch (fs/git/editor); debounced + batched; **tiered authorship attribution** (git identity → agent session logs → timing heuristics) where each result carries its confidence and low confidence reads "likely" rather than being asserted; review notes to a granted folder only. |
| F8 | **MCP Manager** | Add/list/disable MCP servers; each capability-scoped; Tawn both exposes and consumes MCP. Self-configuration tools stage but never enable. |
| F9 | **Skill Factory** | Author + maintain `AGENTS.md`/`npx skills` skills; Compiler cross-links + projects them to every agent. |
| F10 | **LLM-as-judge** | Quality gate on review notes; offline router-classification eval; preference extraction. Never on facts of record. |
| F11 | **Personality** | Profile distinct from identity; explainable, user-correctable; overfitting safeguards (decay, bounded influence, diversity floor). Identity baseline — the factual half — ships as one compact system prompt injected identically across every provider. |
| F12 | **Surfaces** | CLI + REPL first; React SPA web frontend second (setup wizard, streaming chat, grants editor, generic per-domain dashboard from a declarative view schema); then Telegram. |
| F12b | **Open integration contract** | Open extension points so third parties can build domain integrations — including opt-in execute/spend integrations — registering under the capability + human-gate + audit contract (§9). Core ships none that spend. |
| F13 | **Domains** | Wealth (read-only), Work, Research, Academic, Hobby ship by default. Plug-in contract via pip `entry_points`, an explicit `tawn domain enable/disable` trust gate mirroring grants deny-all, and `tawn domain create` for a no-package local path. |
| F14 | **Failure recovery** | Durable failure journal; bounded-backoff auto-replay; human-gated actions never auto-retried. |
| **F15** | **Policy engine** | One decision point for every action class. A typed action in, `Decision(allowed, reason, matched_rule)` out. Filesystem mediation becomes one caller among several rather than the only gate. Every refusal carries a reason a human can act on. |
| **F16** | **Registrable action types** | Action classes and `grants.yaml` schema blocks contributed by plugins through the same `entry_points` mechanism domains use. Core remains unaware of any specific action domain, so new authority surfaces need no core change. |
| **F17** | **Domain principals** | Each domain is an addressable principal carrying its own authority envelope — grants, model allowlist, tool allowlist, spend ceiling, sensitivity policy — and its own segment of the evidence trail. Generalises wealth's read-only constraint, in place since Stage 1. **A principal is a boundary, not an actor**: it has limits and an identity, never initiative. |
| **F18** | **Evidence bundles** | Per action, a signed portable envelope: action requested, decision and reason, hash of inputs (never contents), actor plus attribution confidence, audit chain head, signature. Verifiable without access to the corpus. |
| **F19** | **Policy over MCP** | `may_i(action)` and `evidence(id)` exposed over MCP so any agent — Claude Code, Cursor, anything speaking the protocol — can ask permission and receive an auditable answer. Tawn becomes the permission oracle for the agents around it, not only for itself. |
| **F20** | **Verifiable log integrity** | An `AnchorTarget` port publishing one chain head per interval so integrity is checkable by someone other than the owner. OpenTimestamps as the default — no wallet, no chain integration, no account. Content never leaves the machine. |
| **F21** | **Durability + recovery** | `BackupStore` interface with client-side encryption where the user holds the key; local-directory and S3-compatible backends; restore onto a clean machine as a tested path. Key recovery via threshold secret sharing (k-of-n guardians or devices) plus an inheritance path, so a forgotten passphrase does not destroy the corpus permanently. |

## 8. Non-functional requirements

- **Local-first & private:** all data on device; API bound to loopback and never
  network-exposed without an explicit flag.
- **Encrypted at rest:** secrets in OS keyring; `config.yaml`/`grants.yaml`/DB
  never in git. API keys never in files, never in the ledger, never in error
  messages.
- **Auditable:** every core write, grant use, cross-domain action, conflict
  resolution and policy decision logged; the chain verifiable, and verification
  names the exact point a chain breaks.
- **Durable:** no single machine failure loses the corpus. Restore is a tested
  procedure, not an assumption. *(This requirement was absent from v1 and is the
  most serious omission this revision corrects.)*
- **Honest under uncertainty:** low-confidence attribution reads "likely";
  unpriceable model calls read "unpriced". The system never launders a guess into a
  fact.
- **Injection-resistant:** untrusted content — documents, tool results, repository
  files — cannot reach a privileged action without explicit confirmation.
- **Performant at personal scale:** Postgres + pgvector; sub-second recall on hot
  paths; proven at ~12,300 chunks / 11,988 entities / 12,878 edges.
- **Extensible:** add a domain by dropping a folder; add an action class by
  registering it; swap a provider behind the Protocol without upstream change.
- **Resilient:** provider failover invisible to the user; staleness detected, not
  declared.
- **Money is `Decimal` end to end**, serialized as strings. Floats are forbidden on
  monetary paths.

## 9. Constraints / governance (non-negotiable)

- **The Tawn core is read-only on money and holds no spend/withdrawal credentials.**
- **Execute/spend is an opt-in plug-in, never the core.** Any such integration MUST:
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
- **Nothing marked `sensitive` leaves the machine.** Candidate filtering happens
  before provider selection, never after.
- **Commits are the maintainer's to run.** An agent proposes; it does not commit.
- **Licensing (decided 2026-07-29):** anything that runs on your own machine
  against your own data is MIT, permanently — including the whole authority layer.
  Only hosted convenience (backup/sync, attestation service) and administering Tawn
  across other people (team deployment, SSO, org reporting) may cost money.
  Self-hosting must always be a complete substitute. The authority layer is
  deliberately **not** the commercial tier: it *is* the capability spine already
  released under MIT, and a proprietary auditor cannot be trusted by the people
  relying on it.

## 10. Milestones

Historical milestones M0–M9 mapped to the original stage numbering and are retained
for continuity. Current state and forward plan below.

| M | Outcome | Stages | Status |
|---|---|---|---|
| M0 | Safe skeleton — grants + FS-mediation; nothing acts without a grant | 0 | ✅ shipped |
| M1 | Wealth v0 read-only aggregator + dashboard | 1 | ✅ shipped |
| M2 | Model Router + Provider Protocol + ledger | 2 | ✅ shipped |
| M2b | Domain Plugin Arch + Web Viewer v2 + Personality + Chat history | 3 | ✅ shipped |
| M3 | Backend (3 verbs) + Compiler + federation loop | 4–6 | ✅ shipped |
| M4 | Memory legibility — enrich pipeline, entity graph, wiki surface | 7 | ✅ shipped |
| M5 | Observability — audit correctness, cost attribution, spend rollups | 8 | ✅ shipped |
| M6 | Ambient Observer + review notes + tiered attribution | 9 | ✅ shipped |
| M7 | MCP Manager + Skill Factory + universal tool calling + parsing/OCR | 10 | ✅ shipped |
| **M8** | **Durability — encrypted backup, second device, tested restore** | 22 | ⬜ **next** |
| **M9** | **Authority layer — policy engine, action types, domain principals, evidence, `may_i` over MCP** | 16–20 | ⬜ |
| **M10** | **Provable history — anchoring; key recovery and inheritance** | 21, 23 | ⬜ |
| **M11** | Sharing + access control, on top of the authority layer | 11 | ⬜ |
| **M12** | Extra surfaces (Telegram), orchestrator, failure journal | 15, 12, 13 | ⬜ |
| **M13** | Deferred differentiators + personality proper (data-gated) | 14 | ⬜ |

**M8 is first, ahead of the authority layer**, because it is the only outstanding
item where delay risks permanent, unrecreatable loss: the entire compiled corpus
lives in one Postgres on one machine with no backup, and the enrichment pass alone
cost ~44 hours. **M11 moved from first to after M9–M10** — sharing's per-key spend
caps, per-guest attribution and audit-trust story each get built once on the
authority layer instead of twice.

## 10b. Shipped feature inventory (as of 2026-07-29, v0.3.0)

**Capability spine (0)** — `~/.tawn/` home, deny-all grants, SHA-256 integrity
sidecar, `MediatedFS` single chokepoint (resolve-then-check defeats `..` and symlink
escapes), append-only chain-hashed audit log with actor field and JSON/CSV export,
`tawn init` / `grant confirm` / `doctor`.

**Wealth (1)** — holdings YAML (NGX + US), price fetch with fallback, snapshot
scheduler via systemd timer, Rich dashboard with ±5pp drift, `tawn db setup`.

**Model router (2)** — 10 providers (Anthropic, OpenAI, Gemini, DeepSeek, Ollama,
OpenRouter, Kimi, Qwen, Groq, Grok); Provider Protocol with error classification and
circuit breaker; streaming across all adapters; sovereignty ledger; unified model
picker; OS keyring for keys; live model discovery (425 models).

**Domains + web v2 (3)** — `DomainSpec`, `entry_points` registry, enable/disable
trust gate, 5 domains, `tawn domain create` (LLM-assisted with wizard fallback),
React SPA with 13 pages and grouped sidebar, `tawn web start/stop/status` with
pidfile singleton, identity baseline, personality profile, chat history.

**Memory core (4–5)** — `recall`/`note`/`brief` over CLI, HTTP and MCP; pgvector
semantic search; incremental 9-phase compiler; source-priority conflict tiers;
entity resolution without silent merges; TTL staleness.

**Federation (6)** — `FederationRecord` schema, 6 adapters (Claude Code, Codex,
Gemini CLI and others), dispatcher, auto-discovery, normalizer, merge, exporter,
inotify watcher, systemd daemon, ignore-file system with venv auto-detection.

**Memory legibility (7)** — filter→clean→group→enrich pipeline, entity graph
(11,988 entities / 12,878 edges / 11,986 wiki pages), grouped feed, personal notes,
graph→wiki clickthrough.

**Observability (8)** — unified audit path, cost ledger with attribution, spend
rollups, unpriced-call honesty, spend reconciliation.

**Observer (9)** — project-scoped watcher, tiered attribution (git → agent logs →
heuristics) with confidence, review notes to granted folders, CLI/API/UI.

**MCP + tools (10)** — MCP client and manager with adoption and capability gating,
universal tool calling (native and prompted), stdlib-first document parsing with XXE
guard, OCR (thread-pinned, 2m23s→4.7s), skill factory, chat agent loop, generated
tool creator that stages but never enables.

**Hardening** — REVIEW-2026-07-27: ngrok no longer auto-exposes (requires
`--public`), injection boundary enforced, untrusted tools marked, `system` grant
split into `net` + `shell`, self-confirm endpoint removed, 45 silent exception
handlers routed to a reporter, destructive operations confirm. Public site on GitHub
Pages. Org infrastructure: shared health files, issue forms, reusable CI, computed
PR checks.

## 10c. Known gaps

Honest inventory of what is not true yet:

1. **No backup, no second device.** The corpus dies with the machine. Highest
   priority (M8).
2. **Policy evaluation is entangled with filesystem mediation** — the cause of the
   MediatedFS coverage gap recorded in REVIEW-2026-07-27 (`135:6`).
3. **Adoption is unmeasured.** No PyPI, star, or dependant figures recorded.
4. **Bus factor of one.** No second reviewer; the release process is undocumented.
5. **`float` on a monetary path** at `src/tawn/web/routes/observability.py:62`, and
   lines 71 and 81 — violates §8's own Decimal rule on the spend-reporting path.
6. **Windows and macOS are CI-verified only**, never confirmed by a real user.
7. **Audit log growth is unbounded** — no rotation or compaction.
8. **First-run still requires Postgres** with no zero-setup fallback.

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| **Corpus loss from single-machine failure** | M8: encrypted backup, second device, tested restore. Currently unmitigated. |
| **Forgotten passphrase destroys the corpus** | M10: threshold key recovery + inheritance path |
| Knowledge layer goes stale | TTL marking + scheduled federation loop + self-maintaining Compiler |
| Authority layer becomes a false assurance | One decision point, no bypass paths, a test asserting no code path reaches user content unchecked; external review after M9 |
| Prompt injection escalating to privileged action | Enforced boundary, untrusted tools marked, per-action confirmation, no `*_enable` tool exposed to models |
| Personality echo-chamber | Bounded influence + diversity floor + user-correctable profile |
| Multi-provider maintenance burden | Provider Protocol behind one interface |
| Over-surveillance from Observer | Deny-all grants; project-scoped default; system awareness opt-in; full audit |
| Entity graph corruption | No silent merges; ambiguous cases to review queue |
| **Bus factor of one** | Architecture doc, documented release process, recruit one reviewer with bounded merge rights |
| **Sharing exposing more than intended** | M11 deliberately sequenced after the authority layer so caps, attribution and audit trust are built once |
| Scope creep | Sequence by data dependency and irreversible-risk first; defer data-gated features |

## 12. Out of scope for v1 (planned later phases)

- **Multi-user / team sharing** — later phase; the commercial tier.
- **Cloud hosting for non-Linux users** — later phase (Linux-first now).
- **Execute/spend integrations** — via the open integration contract (§9), not core.
- **Chain-bound capabilities** — value rails, wallets, on-chain identity, session
  keys. Specified separately as an optional layered package with a one-way
  dependency on Tawn. Nothing in this document depends on it, and removing it costs
  no capability.
- **Mobile-native app** — after web + Telegram surfaces.

## 13. Open questions

- Trademark posture for the name "Tawn" and the cairn mark.
- Whether Postgres stays a hard first-run dependency or gains a zero-setup fallback.
- Where the team/org boundary sits precisely — which administration features are
  paid, and whether a delayed-open licence is acceptable for that tier only.
- Whether `may_i` should be specified as a protocol others can implement, or remain
  a Tawn interface.
- Reference design for the first execute/spend integration once the contract is
  stable.

---

*Product requirements for Tawn — memory and authority. Technical realization in the
design spec; build order in `docs/ROADMAP.md`; user-facing outcome in
`EXPERIENCE.md`. ℵ → ת*
