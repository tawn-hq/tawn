"""Research tests. No network: `searcher` and `fetcher` are always injected."""

import pytest

from tawn.model.research import (
    DEFAULT_SOURCES, ResearchResult, Source, _parse_queries, _unwrap_ddg,
    deep_research, diversify, gather_context,
)

DOMAINS = ["work", "wealth", "research", "academic", "hobby"]


class FakeClient:
    """Scripted model. Returns a plan, then gap queries, then prose."""

    def __init__(self, plan=None, gaps=None, contradictions="NONE", report="## Answer\nYes [1]."):
        self.plan = plan if plan is not None else ["q one", "q two"]
        self.gaps = gaps if gaps is not None else []
        self.contradictions = contradictions
        self.report = report
        self.prompts = []

    def complete(self, msgs, sensitive=True):
        prompt = msgs[0].content
        self.prompts.append(prompt)

        class R:
            pass

        r = R()
        if "distinct web search queries" in prompt:
            r.text = str(self.plan).replace("'", '"')
        elif "fill the biggest remaining gaps" in prompt:
            r.text = str(self.gaps).replace("'", '"')
        elif "genuinely disagree" in prompt:
            r.text = self.contradictions
        else:
            r.text = self.report
        return r


def fake_search(pages):
    def _search(query, limit=DEFAULT_SOURCES):
        return [
            Source(title=t, url=u, snippet=s)
            for t, u, s in pages
        ][:limit]

    return _search


def fake_fetch(body="page body"):
    return lambda url, limit=6000: f"{body} from {url}"


NO_SEARCH = lambda q, limit=DEFAULT_SOURCES: []
NO_FETCH = lambda u, limit=6000: ""


@pytest.fixture
def no_memory(monkeypatch):
    monkeypatch.setattr(
        "tawn.model.research.memory_sources", lambda q, d, limit: []
    )


@pytest.fixture
def no_model(monkeypatch):
    """No usable model anywhere.

    `client=None` means *auto-resolve*, and on a developer machine that finds a
    real Ollama config — so the genuine no-model path has to be forced.
    """
    def _boom(home):
        raise RuntimeError("no provider configured")

    monkeypatch.setattr("tawn.model.router.default_router", _boom)


# ── the loop ─────────────────────────────────────────────────────────────────

def test_it_plans_angles_rather_than_searching_the_question_verbatim(tmp_path, no_memory):
    client = FakeClient(plan=["angle a", "angle b", "angle c"])
    seen = []

    def _search(query, limit=6):
        seen.append(query)
        return []

    deep_research("why X", home=tmp_path, client=client, depth=1,
                  searcher=_search, fetcher=NO_FETCH)
    assert seen == ["angle a", "angle b", "angle c"]


def test_a_second_round_searches_the_gaps_the_model_names(tmp_path, no_memory):
    client = FakeClient(plan=["first"], gaps=["the gap"])
    seen = []

    def _search(query, limit=6):
        seen.append(query)
        return []

    r = deep_research("q", home=tmp_path, client=client, depth=2,
                      searcher=_search, fetcher=NO_FETCH)
    assert seen == ["first", "the gap"]
    assert r.rounds == 2


def test_it_stops_early_when_the_model_reports_no_gaps(tmp_path, no_memory):
    client = FakeClient(plan=["first"], gaps=[])
    seen = []

    def _search(query, limit=6):
        seen.append(query)
        return []

    deep_research("q", home=tmp_path, client=client, depth=4,
                  searcher=_search, fetcher=NO_FETCH)
    assert seen == ["first"]  # no wasted rounds


def test_duplicate_urls_are_fetched_once(tmp_path, no_memory):
    pages = [("T", "http://a.com/1", "s")]
    fetched = []
    client = FakeClient(plan=["a", "b"])
    deep_research(
        "q", home=tmp_path, client=client, depth=1,
        searcher=fake_search(pages),
        fetcher=lambda u, limit=6000: fetched.append(u) or "body",
    )
    assert fetched == ["http://a.com/1"]


def test_an_unreachable_page_keeps_its_snippet_instead_of_being_dropped(tmp_path, no_memory):
    def _boom(url, limit=6000):
        raise RuntimeError("404")

    r = deep_research(
        "q", home=tmp_path, client=FakeClient(plan=["a"]), depth=1,
        searcher=fake_search([("T", "http://a.com", "the snippet")]),
        fetcher=_boom,
    )
    assert r.sources[0].body == "the snippet"


# ── source diversity ─────────────────────────────────────────────────────────

def test_diversify_caps_pages_per_host(tmp_path):
    srcs = [Source(title=f"t{i}", url=f"http://vendor.com/{i}") for i in range(5)]
    srcs.append(Source(title="other", url="http://elsewhere.org/1"))
    kept = diversify(srcs, max_per_host=2)
    assert sum(1 for s in kept if s.host == "vendor.com") == 2
    assert any(s.host == "elsewhere.org" for s in kept)


def test_diversify_never_drops_memory_sources(tmp_path):
    srcs = [Source(title=f"m{i}", url="", origin="memory") for i in range(5)]
    assert len(diversify(srcs, max_per_host=1)) == 5


def test_one_vendor_cannot_dominate_a_run(tmp_path, no_memory):
    pages = [("T", f"http://vendor.com/{i}", "s") for i in range(6)]
    r = deep_research(
        "q", home=tmp_path, client=FakeClient(plan=["a"]), depth=1,
        searcher=fake_search(pages), fetcher=fake_fetch(),
    )
    assert len(r.sources) == 2  # MAX_PER_HOST


# ── cross-checking ───────────────────────────────────────────────────────────

def test_agreement_records_no_contradictions(tmp_path, no_memory):
    r = deep_research(
        "q", home=tmp_path, client=FakeClient(plan=["a"], contradictions="NONE"),
        depth=1, searcher=fake_search([("T", "http://a.com", "s")]), fetcher=fake_fetch(),
    )
    assert r.contradictions == ""
    assert "Where sources disagree" not in r.to_markdown()


def test_disagreement_is_surfaced_not_averaged(tmp_path, no_memory):
    r = deep_research(
        "q", home=tmp_path,
        client=FakeClient(plan=["a"], contradictions="[1] says 5%, [2] says 12%."),
        depth=1,
        searcher=fake_search([("T", "http://a.com", "s"), ("U", "http://b.org", "s")]),
        fetcher=fake_fetch(),
    )
    assert "5%" in r.contradictions
    assert "Where sources disagree" in r.to_markdown()


def test_a_single_source_cannot_contradict_itself(tmp_path, no_memory):
    r = deep_research(
        "q", home=tmp_path,
        client=FakeClient(plan=["a"], contradictions="[1] says 5%, [2] says 12%."),
        depth=1, searcher=fake_search([("T", "http://a.com", "s")]), fetcher=fake_fetch(),
    )
    assert r.contradictions == ""  # the cross-check pass never ran


# ── degradation ──────────────────────────────────────────────────────────────

def test_no_model_still_gathers_and_says_so(tmp_path, no_memory, no_model):
    r = deep_research(
        "q", home=tmp_path, client=None, depth=1,
        searcher=fake_search([("T", "http://a.com", "s")]), fetcher=fake_fetch(),
    )
    assert "not synthesised" in r.report
    assert len(r.sources) == 1  # evidence survives the missing model


def test_no_web_results_is_reported_as_a_limit(tmp_path, no_memory):
    r = deep_research("q", home=tmp_path, client=FakeClient(), depth=1,
                      searcher=NO_SEARCH, fetcher=NO_FETCH)
    assert any("no web results" in n for n in r.notes)


def test_empty_memory_is_reported_as_a_limit(tmp_path, no_memory):
    r = deep_research("q", home=tmp_path, client=FakeClient(), depth=1,
                      searcher=NO_SEARCH, fetcher=NO_FETCH)
    assert any("local memory" in n for n in r.notes)


def test_a_failing_searcher_does_not_end_the_run(tmp_path, no_memory):
    def _boom(query, limit=6):
        raise RuntimeError("network down")

    r = deep_research("q", home=tmp_path, client=FakeClient(plan=["a"]), depth=1,
                      searcher=_boom, fetcher=NO_FETCH)
    assert isinstance(r, ResearchResult)
    assert any("no web results" in n for n in r.notes)


def test_synthesis_failure_still_returns_the_sources(tmp_path, no_memory):
    class Failing(FakeClient):
        def complete(self, msgs, sensitive=True):
            if "research briefing" in msgs[0].content:
                raise RuntimeError("model exploded")
            return super().complete(msgs, sensitive)

    r = deep_research(
        "q", home=tmp_path, client=Failing(plan=["a"]), depth=1,
        searcher=fake_search([("T", "http://a.com", "s")]), fetcher=fake_fetch(),
    )
    assert "Synthesis failed" in r.report
    assert len(r.sources) == 1


# ── domains ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("domain", DOMAINS)
def test_the_domain_reaches_local_recall(tmp_path, monkeypatch, domain):
    seen = {}

    def _mem(question, dom, limit):
        seen["domain"] = dom
        return []

    monkeypatch.setattr("tawn.model.research.memory_sources", _mem)
    deep_research("q", domain=domain, home=tmp_path, client=FakeClient(),
                  depth=1, searcher=NO_SEARCH, fetcher=NO_FETCH)
    assert seen["domain"] == domain


@pytest.mark.parametrize("domain", DOMAINS)
def test_the_domain_reaches_the_prompts_and_the_report(tmp_path, no_memory, domain):
    client = FakeClient()
    r = deep_research("q", domain=domain, home=tmp_path, client=client,
                      depth=1, searcher=NO_SEARCH, fetcher=NO_FETCH)
    assert r.domain == domain
    assert f"*domain: {domain}*" in r.to_markdown()
    assert any(domain in p for p in client.prompts)


@pytest.mark.parametrize("domain", DOMAINS)
def test_remember_files_the_briefing_into_the_right_domain(tmp_path, no_memory, monkeypatch, domain):
    saved = {}

    def _note(payload, domain=None, type="observation", source=None, **kw):
        saved["domain"] = domain
        saved["source"] = source
        saved["payload"] = payload
        return {"ok": True}

    monkeypatch.setattr("tawn.memory.note.note", _note)
    r = deep_research("q", domain=domain, home=tmp_path, client=FakeClient(),
                      depth=1, remember=True, searcher=NO_SEARCH, fetcher=NO_FETCH)
    assert r.remembered is True
    assert saved["domain"] == domain
    assert saved["source"] == "deep_research"
    assert "# q" in saved["payload"]


def test_remember_is_off_by_default(tmp_path, no_memory, monkeypatch):
    called = []
    monkeypatch.setattr(
        "tawn.memory.note.note", lambda **kw: called.append(kw) or {"ok": True}
    )
    r = deep_research("q", home=tmp_path, client=FakeClient(), depth=1,
                      searcher=NO_SEARCH, fetcher=NO_FETCH)
    assert r.remembered is False
    assert called == []


def test_a_failed_save_is_a_note_not_a_crash(tmp_path, no_memory, monkeypatch):
    def _boom(**kw):
        raise RuntimeError("db down")

    monkeypatch.setattr("tawn.memory.note.note", _boom)
    r = deep_research("q", home=tmp_path, client=FakeClient(), depth=1,
                      remember=True, searcher=NO_SEARCH, fetcher=NO_FETCH)
    assert r.remembered is False
    assert any("could not save" in n for n in r.notes)


def test_memory_sources_outrank_web_in_the_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "tawn.model.research.memory_sources",
        lambda q, d, limit: [Source(title="my note", url="", body="mine", origin="memory")],
    )
    client = FakeClient(plan=["a"])
    deep_research("q", home=tmp_path, client=client, depth=1,
                  searcher=fake_search([("T", "http://a.com", "s")]), fetcher=fake_fetch())
    synth = next(p for p in client.prompts if "research briefing" in p)
    assert "MEMORY" in synth
    assert "higher authority" in synth


# ── context gathering ────────────────────────────────────────────────────────

def test_gather_context_searches_fixed_breadth_angles(tmp_path, no_memory):
    seen = []

    def _search(query, limit=3):
        seen.append(query)
        return []

    gather_context("pgvector", home=tmp_path, client=FakeClient(),
                   searcher=_search, fetcher=NO_FETCH)
    assert any("criticism" in q for q in seen)
    assert any("alternatives" in q for q in seen)
    assert any("latest" in q for q in seen)


@pytest.mark.parametrize("domain", DOMAINS)
def test_gather_context_carries_its_domain(tmp_path, no_memory, domain):
    r = gather_context("topic", domain=domain, home=tmp_path, client=FakeClient(),
                       searcher=NO_SEARCH, fetcher=NO_FETCH)
    assert r.domain == domain
    assert r.question == "Context: topic"


def test_gather_context_without_a_model_still_returns_sources(tmp_path, no_memory, no_model):
    r = gather_context("topic", home=tmp_path, client=None,
                       searcher=fake_search([("T", "http://a.com", "s")]),
                       fetcher=fake_fetch())
    assert "No model available" in r.report
    assert len(r.sources) >= 1


# ── helpers ──────────────────────────────────────────────────────────────────

def test_parse_queries_tolerates_prose_around_the_json():
    assert _parse_queries('Sure! ["a", "b"] hope that helps', 3) == ["a", "b"]
    assert _parse_queries("no json here", 3) == []
    assert _parse_queries('["a","b","c","d"]', 2) == ["a", "b"]


def test_ddg_redirect_is_unwrapped():
    assert _unwrap_ddg("//duckduckgo.com/l/?uddg=https%3A%2F%2Fx.org%2Fa&rut=1") == "https://x.org/a"
    assert _unwrap_ddg("https://plain.example") == "https://plain.example"


def test_report_markdown_names_source_provenance(tmp_path, no_memory):
    r = deep_research(
        "q", home=tmp_path, client=FakeClient(plan=["a"]), depth=1,
        searcher=fake_search([("T", "http://a.com", "s"), ("U", "http://b.org", "s")]),
        fetcher=fake_fetch(),
    )
    md = r.to_markdown()
    assert "from your memory" in md
    assert "across 2 sites" in md
    assert "## Angles searched" in md
