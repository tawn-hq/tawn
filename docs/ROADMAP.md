# Tawn Build Roadmap — living document

> Master plan for all stages (design spec §14). Updated as stages complete and
> decisions land. Detailed bite-sized plans are written **per stage at the
> moment it goes active** — never earlier, so they build on what the previous
> stage taught us. One stage = one plan file in this directory.
>
> **Scope:** this file tracks *what gets built* in this repository, stages 0–23.
> Two companion documents live in the `tawn-hq` workspace, outside this repo:
> `docs/OSS-ROADMAP.md` (the open-source journey — MIT boundary, adoption,
> contributors, releases, community) and `docs/WEB3_ROADMAP.md` (a separate layered
> package, one-way dependency on `tawn`, not on the path to 1.0).
> A project can ship every stage here and still fail as open source.

**Status legend:** ✅ shipped · 🔨 active · 📋 planned (plan written) · ⬜ not started

| Stage | Ships | Status | Plan file |
|---|---|---|---|
| 0 | `~/.tawn/` skeleton + deny-all grants + FS-mediation + audit + CLI | ✅ | `2026-07-07-stage0-capability-spine.md` |
| 1 | Wealth v0: holdings (NGX+US) → snapshots (Postgres) → CLI dashboard + global web viewer shell + `tawn db setup`/`doctor` + scheduled snapshots + branded CLI | ✅ | `2026-07-07-stage1-wealth-v0.md` |
| 2 | Provider Protocol + 5 cloud adapters + Model Router (error classify, circuit breaker, sovereignty ledger) + `tawn ask`/`ledger`/`model` CLI + streaming completions + model catalog | ✅ | `2026-07-07-stage2-model-router.md` |
| 3 | Domain Plugin Arch + Web Viewer v2 + Personality layer + Chat history + Web daemon + Audit chain | ✅ | `2026-07-08-domain-plugin-and-web-viewer-v2.md` |
| 4 | Backend: `recall/note/brief` over MCP + HTTP, `127.0.0.1`; pgvector semantic search | ✅ | `2026-07-20-stage4-5-memory-core-part1.md` / `part2.md` |
| 5 | Compiler: incremental, conflict tiers, entity resolution, TTL, provenance | ✅ | `2026-07-20-stage4-5-memory-core-part1.md` / `part2.md` |
| 6 | Federation loop: ingest + cloud-export inbox + project canonical out | ✅ | `2026-07-22-stage6-federation-loop-part1.md` / `part2.md` |
| 7 | Memory legibility: filter→clean→group→enrich pipeline, entity graph, wiki surface (CLI+web), grouped feed, document reconstruction | ✅ | `2026-07-25-stage7-memory-legibility.md` |
| 8 | Observability: audit trail correctness, cost ledger with attribution, spend rollups, activity page | ✅ | `2026-07-25-stage8-observability.md` |
| 9 | Ambient Observer (project-scoped) + review notes + authorship attribution | ✅ | `2026-07-26-stage9-ambient-observer.md` |
| 10 | MCP Manager (client, adoption, capability-gated) + universal tool calling + standard toolset (files/net/shell/research/diagrams/parsing) + Skill Factory + skill import + generated-tool creator | ✅ | `2026-07-26-stage10-mcp-manager-and-skill-factory.md` |

## Remaining work, in priority order

**Stage numbers are stable identifiers, not an execution order.** They are
referenced from the decision log below and from plan filenames, so they never
change. `#` is the order to build in, and it is the column that gets reshuffled.

| # | Stage | Ships | Status |
|---|---|---|---|
| **1** | 22 | **Encrypted backup + second device.** `BackupStore` interface, client-side encryption (user holds the key), local-directory and S3-compatible backends. Content-addressed backends may be added later, never as the only option | ⬜ |
| **2** | 16 | **Policy engine extraction.** Split `PolicyEngine` (typed action → `Decision(allowed, reason, matched_rule)`) out of filesystem mediation; MediatedFS becomes one caller among several rather than the only gate | ⬜ |
| **3** | 17 | **Registrable action types.** Plugins contribute action classes and `grants.yaml` schema blocks through the entry-point machinery the domain plugins already use; core stays unaware of any specific action domain | ⬜ |
| **4** | 18 | **Domain principals.** Each domain carries its own authority envelope — grants, model allowlist, tool allowlist, spend ceiling, sensitivity policy — and its own segment of the evidence trail | ⬜ |
| **5** | 19 | **Signed evidence bundles.** Per-action envelope: action, decision + reason, hash of inputs (never contents), actor + attribution confidence, audit chain head, signature | ⬜ |
| **6** | 20 | **Policy over MCP.** `may_i(action)` and `evidence(id)` so any agent — Claude Code, Cursor, anything speaking MCP — can ask permission and get an answer that lands in the audit trail | ⬜ |
| **7** | 21 | **`AnchorTarget` port + OpenTimestamps.** Publish one chain head per interval so log integrity is checkable by someone other than its owner. No wallet, no chain integration; other anchors become adapters behind the same port | ⬜ |
| **8** | 23 | **Key recovery and inheritance.** Threshold secret sharing / social recovery for the backup key (k-of-n guardians or devices) plus a dead-man's-switch path | ⬜ |
| **9** | 11 | Sharing + access control: owner/guest keys, allowlisted guest view (shared artifacts + comments), **public chat over an opt-in public corpus, no tools, owner-chosen model, per-key spend caps**, public persona, per-guest audit attribution, code-doc artifacts, vertical nav | ⬜ |
| **10** | 15 | Telegram surface (the domain-module half already shipped unplanned during Stage 0–3 work via records-engine config for work/research/academic/hobby) | 🔨 |
| **11** | 12 | Orchestrator: router (retrieval-first + escalation) + handoff artifact | ⬜ |
| **12** | 13 | Failure journal + auto-replay | ⬜ |
| **13** | 14 | Deferred differentiators: contradiction sweep, time-travel, preference learning, personality proper | ⬜ |

### Why this order

Four tiers, in descending urgency:

**Tier 1 — irreversible risk (#1–2).** Stage 22 is first because it is the only
item where delay risks **permanent loss**. ~12,300 chunks and 11,988 entities live
in one Postgres on one machine with no backup; the enrichment pass alone took ~44
hours. Every other item on this list can wait a month without anything being
destroyed. Stage 16 is second because it fixes a defect that already exists — the
MediatedFS coverage gap (REVIEW-2026-07-27, `135:6`) — and unblocks #3–#6.

**Tier 2 — the authority spine (#3–6).** 17 → 18 → 19 → 20, each depending on the
one before. #6 is the leverage peak: `may_i` and `evidence` over MCP turn Tawn from
a memory server into the policy sidecar any agent can consult.

**Tier 3 — make sharing safe, then share (#7–9).** Stage 11 **moved from first to
ninth**, which is the largest change here. Sharing is the biggest risk surface in
the whole roadmap — it puts Tawn on the internet — and it gets materially better
after the authority layer: per-key spend caps become a use of registrable action
types instead of a bespoke implementation, per-guest attribution rides on evidence
bundles, and anchoring (#7) turns the audit trail a guest is asked to trust into
something they can verify. Building 11 first would mean writing all three of those
mechanisms twice.

**Tier 4 — value after the foundation (#10–13).** Telegram is a thin surface. The
orchestrator and failure journal are quality-of-life over a core that works. Stage
14 stays last because it is data-gated regardless of priority.

## Stage dependency notes (why this order holds)

- **1 before 2:** wealth v0 needs no LLM; proves DB + domain pattern cheaply.
- **2 before 3:** every backend model call goes through the Provider Protocol —
  ledger + provenance wired in from day 1 (spec §21: build early or never).
- **3 before 4:** personality + domain registry anchor what the compiler must know about the user.
- **4 before 5/6:** the verbs define what the Compiler must produce; semantic recall needs pgvector.
- **5 before 6:** federation loop's compile step *is* the Compiler.
- **7 after 4–6:** wiki surface reads what the core produces.
- **8 anytime after 4** (needs `note` write-back); placed after 7 so review
  notes land somewhere visible.
- **11 after 10** *(original reasoning, still true)*: sharing exposes Tawn to the
  internet, so it must come after the tool surface it would expose is finished and
  testable. **Superseded on ordering** — see the priority table: 11 now also waits
  on the authority layer, because its spend caps, guest attribution and audit
  trust all get built once instead of twice.
- **14 is data-gated:** needs months of accept/reject + graph density; capture
  signal from Stage 8, build the compilers here.
- **15's domain half is done**; only the Telegram surface remains, and a thin
  surface earns no priority over foundations.
- **16–23 are the authority layer**, the chapter that takes Tawn from a memory layer
  to an authority layer. Every one of them is useful with no blockchain present —
  that is the test each had to pass to be in this file rather than the separate web3
  layer.
- **16 stands on its own merit.** Policy evaluation is currently entangled with
  filesystem mediation, which is why the MediatedFS coverage gap exists
  (REVIEW-2026-07-27, `135:6`). Extracting it is a refactor worth doing even if
  nothing downstream were ever built.
- **16 before 17 before 19 before 20** — that chain is the spine. 18 can land
  alongside 17, since a domain envelope is a grant scope and needs the registrable
  schema first.
- **20 is where the leverage is.** Exposing `may_i` and `evidence` turns Tawn from a
  memory server into the policy sidecar any agent can consult — a larger strategic
  surface than the rest of 16–23 combined.
- **21 is cheap and independent.** One hash per interval. It can ship any time after
  16, but it only becomes load-bearing at Stage 11: sharing hands a guest a view
  backed by an audit trail they must otherwise trust completely, and anchoring is
  what turns that trail from assertion into evidence.
- **22 is now first overall.** Everything compiled lives in one Postgres on one
  machine with no backup and no second device, so "the memory you own" currently
  dies with the laptop. It is a correctness gap in the product thesis, it depends on
  no other stage, and it is the only item on the list where waiting risks losing
  work that cannot be recreated.
- **23 needs 22.** There is no key to recover until there is a backup key. It closes
  the worst failure mode of client-side encryption: a forgotten passphrase
  destroying the corpus permanently.

## Decision log (append-only; newest first)

| Date | Decision | Where it bites |
|---|---|---|
| 2026-07-29 | **The authority layer stays MIT. What gets sold is operator burden, not trust primitives.** Considered and rejected: moving stages 16–23 into a private repo as a paid tier. The decisive argument is technical, not ideological — **the authority layer is not severable.** It *is* the capability spine: grants, MediatedFS and the audit chain shipped under MIT in Stage 0 and are already on PyPI, so Stage 16 is a refactor of already-released MIT code. Closing "authority" would mean running a licence boundary through the middle of `capability/` and triaging every future change to `grants.py` as open-or-closed, permanently, in the highest-traffic subsystem. Three supporting reasons: a proprietary policy engine and audit log make Tawn's deny-all and injection-resistance claims unverifiable, and for a sovereignty product an unauditable auditor is worse than no claim; it disqualifies the strongest funding fits (FUTO, Mozilla, OTF, GitHub SOSF all weigh openness); and `may_i` over MCP only has value if it is ubiquitous — a permission oracle other vendors must license gets reimplemented or ignored, which is why MCP itself was donated to the Linux Foundation. The commercial line therefore sits at *who carries the cost of running policy at scale*, not at whether policy exists: single-user policy, evidence, audit and local anchoring are free forever; hosted backup/sync, team deployment with central administration and SSO, and hosted attestation with auditor export are paid. Full free/paid split in `tawn-hq/docs/OSS-ROADMAP.md` under "The promise". BUSL-1.1 with a delayed MIT conversion was also rejected for this layer — not OSI-approved, so the same funders still exclude it — though it remains open for the team/org features, where no trust claim depends on it. | Stages 16–23; the MIT boundary |
| 2026-07-29 | **Remaining work is ordered by priority in its own table; stage numbers are frozen identifiers.** Renumbering was rejected: stage numbers are referenced from eight rows of this decision log and encoded in plan filenames, so reordering by renumbering would invalidate the project's own history. Priority is a separate, mutable column. The substantive changes: **Stage 22 (backup) moves to first** — it is the only item where delay risks permanent, unrecreatable loss of ~12,300 chunks and 11,988 entities sitting in a single un-backed-up Postgres — and **Stage 11 (sharing) moves from first to ninth**, because its per-key spend caps, per-guest attribution and audit-trust story each get built once on top of the authority layer instead of twice. | Ordering of 11–23 |
| 2026-07-29 | **The authority layer is open source, and stays in this repo.** Stages 16–23 generalise what the capability spine already does for files to every action class, and expose it as a decision other agents can ask for. The test each had to pass: *is this useful with no blockchain present?* Policy extraction fixes an existing coupling defect; evidence bundles are what Stage 11 sharing needs to hand a guest something better than blind trust; `may_i` serves any MCP agent immediately; backup is a correctness gap today. Chain-bound work — `spend`/`sign` capabilities, value rails, wallet-enforced session keys, on-chain identity — is a **separate package** with a one-way dependency on `tawn`, tracked outside this repo. Rationale: putting authority in the web3 layer would leave the open-source product as "just memory" and place the most valuable part outside the MIT promise, inverting the open-core boundary. | Stages 16–23 |
| 2026-07-29 | **A domain is a scoped principal, not an autonomous agent.** Domain principals (Stage 18) get an identity, an authority envelope, a budget and an evidence segment — generalising the constraint wealth has carried since Stage 1, where it is read-only and never holds withdrawal credentials. What they do *not* get is initiative. Tawn's value is constraint, not autonomy; the moment a domain acts on its own behalf, the safety property that makes the whole system worth trusting is gone. | Stage 18 |
| 2026-07-27 | **Attachments are parsed on attach, not on send, and travel by id** — the previous flow read every file as text (so a PDF became binary noise), inlined it into the message, and therefore re-sent the whole document on *every* later turn until the request grew large enough that chat stopped responding. Now upload → parse through the harness → store under an id; a turn references ids and the text enters context once, for that turn only. The wait moves to while the user is still typing, and send is blocked until parsing finishes. | Stage 10 |
| 2026-07-27 | **Tesseract's OpenMP pool is pinned to one thread** — measured 2m23s unconstrained versus 4.7s pinned on the same 900x320 image, identical output. Set in code rather than documented as a tip: a user who hits the 30x slow path concludes OCR is broken and never finds the workaround. | Stage 10 |
| 2026-07-27 | **Tool generation asks for delimited sections, not JSON** — a tool payload *contains Python source*, and embedding that in a JSON string needs every newline and quote escaped correctly, which is where smaller models fail. Fenced sections need no escaping. JSON is still accepted, with repair for unquoted keys, single quotes, trailing commas and Python singletons, plus brace-matching so trailing prose is not swallowed. One corrective retry, and the *first* error is reported rather than the last because a retry tends to drift further. | Stage 10 |
| 2026-07-27 | **A generated tool that echoes the prompt template is rejected** — a model too small for the task returns the example body verbatim. That output parses perfectly and does nothing, which looks like success: the worst failure mode available. A local-only failure now names the model and points at `--cloud`. | Stage 10 |
| 2026-07-27 | **Navigation regrouped into a sidebar** — nine flat links in one row gave every destination equal weight and no shape, with "activity" sitting beside "chat" as though they were the same kind of thing. Four labelled groups (your twin / knowledge / capability / system), a collapsible rail, and one shared `Page` heading so titles land in the same place everywhere. | Stage 10 |
| 2026-07-27 | **Every model can call tools, via a three-tier ladder** — native tools API where the provider has one, a prompted `<tool_call>` protocol where it does not, and support discovered by *trying* rather than a hardcoded model list (Ollama's tool-capable set changes every release, and a stale list silently downgrades models that gained support). Refusing tools on non-native providers would have made Tawn's whole tool surface work only on the expensive ones — backwards for a local-first system. OpenRouter needed no special casing: it speaks the OpenAI dialect. | Stage 10 |
| 2026-07-27 | **Self-configuration tools stage but never enable** — a model can call `mcp_add`, `mcp_adopt`, `skill_new` and `tool_new`, and each produces a *disabled* artifact plus the command the user must run. `mcp_enable`, `tool_enable` and grant edits are never exposed. A model able to register a server, enable it and call it inside one turn would grant itself a capability the user never approved, making disabled-by-default decorative. A test asserts the exposed set contains no `*_enable`. | Stage 10 |
| 2026-07-27 | **Generated tools declare their capabilities, and the declaration is verified by AST** — `inspect_source` walks imports and calls; a manifest claiming less than the code does is rejected at creation. A model's account of its own code is not evidence. Over-declaring is allowed because it is the safe direction. This is not a sandbox and the docs say so: an enabled tool runs in Tawn's process with Tawn's access, so the review step is the protection. | Stage 10 |
| 2026-07-27 | **Document parsing is stdlib-first** — docx, xlsx, pptx, odt and epub are ZIP+XML, which `zipfile` and `ElementTree` read for free, so reaching for python-docx et al would have made the common case needlessly expensive. Cost ladder: stdlib → optional library → local Tesseract → Mistral OCR → generic vision model. OCR is on by default (local, free); the model tier is off (paid, leaves the machine). | Stage 10 |
| 2026-07-27 | **A security guard that can silently not-apply is worse than none** — the XML entity check used `XMLParser.parser.EntityDeclHandler`, which does not exist on Python 3.12, and an `except AttributeError` swallowed the failure. The guard never armed; a test caught it. Replaced with a byte scan for `<!DOCTYPE` + `<!ENTITY` before parsing, which cannot fail to run. | Stage 10 |
| 2026-07-27 | **Skill sync never overwrites what it did not write** — every synced directory gets a `.tawn-synced` marker, and a same-named file without one is reported as a conflict and left alone. Import dedupes on name *and* body hash (not the whole file, whose frontmatter differs after a round trip), so sync-then-import does not fork a skill against itself. | Stage 10 |
| 2026-07-27 | **Mistral pricing recorded only where verified** — mistral.ai states Mistral Large at $2/M in and $6/M out; the smaller models and the OCR endpoint sit in a JS-rendered table that could not be read from source, so they are deliberately absent. `estimate_cost` reports those as unpriced, which is honest; a guessed figure would silently corrupt the spend dashboard. | Stage 10 |
| 2026-07-27 | **Guest access is an allowlist, and public chat gets its own corpus** — a shared artifact leaks exactly what was shared, but a chat grounded in memory leaks whatever a guest can get it to say, so filtering private recall would fail open and fail silently. Public chat will recall only from chunks explicitly flagged public, run with **zero tools** (a guest turn with tool access is remote code execution on the owner's machine), use an owner-chosen model under per-key spend caps, and log every turn against the guest key. Guest identity is the key, not the self-asserted name — so keys are per-person and individually revocable. | Stage 11 |
| 2026-07-26 | **Observed projects derive from `read:` grants, not a second path list** — the `observe:` grant stays a list of *signal names* (`fs`, `git`, `agents`), and every granted `read:` directory is watched. A separate observe-path list would have been more precise and would also have been a second way to get grants wrong: two lists that drift apart, and a path the Observer watches but the compiler cannot read. The Observer's reach is now provably a subset of what Tawn could already index. | Stage 9 |
| 2026-07-26 | **Timing heuristics ship, but ranked last and always hedged** — burst-detection can attribute writes on a machine with no agent session log, which is why it is in. It runs only after git identity and agent-session correlation have both come up empty, returns `low` confidence, and renders as "likely agent" rather than "agent". A confident wrong answer about who wrote a piece of code is worse than an honest `unknown`, so the confidence field is load-bearing and a regression test asserts a timing result can never override a git or session one. | Stage 9 |
| 2026-07-26 | **Observed events store paths and line counts, never file content** — storing diffs would have made Tawn an unversioned second copy of the user's source, growing without bound and outliving deletion. Review composition reads files at compose time through the normal grant check instead. The cost is that a file deleted before its session closes cannot be quoted, which is correct behaviour rather than a limitation. | Stage 9 |
| 2026-07-26 | **Stage 9 migration written by hand** — `alembic.ini` pins an in-memory SQLite URL so autogenerate cannot reach the real database, and autogenerate in this repo injects a `pgvector…VECTOR(dim=…)` reference with no import on every revision. Two tables with no vector columns were cheaper to state directly than to generate and then repair. | Stage 9 |
| 2026-07-26 | **Stage numbering corrected** — Stage 7 was rescoped mid-session and its observability half split into a new stage, which was written into row 8 without checking what was already there. That overwrote the planned **Ambient Observer** stage. Ambient Observer is restored at 9 and the unstarted stages shifted down; none had plan files, so nothing else moved. Observability keeps 8 because its spec, plan and decision-log entries already reference it by that number. | Stages 8, 9 |
| 2026-07-26 | **Audit trail was reading the wrong file** — every writer appended to `audit.log` (8KB, current) while `/api/audit*` read `audit.jsonl` (408B, stale for two days). The Dashboard panel, Settings view, chain-verify button and CSV export all reported on a file nothing wrote to, and `verify_chain` returned `intact: true` because it verified the stale copy. A `chat.py` comment showed the split had been "fixed" once already in the wrong direction. Unified on `audit.jsonl` with a locked, atomic migration; a grep-based test now fails if either filename is hardcoded again. | Stages 0, 3, 8 |
| 2026-07-26 | **`estimate_cost` collapsed "free" and "unknown" into $0** — `PRICES` held 7 models against 9 configured providers plus embedders, so most spend billed as free. Now returns `(cost, priced)`. Coverage must follow *usage* rather than registry defaults: 1,306 real `gemini-2.5-pro` calls billed as $0 because only the default (flash) was listed. Ollama names carry a `:tag` suffix, so an exact-name set never matched them and local models read as unpriced rather than free. All prices verified against vendor documentation, not memory. | Stage 8 |
| 2026-07-26 | **Embeddings were invisible** — ~12k calls per rebuild recorded nothing, so the slowest part of the system had no cost or throughput data. Now one ledger entry per text with a shared `batch_id` and elapsed time attributed by input length. | Stage 8 |
| 2026-07-26 | **Ledger stays JSONL; rollups are a derived cache** — recording every embed takes the file from dozens of entries to ~12k per rebuild, and `entries()` reads it all into memory. A watermarked reconciler folds new lines into Postgres, advancing only to the last complete newline so a partial append is never consumed. Because the table is derived, it also reprices historical entries whose model had no price when written — the file stays immutable, the view gets more accurate. | Stage 8 |
| 2026-07-26 | **Model catalogue was hardcoded and frozen** — `PROVIDER_MODELS` offered 1 OpenAI model while the live catalogue had 82, and 3 OpenRouter models against 330. Models are now discovered from each provider's API, cached for a day, with the curated list demoted to a fallback for when a provider is unreachable. 425 cloud models where there were ~24. | Stages 2, 8 |
| 2026-07-26 | **`tawn db setup` never enabled pgvector** — it created the database but not the extension, so semantic search silently degraded to keyword matching with nothing reported. Now enabled during setup, with the per-platform package command printed when it fails. | Stages 1, 8 |
| 2026-07-26 | **`__version__` was hardcoded** and drifted from `pyproject.toml`, so the update page reported 0.1.0 while 0.2.0 was installed and running. Now read from package metadata. Fixing it exposed a second bug: `update_available` compared `latest != current`, telling users on a newer local build to "update" to an older release. | Stage 3, 8 |

| 2026-07-26 | **`scan_raw` treated every non-`raw/` file as deleted** — it loaded *all* `FileState` rows while globbing only `raw/`, so granted repos, history and agent memory looked deleted on every compile. Their chunks were removed and re-added on alternating runs; the compile log shows +1,347 then −2,303 twenty minutes later. This was the single most destabilising bug in the compiler and explains wiki pages and feed cards vanishing at random. Pre-existing, found while chasing a blank feed. | Stage 5, 7 |
| 2026-07-26 | **Domain index pages deleted by an empty compile** — `changed_domains` was derived from chunks processed *this run*, so a compile with nothing changed staged no domain pages, and the new prune in `atomic_swap` then deleted every live one. Indexes are now generated for every domain that has chunks, and the prune is skipped when nothing was staged. | Stage 7 |
| 2026-07-26 | **Derived data never backfills onto untouched rows** — the same shape three times: changing embedder left 12k stale vectors, adding grouping left 11,103 chunks ungrouped, and fixing markdown domain inference left 967 rows unclassified. A normal compile only revisits files whose *contents* changed, so each needed an in-place repair pass: `tawn reembed`, `compiler/regroup.py`, `backfill_domains`. Any future derived column needs one from the start. | Stage 5, 7 |
| 2026-07-26 | **Embedding client was constructed per call** — measured 43s for the first Gemini embed against 0.8–1.9s on a reused client, so ~42s of every call was TLS handshake and API discovery. Clients are now cached per process: 27s/chunk (local CPU) and 43s/chunk (cloud, unfixed) became 0.79s/chunk. This also explains an earlier 56-minute OpenAI run. | Stage 5, 7 |
| 2026-07-26 | **Dimension is not identity** — `nomic-embed-text` and `gemini-embedding-001` are both 768-dimensional but occupy unrelated vector spaces. Recall and the compiler's skip-check both matched on width alone, which would have compared Gemini queries against nomic vectors and returned confident nonsense. Both now match on `embed_model`, recorded per row, and the embedding column is dimensionless so any embedder can be used. | Stage 4, 7 |
| 2026-07-26 | **Cloud embedding is opt-in** — a stale `embed_model` in config sent the entire corpus to OpenAI for 56 minutes unnoticed. Embedding exposes *everything*, unlike a single chat call, so `_chain()` now includes cloud providers only with `embed_allow_cloud: true` or `TAWN_EMBED_ALLOW_CLOUD=1`, and raises rather than silently falling back to a paid remote. | Stage 7 |
| 2026-07-26 | **Chunks are for retrieval, documents are for reading** — a feed card listing five length-based fragments of one file asks the reader to reassemble it mentally, and the splits fall mid-sentence. `memory/document.py` rebuilds a group into one document from its stored chunks; `recall` still matches individual chunks, which is correct for search. | Stage 7 |
| 2026-07-26 | **Entity hygiene** — LLM extraction beat the old Title-case regex but still admitted file paths, IPs, hex tokens and `Category #hash` codes (4,117 of 17,612), phrased one relation three ways (`is located in`/`located_in`/`located in`), and forked identity by case (`Uniswap`/`uniswap`/`UNISWAP` — which also broke wikilink resolution). `compiler/hygiene.py` holds the rules; `entity_cleanup.py` applies them to existing data. | Stage 7 |
| 2026-07-26 | **Stale-process detection** — three separate wrong conclusions in one session came from long-lived processes running old code: a compile daemon undoing CLI work, a pipx install shadowing an editable checkout, and a web server serving pre-fix API responses. A content fingerprint is recorded at startup and compared by `tawn doctor`, `tawn web status` and `/api/status`. | Stage 0, 7 |

| 2026-07-23 | **Roadmap sync** — Stages 4/5/6 had been built and shipped without the roadmap table ever being flipped from ⬜; this entry documents the catch-up, not new work. Also found: Stage 13's work/research/academic/hobby domains were already shipped (thin `record_domain()` configs over the shared RecordsEngine) as an unplanned add-on during earlier Stage 0–3 work — table now shows 🔨 instead of ⬜. | Stages 4–6, 13 |
| 2026-07-23 | **Audit log `actor` field** — every `AuditLog.record()` call now tags who initiated it (`cli`\|`web`\|`chat`\|`system`); centralized in `merge_pending()` for federation actions so CLI/web/chat callers all get it for free rather than each call site remembering to audit separately. Old entries lack the field (backward compatible — chain hash recompute ignores missing keys). | Stages 0, 6 |
| 2026-07-23 | **Compiler durability** — `run_compile()` only committed once at the very end of a multi-thousand-chunk run; a kill mid-run (or one bad embed call) lost the entire batch, not just the tail. Switched the existing 200-row batch `flush()` to `commit()` so progress survives incrementally. Embed failures also get bounded retry-with-backoff (3× if a provider was previously confirmed working, 1× if never confirmed — avoids hanging forever on a transient network blip while still failing fast when no provider is configured at all). | Stage 5 |
| 2026-07-23 | **Federation source auto-discovery now backfills immediately** — previously a newly auto-detected source (e.g. Codex used before Tawn was installed) only got its pre-existing history scanned on the next full server restart; `GET /api/federation/sources` now runs `scan_all_sources` + `merge_pending` inline the moment discovery finds something new. Startup scan also moved off the main thread (was blocking `uvicorn.run()` from binding the port on large source dirs) and gained a 2MB per-file size cap (stray multi-MB tool-output logs in `~/.gemini/tmp/` were making the scan take minutes). | Stage 6 |
| 2026-07-23 | **Light mode toggle** — 3-state cycle (system → light → dark) in `AppNav`, persisted to `localStorage`, applied pre-paint via inline `index.html` script (no flash). Fixed a real CSS bug along the way: `[data-theme="light"]` only set `color-scheme`, not the actual tokens, so explicitly picking light while the OS preferred dark silently rendered dark anyway — same-specificity `:root` rules don't merge per-block, they compete per-property. | Stage 3 (web viewer) |
| 2026-07-20 | **Chat history persistence** — per-session JSONL at `~/.tawn/history/` with `chmod 700` dir and `600` files. Session metadata (id, started, turns, model) indexed on list. Web UI viewer page with session list + message thread. Never synced. | Stage 3+ |
| 2026-07-20 | **`tawn web start/stop/status` daemon mode** — `tawn web` is now a subcommand group. `start` spawns `python -m tawn._webserver <port>` as a detached subprocess (`start_new_session=True`), writes PID + port to `~/.tawn/web.pid` + `web.port`. `stop` sends SIGTERM to stored PID. Avoids `os.daemon()` fork complexity; works on any Unix. | Stage 3+ |
| 2026-07-20 | **Audit log chain hashing** — each entry gets a `chain` field (sha256[:16] of prev_chain + entry payload, sort_keys). Tamper evident without a separate DB. `/api/audit/verify` runs the full chain walk. `/api/audit/export?format=json\|csv` downloads the log. File is `chmod 600` after every write. | Stage 0 backfill, Stage 3+ |
| 2026-07-20 | **Personality from web** — `GET/PUT /api/profile` routes + `Profile.tsx` page. Profile fields (name, role, focus) editable in browser; saved to `~/.tawn/personality/profile.yaml`; injected into every model call via identity baseline. Same data as first-run CLI onboarding, now always reachable. | Stage 3+ |
| 2026-07-20 | **ngrok polling fix** — `tawn web start` first checks if ngrok API is already answering (tunnel re-use), then spawns `ngrok http <port>` with `start_new_session=True`, then polls `localhost:4040/api/tunnels` up to 20×0.5s instead of a single 2s sleep. | Stage 3+ |
| 2026-07-20 | **All models endpoint** — `GET /api/models` returns `usable_models(home)` (all 5 adapters' local + cloud entries). `Models.tsx` page groups by locality (local = green, cloud = lapis). | Stage 3+ |
| 2026-07-08 | **Streaming pulled into Stage 2** — `StreamChunk`, `Provider.stream_complete()`, `Router.stream()` (all 5 adapters); CLI `ask`/`chat` streams; web SSE endpoint. Previously deferred to Stage 6. | Stages 2–3 |
| 2026-07-08 | **Identity baseline pulled into Stage 2** — compact factual system prompt (capability model, sovereignty, domain list) injected identically across all providers; user profile appended when set. Personality (learned tone) still Stage 12. | Stages 2–3 |
| 2026-07-08 | **Domain Plugin Arch shipped in Stage 3** — `DomainSpec` + `entry_points` registry + trust gate; 5 default domains; `tawn domain create` (LLM-assisted + wizard fallback). Previously specced for Stage 12. | Stage 3 |
| 2026-07-08 | **Web Viewer v2 React SPA shipped in Stage 3** — FastAPI JSON API (`web/routes/`), React SPA (Vite, brand tokens, cairn SVG); 10 pages; data-driven nav from `/api/domains`. Previously specced for Stage 6. | Stage 3 |
| 2026-07-08 | **Bare `tawn` → chat** — typing just `tawn` with no subcommand invokes `tawn chat` if initialized (else shows init banner). First-run onboarding collects name/role/focus. Slash commands mirror Claude Code's `/` pattern. | Stage 3 |
| 2026-07-07 | **Official SDKs for adapters** (`google-genai`, `ollama`) — supersedes the raw-REST plan; SDK clients injected in tests (fakes, no respx for these). Provider Protocol unchanged, so swapping stays cheap. | Stage 2+ |
| 2026-07-07 | **Four cloud adapters** — Anthropic (claude-opus-4-8, adaptive thinking), OpenAI (gpt-5.1) + DeepSeek via one OpenAI-compatible adapter, Gemini; `CLOUD_REGISTRY` in router.py enables any provider whose key exists, order anthropic → openai → gemini → deepseek → ollama; `sensitive=True` filters to local *before* selection. New providers later = one factory + one registry row. | Stages 2, 9 |
| 2026-07-07 | **Model preference (`model:` in config.yaml)** — `tawn model use` picker/direct/auto + `/model` in chat; preferred provider moves to front of chain with model pinned, rest stays as failover; `PROVIDER_MODELS` curates per-provider options. **`tawn setup` wizard** (home → db → local model → keys) is the single onboarding path. | Stages 2, 6 |
| 2026-07-07 | **Circuit breaker defaults 3 failures / 60s cooldown / 1 half-open probe**; per-provider, injectable clock. | Stages 2, 9 |
| 2026-07-07 | **API keys: OS keyring, verified round-trip on `tawn key set`**, env `<PROVIDER>_API_KEY` fallback; never files, never ledger, redacted from errors. | every stage |
| 2026-07-07 | **Model discovery = curated catalog (offline, blurbs) + live ollama.com scrape (`--live`, no official API) + Gemini `models.list`**; `tawn model setup` picks by RAM ladder. | Stages 2, 6 |
| 2026-07-07 | **Web viewer is global, not per-domain** — `tawn web` serves one app with a home shell + per-domain pages; Stage 7 adds wiki/graph onto the same app. | Stages 1, 6, 12 |
| 2026-07-07 | **Background snapshots via systemd user timer** (`tawn wealth schedule`, Persistent=true) — no custom daemon; ARQ decision still parked at Stage 4. | Stages 1, 4 |
| 2026-07-07 | **Branded CLI entry**: bare `tawn` renders cairn + monoline wordmark (lapis n) + status when uninitialized; routes to chat REPL when initialized. | every stage |
| 2026-07-07 | **Postgres system service** (not Docker, not SQLite-first). Default DSN `postgresql+psycopg:///tawn` — unix socket, peer auth, no password stored. `TAWN_DB_URL` overrides. | Stages 1, 4, 5 |
| 2026-07-07 | **Alembic deferred to Stage 4** — v0 has one table; `create_all` until the backend schema is real. | Stages 1→4 |
| 2026-07-07 | **Wealth input = holdings YAML + NGX price fetch** with manual-price fallback; no broker APIs; fully read-only. | Stage 1 |
| 2026-07-07 | **grants.yaml integrity = SHA-256 sidecar** + `tawn grant confirm` flow. | Stage 0 (shipped) |
| 2026-07-07 | **All file I/O through `MediatedFS`** — bare `open()` outside `capability/fs.py` is review-rejectable (CONTRIBUTING.md). | every stage |
| 2026-07-07 | Conventional commits enforced via `.githooks/commit-msg`; user runs commits personally. | every stage |

## Standing open questions (resolve when their stage activates)

- **Stage 4 (resolved):** Redis + ARQ never materialized — background work
  (auto-compiler, federation merge) runs on a plain daemon thread with a
  30-min sleep loop inside `_webserver.py`, no queue infra. Revisit only if
  single-threaded background work becomes an actual bottleneck.
- **Stage 5 (resolved):** pgvector confirmed available (`pgvector/pgvector:pg16`
  image in CI; `CREATE EXTENSION vector` on local Postgres 16). Embed dims
  locked per-installation in `config.yaml`, read by `schema.py` at table-def
  time — changing embed model requires `tawn compile --rebuild`.
- **Stage 6 (resolved):** 6 adapters shipped (claude-code, claude.ai, chatgpt,
  gemini export, gemini-cli local logs, codex) + generic fallback. Real-world
  format quirks found late and fixed: Codex's actual file is
  `rollout-*.jsonl` (not `session-*.jsonl` as first assumed) with a nested
  envelope, not a flat `{role, content}` line; Gemini CLI has two distinct
  on-disk formats (`logs.json` prompt-only log vs. `chats/*.jsonl` full
  transcript with model name) requiring one adapter to handle both.
- **Stage 7:** wiki markdown flavor + backlink syntax (Obsidian-compatible).
- **Stage 8:** VSCode signal — extension vs file-mtime/LSP fallback first.
- **Stage 13:** Telegram bot library + how briefs render as messages.

## Update protocol

When a stage completes: flip status, link the plan, append decisions learned.
When scope changes: edit the stage row *and* note why in the decision log.
This file is the single place to see where the build stands.
