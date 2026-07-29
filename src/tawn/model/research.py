"""Deep research — plan, gather, cross-check, synthesise, remember.

The differentiator is that it searches the user's own compiled memory *and* the
web in the same pass. A web-only researcher is a worse Perplexity; a
memory-and-web researcher is the twin doing work only it can do, because only it
has read what the user has read.

A run:

    plan       decompose the question into sub-questions and search angles
    gather     local recall + web search per angle, capped per host for
               source diversity, then fetch bodies
    expand     the model names what is still missing; search that; repeat
    cross-check find claims the sources disagree on, rather than averaging them
    synthesise cited briefing, with confidence graded per claim
    remember   optionally write the briefing back into memory so the next
               question starts from this one's answer

Every network-touching step is injectable, so the whole loop is testable
without a network.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

MAX_DEPTH = 5
DEFAULT_SOURCES = 6
DEFAULT_ANGLES = 4
FETCH_CHARS = 6_000
SNIPPET_CHARS = 1_200
#: At most this many pages from any one host, so ten pages of one vendor's
#: marketing cannot look like consensus.
MAX_PER_HOST = 2


@dataclass
class Source:
    title: str
    url: str
    snippet: str = ""
    body: str = ""
    origin: str = "web"  # web | memory
    angle: str = ""

    @property
    def host(self) -> str:
        try:
            return urlparse(self.url).netloc.lower().removeprefix("www.")
        except Exception:
            return ""

    def cite(self, n: int) -> str:
        where = self.url or "local memory"
        return f"[{n}] {self.title} — {where}"


@dataclass
class ResearchResult:
    question: str
    domain: str | None
    report: str
    sources: list[Source] = field(default_factory=list)
    rounds: int = 1
    angles: list[str] = field(default_factory=list)
    contradictions: str = ""
    notes: list[str] = field(default_factory=list)
    remembered: bool = False

    @property
    def hosts(self) -> set[str]:
        return {s.host for s in self.sources if s.host}

    def to_markdown(self) -> str:
        out = [f"# {self.question}", ""]
        if self.domain:
            out.append(f"*domain: {self.domain}*\n")
        out += [self.report.strip(), ""]
        if self.contradictions.strip():
            out += ["## Where sources disagree", self.contradictions.strip(), ""]
        if self.sources:
            mem = sum(1 for s in self.sources if s.origin == "memory")
            out.append(
                f"## Sources ({len(self.sources)} — {mem} from your memory, "
                f"{len(self.sources) - mem} from the web across "
                f"{len(self.hosts)} sites)"
            )
            out += [s.cite(i) for i, s in enumerate(self.sources, 1)]
        if self.angles:
            out += ["", "## Angles searched"] + [f"- {a}" for a in self.angles]
        if self.notes:
            out += ["", "## Limits"] + [f"- {n}" for n in self.notes]
        return "\n".join(out)


# ── web search ───────────────────────────────────────────────────────────────

def web_search(query: str, limit: int = DEFAULT_SOURCES) -> list[Source]:
    """Search the web. Tries a keyed provider, falls back to DuckDuckGo.

    DuckDuckGo's HTML endpoint needs no key, which keeps research working on a
    fresh install; a keyed provider is preferred when configured because the
    result quality is better.
    """
    for provider in (_brave, _tavily, _duckduckgo):
        try:
            results = provider(query, limit)
            if results:
                return results
        except Exception:
            continue
    return []


def _key(name: str) -> str | None:
    import os

    value = os.environ.get(name)
    if value:
        return value
    try:
        import keyring

        return keyring.get_password("tawn", name)
    except Exception:
        return None


def _brave(query: str, limit: int) -> list[Source]:
    key = _key("BRAVE_API_KEY")
    if not key:
        return []
    import httpx

    resp = httpx.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": limit},
        headers={"X-Subscription-Token": key, "Accept": "application/json"},
        timeout=20,
    )
    resp.raise_for_status()
    return [
        Source(title=r.get("title", ""), url=r.get("url", ""),
               snippet=_strip_html(r.get("description", "")))
        for r in (resp.json().get("web", {}).get("results") or [])[:limit]
    ]


def _tavily(query: str, limit: int) -> list[Source]:
    key = _key("TAVILY_API_KEY")
    if not key:
        return []
    import httpx

    resp = httpx.post(
        "https://api.tavily.com/search",
        json={"api_key": key, "query": query, "max_results": limit},
        timeout=25,
    )
    resp.raise_for_status()
    return [
        Source(title=r.get("title", ""), url=r.get("url", ""),
               snippet=(r.get("content") or "")[:SNIPPET_CHARS])
        for r in (resp.json().get("results") or [])[:limit]
    ]


def _duckduckgo(query: str, limit: int) -> list[Source]:
    import httpx

    resp = httpx.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query},
        headers={"User-Agent": "Mozilla/5.0 (compatible; tawn-research)"},
        timeout=20,
        follow_redirects=True,
    )
    resp.raise_for_status()
    out: list[Source] = []
    for m in re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', resp.text, re.S
    ):
        url, title = m.group(1), _strip_html(m.group(2))
        if title:
            out.append(Source(title=title, url=_unwrap_ddg(url)))
        if len(out) >= limit:
            break
    return out


def _unwrap_ddg(href: str) -> str:
    """DuckDuckGo wraps results in a redirect; the real URL is in `uddg`."""
    m = re.search(r"uddg=([^&]+)", href)
    if not m:
        return href
    from urllib.parse import unquote

    return unquote(m.group(1))


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def fetch_page(url: str, limit: int = FETCH_CHARS) -> str:
    import httpx

    resp = httpx.get(
        url,
        timeout=20,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; tawn-research)"},
    )
    resp.raise_for_status()
    text = re.sub(
        r"(?is)<(script|style|nav|footer|header|aside)[^>]*>.*?</\1>", " ", resp.text
    )
    return re.sub(r"\s+", " ", _strip_html(text))[:limit]


# ── local memory ─────────────────────────────────────────────────────────────

def memory_sources(question: str, domain: str | None, limit: int) -> list[Source]:
    """What the twin already knows.

    Never fails the run: an empty corpus is a normal state on a fresh install,
    not an error.
    """
    try:
        from tawn.memory.recall import recall

        payload = recall(query=question, domain=domain, top_k=limit)
    except Exception:
        return []
    chunks = payload.get("chunks") or payload.get("results") or []
    out: list[Source] = []
    for c in chunks[:limit]:
        if not isinstance(c, dict):
            continue
        body = (c.get("content") or "")[:FETCH_CHARS]
        out.append(
            Source(
                title=c.get("title") or c.get("group_label")
                or c.get("source_path", "memory"),
                url="",
                snippet=body[:SNIPPET_CHARS],
                body=body,
                origin="memory",
                angle="local memory",
            )
        )
    return out


# ── prompts ──────────────────────────────────────────────────────────────────

_PLAN = """Research question: {question}
{domain_hint}
Break this into at most {n} distinct web search queries that together cover it.
Cover different angles — definitions, current state, criticisms, alternatives,
concrete numbers — not {n} rewordings of the same query.

Output ONLY a JSON array of strings."""

_GAPS = """Question: {question}

Evidence so far:

{evidence}

Name up to {n} web search queries that would fill the biggest remaining gaps.
Output ONLY a JSON array of strings. If the evidence already answers the
question, output []."""

_CONTRA = """Question: {question}

Evidence:

{evidence}

Identify points where these sources genuinely disagree — conflicting numbers,
dates, causal claims or recommendations. For each, state the disagreement in
one line and cite the conflicting sources as [n].

If they broadly agree, reply with exactly: NONE

Do not manufacture disagreement. Different emphasis is not conflict."""

_SYNTH = """You are writing a research briefing answering:

{question}
{domain_hint}
Evidence follows, numbered. Cite inline as [1], [2]. Sources marked MEMORY come
from the user's own notes and documents — treat them as higher authority on
anything about the user's own work, decisions or holdings.

{evidence}

Write markdown with exactly these sections:

## Answer
Three to six sentences. Lead with the answer, not preamble. Cite.

## Key findings
Bullets. Each cites at least one source, and each ends with a confidence tag —
**(high)** when several independent sources agree, **(medium)** when one solid
source supports it, **(low)** when it is inference or a single weak source.

## What this means for you
Two to four bullets, specific to what the MEMORY sources reveal about this
user's situation. If the memory sources say nothing relevant, write exactly:
"Nothing in your memory bears on this yet."

## Open questions
What the evidence does not settle. If everything is settled, one line saying so.

Never state as fact anything no source supports. Thin evidence must be
described as thin."""


def _domain_hint(domain: str | None) -> str:
    return f"\nThis belongs to the user's '{domain}' domain.\n" if domain else "\n"


def _evidence_block(sources: list[Source]) -> str:
    parts = []
    for i, s in enumerate(sources, 1):
        tag = "MEMORY" if s.origin == "memory" else (s.host or s.url)
        text = (s.body or s.snippet or "")[:FETCH_CHARS]
        parts.append(f"[{i}] {s.title} ({tag})\n{text}")
    return "\n\n".join(parts) or "(no evidence gathered)"


def _ask(client, prompt: str, allow_cloud: bool) -> str:
    from tawn.model.types import Message

    return client.complete(
        [Message(role="user", content=prompt)], sensitive=not allow_cloud
    ).text


def _parse_queries(text: str, limit: int) -> list[str]:
    m = re.search(r"\[.*\]", text or "", re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except Exception:
        return []
    return [str(q).strip() for q in items if isinstance(q, str) and str(q).strip()][:limit]


def diversify(sources: list[Source], max_per_host: int = MAX_PER_HOST) -> list[Source]:
    """Cap how many pages any single host contributes.

    Ten pages from one vendor's own site is one source wearing ten hats, and a
    synthesiser reading them will report manufactured consensus.
    """
    counts: dict[str, int] = {}
    kept: list[Source] = []
    for s in sources:
        if s.origin == "memory" or not s.host:
            kept.append(s)
            continue
        if counts.get(s.host, 0) >= max_per_host:
            continue
        counts[s.host] = counts.get(s.host, 0) + 1
        kept.append(s)
    return kept


# ── the loop ─────────────────────────────────────────────────────────────────

def deep_research(
    question: str,
    domain: str | None = None,
    depth: int = 2,
    sources: int = DEFAULT_SOURCES,
    angles: int = DEFAULT_ANGLES,
    home: Path | None = None,
    client=None,
    allow_cloud: bool = False,
    remember: bool = False,
    searcher=web_search,
    fetcher=fetch_page,
) -> ResearchResult:
    """Research a question against local memory and the web.

    `searcher` and `fetcher` are injected so the entire loop is testable
    without a network.
    """
    from tawn.home import tawn_home

    home = Path(home) if home else tawn_home()
    depth = max(1, min(depth, MAX_DEPTH))
    notes: list[str] = []

    if client is None:
        try:
            from tawn.model.router import default_router

            client = default_router(home)
        except Exception as exc:
            notes.append(f"no model available: {exc}")

    collected: list[Source] = memory_sources(question, domain, sources)
    if not collected:
        notes.append("nothing in local memory matched this question")

    # ── plan ─────────────────────────────────────────────────────────────
    queries = [question]
    if client is not None and angles > 1:
        try:
            planned = _parse_queries(
                _ask(
                    client,
                    _PLAN.format(
                        question=question, n=angles, domain_hint=_domain_hint(domain)
                    ),
                    allow_cloud,
                ),
                angles,
            )
            if planned:
                queries = planned
        except Exception:
            notes.append("planning failed — searched the question verbatim")

    searched: list[str] = []
    seen_urls: set[str] = set()
    rounds = 0

    # ── gather and expand ────────────────────────────────────────────────
    for round_no in range(depth):
        rounds = round_no + 1
        for query in queries:
            searched.append(query)
            try:
                hits = searcher(query, sources)
            except Exception:
                continue
            for hit in hits:
                if hit.url and hit.url in seen_urls:
                    continue
                if hit.url:
                    seen_urls.add(hit.url)
                hit.angle = query
                try:
                    hit.body = fetcher(hit.url) if hit.url else hit.snippet
                except Exception:
                    # An unreachable page is normal; keep whatever snippet the
                    # search gave us rather than discarding the lead.
                    hit.body = hit.snippet
                collected.append(hit)

        collected = diversify(collected)

        if round_no + 1 >= depth or client is None:
            break
        try:
            queries = _parse_queries(
                _ask(
                    client,
                    _GAPS.format(
                        question=question, evidence=_evidence_block(collected), n=3
                    ),
                    allow_cloud,
                ),
                3,
            )
        except Exception:
            break
        if not queries:
            break  # the model judges the evidence sufficient

    if not any(s.origin == "web" for s in collected):
        notes.append("no web results — check the `net:` grant and connectivity")

    # ── cross-check ──────────────────────────────────────────────────────
    contradictions = ""
    if client is not None and len(collected) > 1:
        try:
            raw = _ask(
                client,
                _CONTRA.format(
                    question=question, evidence=_evidence_block(collected)
                ),
                allow_cloud,
            ).strip()
            if raw and raw.upper() != "NONE":
                contradictions = raw
        except Exception:
            notes.append("cross-check pass failed")

    # ── synthesise ───────────────────────────────────────────────────────
    if client is None:
        report = (
            "No model was available, so the evidence below was gathered but not "
            "synthesised."
        )
    else:
        try:
            report = _ask(
                client,
                _SYNTH.format(
                    question=question,
                    evidence=_evidence_block(collected),
                    domain_hint=_domain_hint(domain),
                ),
                allow_cloud,
            )
        except Exception as exc:
            report = f"Synthesis failed ({exc}). The gathered sources are listed below."

    result = ResearchResult(
        question=question,
        domain=domain,
        report=report,
        sources=collected,
        rounds=rounds,
        angles=searched,
        contradictions=contradictions,
        notes=notes,
    )

    # ── remember ─────────────────────────────────────────────────────────
    if remember:
        try:
            from tawn.memory.note import note as _note

            _note(
                payload=result.to_markdown(),
                domain=domain,
                type="observation",
                source="deep_research",
            )
            result.remembered = True
        except Exception as exc:
            notes.append(f"could not save to memory: {exc}")

    return result


# ── contextual gathering ─────────────────────────────────────────────────────

def gather_context(
    topic: str,
    domain: str | None = None,
    angles: int = DEFAULT_ANGLES,
    per_angle: int = 3,
    home: Path | None = None,
    client=None,
    allow_cloud: bool = False,
    searcher=web_search,
    fetcher=fetch_page,
) -> ResearchResult:
    """Build a context pack about a topic — broader and shallower than research.

    Where `deep_research` answers a question, this one *surrounds a subject*:
    what it is, where it stands, who disputes it, what it connects to. It is
    what to reach for before writing or deciding, when the useful move is to
    load context rather than settle a question.
    """
    from tawn.home import tawn_home

    home = Path(home) if home else tawn_home()
    if client is None:
        try:
            from tawn.model.router import default_router

            client = default_router(home)
        except Exception:
            client = None

    # Fixed angles rather than model-planned: the point is predictable breadth.
    queries = [
        topic,
        f"{topic} explained",
        f"{topic} criticism problems limitations",
        f"{topic} alternatives comparison",
        f"{topic} latest developments",
    ][:max(1, angles + 1)]

    collected = memory_sources(topic, domain, per_angle * 2)
    seen: set[str] = set()
    for query in queries:
        try:
            hits = searcher(query, per_angle)
        except Exception:
            continue
        for hit in hits:
            if hit.url and hit.url in seen:
                continue
            if hit.url:
                seen.add(hit.url)
            hit.angle = query
            try:
                hit.body = fetcher(hit.url) if hit.url else hit.snippet
            except Exception:
                hit.body = hit.snippet
            collected.append(hit)

    collected = diversify(collected)

    if client is None:
        report = "No model available — raw sources gathered without synthesis."
    else:
        prompt = (
            f"Build a context briefing on: {topic}\n{_domain_hint(domain)}\n"
            f"{_evidence_block(collected)}\n\n"
            "Write markdown with exactly these sections:\n"
            "## What it is\nTwo or three sentences.\n"
            "## Current state\nWhere this stands now. Cite.\n"
            "## Points of contention\nWhat people disagree about. Cite.\n"
            "## Adjacent things worth knowing\nBullets, each one line.\n"
            "Cite as [n]. Do not assert what no source supports."
        )
        try:
            report = _ask(client, prompt, allow_cloud)
        except Exception as exc:
            report = f"Synthesis failed ({exc})."

    return ResearchResult(
        question=f"Context: {topic}",
        domain=domain,
        report=report,
        sources=collected,
        rounds=1,
        angles=queries,
    )
