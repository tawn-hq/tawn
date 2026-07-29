# Developing Tawn

Setting up a working development environment, and the things about this
codebase that are not obvious from reading it.

**If you only want to *use* Tawn, this is the wrong document.** Install it with
`pipx install tawn` and read [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md). This
file is for people changing the code.

---

## What you are getting into

| | |
|---|---|
| Python | ~23,000 lines across 155 modules |
| TypeScript | ~7,400 lines, React 18 + Vite |
| Tests | ~14,000 lines, 1,160 passing, ~4 min full run |
| Database | PostgreSQL with pgvector |
| Stages shipped | 0–10 (see `docs/superpowers/plans/ROADMAP.md`) |

The roadmap's **decision log** is the fastest way to understand why the code
looks the way it does. Most of the non-obvious choices are recorded there with
their reasoning, including the mistakes.

---

## 1 · Prerequisites

- **Python 3.12+** — `python3 --version`
- **PostgreSQL 14+** with **pgvector** — the memory core needs both
- **Node 20+** — only for frontend work
- **git**

Optional, per feature:

| For | Install |
|---|---|
| PDF parsing | comes with `.[full]` |
| OCR of scans and images | `sudo apt install tesseract-ocr` (or `brew install tesseract`) |
| Local models | [Ollama](https://ollama.com) |

---

## 2 · Set up

```bash
git clone https://github.com/tawn-hq/tawn.git
cd tawn

python3 -m venv .venv
.venv/bin/pip install -e ".[full,dev]"
```

`-e` is an editable install: your changes take effect without reinstalling.
`[full]` pulls every provider and parser so the whole test suite can run;
`[dev]` adds pytest and respx.

### The database

```bash
sudo apt install -y postgresql postgresql-16-pgvector   # Debian/Ubuntu
sudo systemctl enable --now postgresql

.venv/bin/tawn db setup
```

`db setup` creates the database *and* enables the pgvector extension. Watch for
`pgvector enabled — semantic search available`. Without it Tawn still runs but
recall degrades to keyword matching, and a handful of tests behave differently
from CI.

### Enable the commit hook

```bash
git config core.hooksPath .githooks
```

This enforces Conventional Commits. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

### A global `tawn` for manual testing

The venv binary only exists while the venv is active. For a command that works
from any directory:

```bash
pipx install --force "$PWD[full]"
```

Re-run it after changes you want to exercise outside the repo. Note that this
is a *copy*, not a link — an editable venv install and a pipx install can drift
apart, which is a common source of "my fix did nothing".

---

## 3 · Verify

```bash
.venv/bin/python -m pytest -q
```

Expect **1,160 passed** in roughly four minutes. If Postgres is unreachable a
large block fails at once — that is the usual cause, not your change.

Then:

```bash
.venv/bin/tawn doctor
```

Every line should read `[ok]`.

---

## 4 · The frontend

```bash
cd frontend
npm install
npm run dev      # Vite dev server, proxies /api to :8787
```

Run `tawn web start` in another terminal so the API is there to proxy to.

For a production build:

```bash
npm run build    # tsc -b && vite build → frontend/dist
```

**The step people miss:** the wheel serves `src/tawn/web/dist`, not
`frontend/dist`. After building you must copy it across, or a `pipx` install
serves a stale UI while your dev server looks perfectly correct:

```bash
rm -rf ../src/tawn/web/dist && cp -r dist ../src/tawn/web/dist
```

`npm run build` takes 1–2 minutes, mostly Mermaid. Two builds at once appear to
hang — they are competing, not stuck. `npx tsc -b` alone typechecks in seconds
and catches most mistakes.

---

## 5 · Where things live

```
src/tawn/
├── capability/     grants, audit chain, integrity sidecar, mediated FS
├── compiler/       the pipeline: parse → chunk → embed → enrich → wiki
├── memory/         schema, recall, notes, attachments, document reconstruction
├── model/          router, providers, tools, agent loop, research, diagrams
│   ├── providers/  one adapter per vendor; OpenAI-compatible ones share one
│   ├── tools.py    the registry — every callable the model may reach
│   └── agent.py    the tool-calling loop
├── mcp/            Tawn as an MCP *client* (mcp_server.py is the server side)
├── skills/         skill store, sync out to other agents, import from them
├── tools/          generated-tool creator and loader
├── parsing/        format detection, extractors, safety harness, OCR
├── observer/       ambient work capture and authorship attribution
├── federation/     ingesting other agents' session logs
├── domains/        the plugin system (work, wealth, research, academic, hobby)
├── web/routes/     FastAPI routers, one per surface
└── migrations/     Alembic — inside the package so wheels ship them

frontend/src/
├── components/Shell.tsx   the app frame: grouped sidebar, header, Page heading
├── pages/                 one per route
├── ds/                    design system primitives
└── lib/                   api client, SSE, theme
```

---

## 6 · Things that will bite you

All discovered the hard way. Each one cost real time.

**Alembic autogenerate is not usable here.** `alembic.ini` pins an in-memory
SQLite URL, so autogenerate cannot see the real schema — and when it does run
it emits `pgvector...VECTOR(dim=…)` with no import. Write migrations by hand;
`versions/a1c4f9b02e77_stage9_observer.py` is a good template.

**Tests must never touch your real `~/.tawn`.** Use the `tawn_home` fixture,
which sets `TAWN_HOME`. Anything reading another tool's config (`~/.claude`,
`~/.codex`) honours a `TAWN_*` env override for the same reason — set it in
your tests, or your own files leak into assertions and pass for the wrong
reason.

**The vector column is deliberately dimensionless.** Pinning it to one
embedder's width meant every model switch broke compile. Rows of different
widths coexist; distance operators reject mixed comparisons, so changing
embedder still requires a re-embed.

**A running `tawn web` holds the code it started with.** After changing
anything the daemon touches: `tawn web stop && tawn web start`. `tawn doctor`
warns when the running process is older than the files on disk.

**`except Exception: pass` is load-bearing in the background loop** — compile,
enrich, reconcile and the observer are each best-effort by contract, so one
failing must not stop the others. It is also over-used (26 occurrences). Do not
add more without a comment saying why.

---

## 7 · Common tasks

**Add a model provider.** If it speaks the OpenAI dialect, add a factory to
`providers/openai_compat.py` and one entry to `CLOUD_REGISTRY` in `router.py` —
that is all. Tool calling and vision come along for free. Add a price to
`ledger.py` **from vendor documentation, never from memory**: an absent price
reports honestly as unpriced, a wrong one corrupts the spend dashboard
silently.

**Add a built-in tool.** `model/builtins.py` for generic primitives,
`model/extras.py` for anything that only makes sense because Tawn has a memory.
Declare its capabilities — the registry will not offer a tool whose capability
no grant backs.

**Add a document format.** An extractor in `parsing/extractors.py` plus an
entry in `FORMATS`. Check whether it is really ZIP+XML first; most "hard"
formats are, and the stdlib handles them for free.

**Change the schema.** Edit `memory/schema.py`, then hand-write the migration.

---

## 8 · The capability layer, honestly

`CONTRIBUTING.md` states that all filesystem I/O must go through
`tawn.capability.fs.MediatedFS`. **That rule is not enforced and has not been
followed:** there are 6 uses of `MediatedFS` against roughly 135 direct
`read_text`/`write_text` calls elsewhere in `src/`.

Worth knowing before you write code against the stated rule and wonder why
nothing around you looks like that.

What *is* real today:

- **Grants** (`~/.tawn/grants.yaml`) gate what the compiler indexes, which
  paths built-in tools may touch, which MCP servers may be called, and whether
  network and shell tools are offered at all. Those checks happen at call time,
  in `builtins.py`, `extras.py` and `tools.py`.
- **The audit chain** (`audit.jsonl`) is hash-linked and verified by
  `verify_chain()`.
- **The integrity sidecar** on `grants.yaml` means an edit Tawn did not perform
  must be acknowledged with `tawn grant confirm` before those grants load.

Reconciling the aspiration with the reality — either enforcing `MediatedFS`, or
rewriting the rule to describe the call-time model that actually exists — is
open work. See `docs/REVIEW-2026-07-27.md` §5.

---

## 9 · Security expectations for contributors

Current state is written up in
[`docs/REVIEW-2026-07-27.md`](docs/REVIEW-2026-07-27.md). Two things to hold
onto while working here:

**There is no authentication on the web API.** It binds `127.0.0.1` and must
stay that way. Do not add anything that exposes it — that is Stage 11's job and
it lands together with auth. `tawn web start --public` deliberately refuses.

**Content Tawn did not author is untrusted, and nothing currently marks it.**
Web pages, attachments, MCP results and compiled memory all reach the model in
the same turn as tools it can call. If you touch the agent loop, or add a tool
that returns external content, assume that content is adversarial.

---

## 10 · Where to start reading

1. `docs/superpowers/plans/ROADMAP.md` — the decision log, newest first
2. `src/tawn/capability/grants.py` — the permission model, ~150 lines
3. `src/tawn/model/tools.py` — what the model can reach, and why
4. `src/tawn/compiler/compiler.py` — the pipeline everything else feeds
