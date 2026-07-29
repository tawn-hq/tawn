# Tawn — User Guide

Your twin, from nothing to working, then how to live with it.

Tawn is a local-first memory core. It reads what you already write — notes,
conversations, documents, repositories — and turns it into something you and
your AI tools can search, read and reason over. Your data stays on your
machine unless you explicitly say otherwise.

---

## Part 1 — Setup

### What Tawn does for you, and what only you can do

Tawn automates everything it can. Three things it cannot, because they need
your machine's root password or a secret only you hold:

| Step | Who | Why |
|---|---|---|
| Install PostgreSQL | **you** (`sudo`) | installing system packages needs root |
| Install the pgvector package | **you** (`sudo`) | same — a server-side extension |
| Install Tesseract *(only for OCR)* | **you** (`sudo`) | same — and only needed to read scans and images |
| Add API keys | **you** | they are your secrets; Tawn never invents or fetches them |
| Everything else | **Tawn** | home directory, database, extension, schema, migrations, model selection, first compile |

If a step below does not say "you", Tawn handles it.

### Requirements

- **Python 3.12 or newer** — check with `python3 --version`
- **PostgreSQL 14+** — Tawn's memory lives here
- **Ollama** *(optional)* — for private, free, offline models
- **Tesseract** *(optional)* — only to read scanned PDFs and images; see
  *Reading documents* in Part 2

### Step 1 — Install Tawn

```bash
pipx install tawn
```

`pipx` keeps Tawn isolated from your other Python packages while putting the
`tawn` command on your PATH. If you do not have it:

```bash
sudo apt install -y pipx && pipx ensurepath    # Debian/Ubuntu
brew install pipx && pipx ensurepath           # macOS
```

```powershell
py -m pip install --user pipx                  # Windows
py -m pipx ensurepath
```

Restart your shell afterwards so the PATH change takes effect. On Windows,
open a new PowerShell window.

Verify:

```bash
tawn --help
```

### Step 2 — Install PostgreSQL *(you)*

```bash
# Debian/Ubuntu
sudo apt install -y postgresql postgresql-16-pgvector
sudo systemctl enable --now postgresql

# Fedora
sudo dnf install -y postgresql-server pgvector
sudo postgresql-setup --initdb && sudo systemctl enable --now postgresql

# macOS
brew install postgresql@16 pgvector && brew services start postgresql@16
```

**Windows:** download the installer from
[postgresql.org/download/windows](https://www.postgresql.org/download/windows/)
and run it. During setup you will be asked to set a password for the
`postgres` user — remember it, you need it in the next step. Add pgvector
afterwards using **Stack Builder** (bundled with the installer) or by
following the [pgvector Windows instructions](https://github.com/pgvector/pgvector#windows).

Install `pgvector` **at the same time**. Without it Tawn still runs, but
search falls back to keyword matching instead of understanding meaning — and
that is the kind of quiet downgrade you would not otherwise notice.

#### Windows: tell Tawn how to connect

Linux and macOS use a Unix socket with peer authentication, so Tawn needs no
password. Windows has no Unix sockets, so Tawn defaults to a TCP connection
as user `tawn`. Either create that user, or point Tawn at the account you
made during installation:

```powershell
# PowerShell — for this session
$env:TAWN_DB_URL = "postgresql+psycopg://postgres:YOURPASSWORD@localhost/tawn"

# Or permanently, so every new shell has it
[Environment]::SetEnvironmentVariable(
  "TAWN_DB_URL",
  "postgresql+psycopg://postgres:YOURPASSWORD@localhost/tawn",
  "User")
```

Then continue with `tawn setup` as normal.

### Step 3 — Let Tawn set itself up

```bash
tawn setup
```

A four-step wizard; pressing Enter accepts every default.

1. **Home directory** — creates `~/.tawn/` with deny-all capability grants
2. **Database** — creates the `tawn` database *and* enables pgvector
3. **Local model** — offers Ollama models sized to your RAM
4. **Cloud keys** *(optional)* — stored in your OS keyring, never in files

Watch for this line in step 2:

```
pgvector enabled — semantic search available
```

If it instead warns that pgvector is not enabled, install the package from
step 2 and re-run `tawn db setup`. Everything works meanwhile; search is just
less capable.

### Step 4 — Check your work

```bash
tawn doctor
```

Every line should read `[ok]`. It checks Python, your home directory, the
database, grants integrity, and whether any running Tawn process is older
than the installed code.

### Step 5 — Give Tawn something to read

Tawn starts knowing nothing. Grant it read access to what you want
remembered:

```bash
tawn grant list                          # what it can see today (nothing, by default)
```

Grants live in `~/.tawn/grants.yaml`. Add paths under `read:`, then confirm
the change — Tawn checks that file for tampering, so edits need acknowledging:

```bash
tawn grant confirm
```

Then build the memory:

```bash
tawn compile
```

This reads your granted paths, filters out noise (lock files, build output,
stack traces), splits documents into searchable pieces, and embeds them.
The first run takes a while; later runs only process what changed.

### Step 6 — Make it readable

Compiling makes your memory *searchable*. Enrichment makes it *readable* —
titles, one-line summaries, and the entity graph:

```bash
tawn enrich
```

This uses your local model by default. It is resumable: run it as often as
you like, and stop it whenever you want.

### Step 7 — Open it

```bash
tawn web start
```

Then visit **http://tawn:8787**. If the hostname does not resolve, Tawn will
offer to add it to `/etc/hosts` (one `sudo` prompt), or use
`http://127.0.0.1:8787`.

---

## Part 2 — Living with it

### The daily loop

```
you write / work  →  tawn compile  →  tawn enrich  →  searchable, readable memory
```

Both run automatically every 30 minutes while `tawn web` is running, so in
practice you rarely invoke them by hand.

### Notes — telling your twin things directly

Most of Tawn's memory is gathered. Notes are what you tell it deliberately.

From the CLI:

```bash
tawn note "Decided to use pgvector over Pinecone — no external dependency."
tawn note --domain wealth "Rebalancing to 60/40 in Q3."
```

From the web: the **notes** page, or the card on your dashboard. Unlike
gathered memory, notes are yours to revise — edit or delete any of them, and
the change recompiles into memory.

### Recall — asking your memory questions

```bash
tawn recall "what did I decide about vector storage"
tawn recall --domain work "deployment approach"
```

Recall searches by *meaning*, not keywords, so you do not have to remember
your own phrasing. The web **memory** page does the same with a search box.

### The feed — what your twin knows

The **memory** page shows one card per document or conversation, not one per
fragment. Expanding a card reassembles the whole document from its stored
pieces, so you read the thing rather than the index.

Chunks remain the unit for *search* — that is what makes recall precise — but
they are the wrong unit for reading, so the feed hides that seam.

### The wiki — what your twin worked out

The **wiki** page is the entity graph: people, projects, tools and places
Tawn found in your memory, and how they relate.

```bash
tawn wiki                       # what exists
tawn wiki work                  # a domain's index
tawn wiki entity ClauseWise     # one entity, its links and backlinks
tawn wiki graph ClauseWise      # its neighbourhood, in the terminal
```

Pages use Obsidian-style `[[wikilinks]]`, so `~/.tawn/wiki/` opens directly
as an Obsidian vault if you use one.

### The observer — what you and your agents did

Tawn can watch the projects you have granted it and record what changed, who
changed it, and what is worth a second look. It is off until you turn it on:

```yaml
# ~/.tawn/grants.yaml
observe: [fs, git, agents]
```

Each entry enables one source: `fs` for file changes, `git` for commit
authorship, `agents` for correlating writes against your coding agents' own
session logs. That last one is what lets Tawn say *Claude Code wrote this*
about code you have not committed yet.

```bash
tawn observe status             # which sources are on, what is pending
tawn observe projects           # what it is watching
tawn observe review             # close the session and write the note now
```

When a work session ends — you commit, or you stop for 20 minutes — Tawn writes
a review note to `<your write grant>/reviews/<project>/<date>.md`: what changed,
who changed it, and what to revisit. Sessions also appear on the **activity**
page alongside model spend.

The observer only ever watches paths you granted under `read:`, and it never
looks at your windows, applications or processes. Attribution it is not certain
about is labelled *likely*, and attribution it cannot make at all is recorded as
`unknown` rather than guessed — a confident wrong answer about who wrote your
code is worse than no answer.

Tune it in `~/.tawn/config.yaml` if the defaults do not fit:

```yaml
observer:
  idle_minutes: 20              # how long a pause ends a session
  correlation_window_seconds: 90
```

### Tools — what your twin can do

Out of the box your twin can read your memory. Turn tools on and it can also
read files and documents, search the web, research a question against your own
notes *and* the web, draw diagrams, and call any MCP server you allow.

In chat, the **tools** menu next to the composer switches them on for a turn.
Whatever it used shows up above the answer, and you can expand any call to see
exactly what came back — no invisible actions.

```bash
tawn mcp adopt                  # find MCP servers your other tools configure
tawn mcp enable <name>          # turn one on
tawn mcp test <name>            # connect and list its tools
```

A server is callable only when it is **enabled** *and* its name appears under
`mcp:` in `grants.yaml`. Two switches on purpose: the grant is your security
decision, the toggle is your convenience one, and disabling something
temporarily should not throw away the first.

Some tools need a capability you have not granted yet:

```yaml
# ~/.tawn/grants.yaml
net: true      # let tools reach the network — web search, fetching pages
shell: true    # let tools run shell commands — the widest grant here
```

Tools whose capability is not granted are not offered to the model at all,
rather than offered and then refused on every call.

### Reading documents — OCR setup *(you)*

Tawn reads most formats with nothing extra installed. Word, Excel, PowerPoint,
OpenDocument and EPUB are all ZIP-and-XML underneath, so Python's standard
library handles them for free.

Two things need help:

| Format | Needs | Install |
|---|---|---|
| PDF (with text) | a PDF library | `pipx inject tawn pymupdf` |
| Scanned PDF, images | Tesseract OCR | see below — **needs `sudo`** |

**Installing Tesseract.** This is one of the few steps Tawn cannot do for you,
because it installs a system package:

```bash
sudo apt install -y tesseract-ocr        # Debian/Ubuntu
sudo dnf install -y tesseract            # Fedora
brew install tesseract                   # macOS
```

**Windows:** download the installer from
[UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki), run it,
and tick *Add to PATH* during setup. Reopen your terminal afterwards.

Then give Tawn the Python bindings:

```bash
pipx inject tawn pytesseract Pillow pymupdf
```

For other languages, install the language pack and Tesseract picks it up —
`sudo apt install tesseract-ocr-fra` for French, and so on.

**Checking it works.** Attach a scanned PDF or a photo of a page in chat. If
OCR is missing you get a message naming exactly what to install, not a silent
failure.

**A performance note worth knowing.** Tesseract links OpenMP, and its thread
pool thrashes badly on ordinary multi-core machines — the same page measured
2m23s unconstrained and 4.7s with the pool pinned to one thread. Tawn pins it
for you, so you should never see the slow path. If you run `tesseract` yourself
and it crawls, `OMP_THREAD_LIMIT=1` is the reason.

### Attachments — how they are handled

Drop a file into chat with the **+** button and Tawn parses it *immediately*,
while you are still typing. The pill shows the format and size once it is
ready.

That timing matters. Parsing on send instead would mean the wait lands after
you press enter, and the document's text would ride along in the conversation
history — re-sent on every later turn until the request grew too large and the
chat simply stopped responding. Instead the text is stored once and joins the
model's context only for the turn you attached it to.

Folders work too: **+ → attach a folder** skips `node_modules`, `.git`, `dist`
and other build directories, and caps at 40 files.

### Skills — write once, use everywhere

A skill is a set of instructions your agents can follow. Tawn uses the same
`SKILL.md` format Claude Code does, so a Tawn skill *is* a Claude Code skill —
no conversion, nothing to keep in sync.

```bash
tawn skill new review -d "review my migrations for lock risk"
tawn skill sync                 # project them into every agent on this machine
tawn skill import --dry-run     # pull in skills those agents already have
```

Sync never deletes or overwrites a file it did not write. A skill you wrote by
hand under the same name is reported as a conflict and left exactly as it is.
Import dedupes on name *and* content, so syncing out and importing back does
not fork a skill against itself.

### Generated tools — describe it, review it, then enable it

Your twin can write its own tools:

```bash
tawn tool new "fetch the current NGX price for a ticker"
tawn tool show ngx_price        # the manifest and the source
tawn tool enable ngx_price
```

Every generated tool arrives **disabled**. The manifest declares what access
the code needs, and that declaration is checked against the source by static
analysis — a tool claiming less than it does is rejected outright, because a
model's account of its own code is not evidence.

Read the source before enabling anything. An enabled tool runs in Tawn's own
process with Tawn's access. The capability check stops a tool acquiring access
you never granted and stops it running before a human has looked at it, but it
is not a sandbox.

The **tools** page in the web UI does all of this — servers, skills and
generated tools in three tabs.

### Domains

Memory is filed into life-areas: **work**, **wealth**, **research**,
**academic**, **hobby**. Tawn infers the domain where it can, and leaves it
unset where it genuinely cannot — an honest blank beats a wrong label.

```bash
tawn brief work                 # what is going on in a domain
```

### Chat

```bash
tawn chat
```

A conversation with your twin, with your memory as context. Slash commands
mirror what you already know: `/recall`, `/note`, `/wiki`, `/graph`,
`/compile`, `/brief`, `/model`, `/status`.

### Connecting your AI tools

Tawn speaks MCP, so Claude Code and other MCP clients can query your memory
directly. Add to `~/.claude/claude.json`:

```json
{
  "mcpServers": {
    "tawn": { "command": "tawn", "args": ["mcp"] }
  }
}
```

Your tools then share one memory instead of each starting from nothing.

---

## Part 3 — Privacy and control

### Nothing leaves your machine by default

Local models handle everything unless you opt in. Two explicit opt-ins exist,
both off by default:

```bash
tawn enrich --cloud             # send chunk text to a cloud model
```

```yaml
# ~/.tawn/config.yaml
embed_allow_cloud: true         # allow cloud embedding
```

Embedding is called out separately because it sends your *entire corpus*,
which is a different exposure from one chat message. Tawn refuses to fall
back to a paid remote provider silently — if no local model is available it
stops and says so.

### Grants

Tawn cannot read anything you have not granted. Every file access is checked
against `~/.tawn/grants.yaml` and written to an audit log with a tamper-evident
hash chain.

```bash
tawn grant list
tawn grant confirm              # acknowledge an edit to grants.yaml
```

### Cost

```bash
tawn ledger                     # every model call: provider, tokens, cost
```

Local calls cost nothing and are still recorded, because call volume is what
explains a slow run.

---

## Part 4 — Maintenance

| Command | When |
|---|---|
| `tawn doctor` | anything feels wrong — checks every subsystem |
| `tawn compile` | after adding files or grants |
| `tawn compile --rebuild` | after changing chunking or extraction rules; re-reads everything |
| `tawn enrich` | to fill in titles, summaries and the entity graph |
| `tawn reembed` | after changing the embedding model |
| `tawn observe status` | is the observer on, and are notes pending |
| `tawn mcp list` | which MCP servers are registered, enabled and granted |
| `tawn skill sync` | after writing or editing a skill |
| `tawn tool list` | which generated tools exist and whether they are live |
| `tawn web status` | is the server up, and is it running current code |
| `tawn update` | upgrade Tawn itself |

### Changing the embedding model

Embeddings from different models are not comparable, even at the same
dimension count. After switching models, existing vectors are stale and
recall will quietly ignore them:

```bash
tawn reembed --status           # how many are stale
tawn reembed                    # redo them in place
```

### If something looks stale

A long-running Tawn process keeps the code it started with. After upgrading:

```bash
tawn web stop && tawn web start
```

`tawn doctor` warns when a running process is older than the installed code.

---

## Platform notes

Tawn runs on Linux, macOS and Windows. Everything in this guide works on all
three; these are the differences worth knowing.

| | Linux | macOS | Windows |
|---|---|---|---|
| Database connection | Unix socket, no password | Unix socket, no password | TCP — set `TAWN_DB_URL` |
| API key storage | Secret Service | Keychain | Credential Manager |
| Background scheduling | systemd timers | manual | manual |
| `tawn` hostname | offered automatically | offered automatically | edit hosts file manually |

**Background scheduling.** Automatic snapshots and the federation watcher
install as systemd user timers on Linux. On macOS and Windows Tawn tells you
what to run instead of installing a job — `tawn web start` keeps the
30-minute compile and enrich loop going in the meantime, which covers most
of what the timers do.

**The `tawn` hostname on Windows.** Tawn cannot edit the hosts file for you
there. Either use `http://127.0.0.1:8787`, or add this line to
`C:\Windows\System32\drivers\etc\hosts` in an Administrator editor:

```
127.0.0.1  tawn
```

**API keys** need no extra setup on any platform — `keyring` uses whatever
the OS provides.

---

## Troubleshooting

**`tawn doctor` says the database is unreachable**
PostgreSQL is not running. Start it — `sudo systemctl start postgresql` on
Linux, `brew services start postgresql@16` on macOS, or the *postgresql*
service in Windows Services — then re-run.

On Windows this usually means `TAWN_DB_URL` is unset or has the wrong
password; see *Windows: tell Tawn how to connect* above.

**Search returns odd or shallow results**
pgvector may not be enabled, so search is keyword-only. Run `tawn db setup`
and look for the pgvector line.

**The feed is empty but you have compiled**
Compiling makes memory searchable; the feed groups it into documents. Run
`tawn compile` again — grouping is built during compile.

**Cards show filenames instead of titles**
Enrichment has not reached them yet. Run `tawn enrich`, or wait for the
background pass.

**`http://tawn:8787` does not resolve**
Use `http://127.0.0.1:8787`, or let Tawn add the hostname:
`tawn web start` offers this once.

**A scanned PDF or image comes back empty**
Tesseract is not installed. See *Reading documents — OCR setup* in Part 2. Tawn
names exactly what is missing rather than failing silently, so read the message
in the attachment pill.

**Attaching a document feels slow**
Parsing happens on attach, so a large scanned PDF takes a moment — the pill
says `reading…` while it works, and send is blocked until it finishes. That
wait is deliberate: it happens once, instead of on every turn.

**Changes to the code do not take effect**
A running process holds old code. `tawn web stop && tawn web start`.

---

## Where things live

```
~/.tawn/
├── raw/              your notes and imported sources (never edited by Tawn)
├── wiki/             generated entity pages and domain indexes
├── history/          chat transcripts
├── grants.yaml       what Tawn may read and write
├── config.yaml       models and preferences
├── skills/           skills you wrote or imported
├── tools/            tools your twin generated (disabled until you enable them)
├── artifacts/        diagrams and briefings, versioned and append-only
├── mcp/              MCP server registry and tool catalogue
├── audit.jsonl       every access, hash-chained
└── ledger.jsonl      every model call and its cost
```

Review notes are the exception: they live under your `write:` grant, not in
`~/.tawn/`, because they are output you own rather than Tawn's internal state.

Everything is plain text. You can read it, grep it, back it up, or delete it
without Tawn's help — that is the point of local-first.
