# Tawn — What You Get

> The user-facing view: what Tawn does for you once the build is done.
> Companion to `docs/PRD.md` (product requirements) and the technical design spec.
> Written as outcomes and scenes, not architecture.

---

## The one-sentence promise

**Every AI tool you use shares one private brain that knows your work, your money,
your research, and your studies — and keeps itself up to date so it never lies to
you with stale context.**

You install it once as a CLI. You grant it access to a few folders and accounts.
From then on, it reads quietly, writes only where you let it, and makes every
agent you touch smarter about *you*.

---

## How you meet it

You type `tawn` and land in a conversational prompt that feels like Claude Code —
streaming answers, slash commands, a session that remembers. You can also just let
it run in the background while you work in VS Code, and it watches and learns
without you typing anything.

Three things you ever really do:
- **ask it** — `recall` something across any domain
- **tell it** — `note` a decision or fact
- **get briefed** — `brief` a domain for today's summary

Everything else maintains itself.

---

## A day with Tawn

**Morning.** You open the terminal. `tawn brief research` gives you the few new
papers that actually matter to your threads (ClauseWise, AfriVTON) — cross-checked
against what you already know, not a raw feed. `tawn brief wealth` shows your
net-worth view: NGX + USD + land + cash in one number, dividend dates coming up,
and a quiet flag that your banking exposure has drifted from your blueprint. It
will never move your money — it only ever shows you.

**Work.** You open a repo in VS Code and start coding; one of your agents pairs
with you. Tawn is watching the project folder you granted it. It notices what
changed — and *who* changed it, you or which agent. When you wrap the session, a
review note appears in your reviews folder: what moved, what looks risky, what to
revisit. Weeks later, when something regressed, you can ask which agent introduced
it. No other twin can tell you that.

**Research → Academic, the magic moment.** You ask Tawn to draft a section of your
PhD proposal. It doesn't start from a blank page — it pulls evidence from your
*shipped work*, your *papers*, and your *reading list* at once, because to Tawn the
person who is your collaborator, your co-author, and your contact is **one node**,
and the topics linking them are already mapped. One twin does what four tools
couldn't.

**Afternoon.** A frontier model you're using hits its quota mid-task. You don't
notice. Tawn classifies the failure, switches to another provider you've added,
hands off a compact summary of where you were, and keeps going — logged, so you
can see exactly what happened later. If everything frontier is down, it falls back
to your local model and tells you it's running lighter.

**Evening.** The knowledge core quietly recompiles. New notes get cross-linked
against everything already there, so your 50th source sharpens the 1st.
Contradictions get flagged for you instead of silently rotting. Anything past its
freshness window gets marked stale, so tomorrow's answers come with honest
"this may be out of date" labels instead of confident wrong context.

---

## What you can see and touch

- **The CLI / REPL** — your main way in; ask, tell, get briefed, run commands.
- **The wiki** — your knowledge as plain markdown. Have Obsidian? Point it at the
  folder for the graph view. Don't? `tawn web` opens a built-in viewer with the
  same notes and an entity-graph map, right from Tawn.
- **The ledger** — `tawn ledger` shows what ran locally vs in the cloud, and what it
  cost. You can *see* your privacy and spend, not guess.
- **Grants** — `tawn grant list` shows exactly what Tawn can read, write, and watch.
  Revoke anything anytime.

---

## What it will never do

- Out of the box, never moves, trades, or spends your money — the core is
  read-only. If you ever *want* it to act, that's an extra integration you install
  on purpose, and it still asks you before every single action.
- Never sends a message, submits an application, or spends without asking you first.
- Never writes anywhere you didn't explicitly allow.
- Never sends content you marked sensitive to a cloud model.
- Never silently merges two people into one, or serves you a stale fact as fresh.

---

## Why it compounds

Most assistants start over every conversation. Tawn gets **more** useful the longer
you use it: every note cross-links the graph, every accepted or rejected suggestion
teaches it your taste, every review note builds your project history. It learns
*how* you think (your personality) separately from *what's* true about you (your
identity) — and it stays correctable, so it never hardens into a caricature of you.

Four tools that forget you, replaced by one private twin that remembers — and that
every agent you already use can share.

---

*ℵ → ת — the first letter answered by the last; your mark, your twin.*
