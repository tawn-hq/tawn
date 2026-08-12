import datetime

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SASession

from tawn.memory.schema import Base
from tawn.observer import review as rv
from tawn.observer.attribution import Attribution
from tawn.observer.sessions import close_session, current_session, record_event

T0 = datetime.datetime(2026, 7, 26, 14, 2, tzinfo=datetime.timezone.utc)


@pytest.fixture(autouse=True)
def _never_call_a_real_model(monkeypatch):
    """No test here is about the model, and one of them loops five times.

    Without this, a change to `note_path_for` that stopped returning None sent
    four tests down the compose path and into real tinyllama calls — the suite
    went from under two seconds to twenty-three minutes. Stub by default; tests
    that care about the analysis override it.
    """
    monkeypatch.setattr(rv, "_analyse", lambda *a, **k: "### What changed\nStub.\n")


def _sess():
    e = create_engine("sqlite://")
    Base.metadata.create_all(e)
    return SASession(e)


def _home(tmp_path, write_dir="out"):
    (tmp_path / "grants.yaml").write_text(
        f"read: []\nwrite: [{tmp_path / write_dir}]\nobserve: [fs]\n"
    )
    (tmp_path / write_dir).mkdir(exist_ok=True)
    return tmp_path


def _seeded(s):
    record_event(
        s, "tawn", "/x/a.py", "modified",
        Attribution("agent:claude-code", "high", "session"), T0, 40, 3,
    )
    record_event(
        s, "tawn", "/x/b.py", "added", Attribution("human", "high", "git"), T0, 10, 0
    )
    record_event(
        s, "tawn", "/x/c.py", "modified",
        Attribution("agent:unknown", "low", "timing"), T0, 5, 1,
    )
    return close_session(s, current_session(s, "tawn"), T0, "commit")


def test_low_confidence_reads_as_likely_not_as_fact():
    s = _sess()
    sess = _seeded(s)
    events = rv._events(s, sess)
    summary = rv.attribution_summary(events)
    assert "1 agent:claude-code" in summary
    assert "1 human" in summary
    assert "likely" in summary  # the timing guess is hedged
    assert "1 agent:unknown," not in summary


def test_note_is_written_under_tawn_home(tmp_path, monkeypatch):
    """Notes belong in `~/.tawn/reviews/`, not in the first write grant.

    Using `write[0]` filed every project's notes in whichever directory happened
    to be granted first — notes about `engine` landed in the `tawn` repository —
    and gave Tawn nowhere to write when no grant existed at all.
    """
    s = _sess()
    sess = _seeded(s)
    monkeypatch.setattr(rv, "_analyse", lambda *a, **k: "### What changed\nStuff.\n")
    out = rv.write_note(s, sess, _home(tmp_path))
    assert out.note_state == "written"
    p = tmp_path / "reviews" / "tawn" / "2026-07-26.md"
    assert p.exists()
    body = p.read_text()
    assert "agent:claude-code" in body
    assert "Stuff." in body


def test_second_session_the_same_day_appends(tmp_path, monkeypatch):
    s = _sess()
    monkeypatch.setattr(rv, "_analyse", lambda *a, **k: "### What changed\nOne.\n")
    rv.write_note(s, _seeded(s), _home(tmp_path))
    rv.write_note(s, _seeded(s), _home(tmp_path))
    p = tmp_path / "reviews" / "tawn" / "2026-07-26.md"
    assert p.read_text().count("## 14:02") == 2


def test_no_model_still_writes_the_facts(tmp_path, monkeypatch):
    s = _sess()
    sess = _seeded(s)

    def _boom(*a, **k):
        raise RuntimeError("no model available")

    monkeypatch.setattr(rv, "_analyse", _boom)
    out = rv.write_note(s, sess, _home(tmp_path))
    assert out.note_state == "unanalysed"
    body = (tmp_path / "reviews" / "tawn" / "2026-07-26.md").read_text()
    assert "3 files" in body
    assert "agent:claude-code" in body  # losing analysis must not lose record


def test_no_write_grant_still_gets_a_note(tmp_path):
    """A missing write grant used to mean the note could never be written and the
    session stayed pending forever. Tawn's own home needs no grant — it already
    holds the audit log, the ledger and chat history."""
    s = _sess()
    sess = _seeded(s)
    (tmp_path / "grants.yaml").write_text("read: []\nwrite: []\nobserve: [fs]\n")

    out = rv.write_note(s, sess, tmp_path)

    assert out.note_state == "written"
    assert out.note_path == str(tmp_path / "reviews" / "tawn" / "2026-07-26.md")
    assert (tmp_path / "reviews" / "tawn" / "2026-07-26.md").exists()


def test_configured_notes_dir_needs_a_write_grant(tmp_path):
    """Pointing notes at a vault or repo makes it one of *your* directories, so
    the grant model applies. Ungranted falls back rather than dropping the note."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (tmp_path / "grants.yaml").write_text("read: []\nwrite: []\nobserve: [fs]\n")
    (tmp_path / "config.yaml").write_text(f"observer:\n  notes_dir: {vault}\n")
    assert rv.note_path_for(tmp_path, "tawn", T0.date()) == (
        tmp_path / "reviews" / "tawn" / "2026-07-26.md"
    )

    (tmp_path / "grants.yaml").write_text(
        f"read: []\nwrite: [{vault}]\nobserve: [fs]\n"
    )
    assert rv.note_path_for(tmp_path, "tawn", T0.date()) == (
        vault / "tawn" / "2026-07-26.md"
    )


def test_each_project_gets_its_own_directory(tmp_path):
    """`write[0]` put every project's notes in one place — `engine` notes were
    written into the `tawn` repository."""
    (tmp_path / "grants.yaml").write_text("read: []\nwrite: []\nobserve: [fs]\n")
    a = rv.note_path_for(tmp_path, "tawn", T0.date())
    b = rv.note_path_for(tmp_path, "engine", T0.date())
    assert a.parent != b.parent
    assert a.parent.name == "tawn" and b.parent.name == "engine"


def test_attempts_are_bounded(tmp_path):
    """Retries stop. Failure is forced by making the notes directory unwritable —
    now that a path is always available, an OSError is the only way it can fail."""
    s = _sess()
    sess = _seeded(s)
    (tmp_path / "grants.yaml").write_text("read: []\nwrite: []\nobserve: [fs]\n")
    (tmp_path / "reviews").write_text("not a directory")

    for _ in range(rv.MAX_NOTE_ATTEMPTS + 2):
        rv.write_note(s, sess, tmp_path)

    assert sess.note_state == "failed"
    assert sess.note_attempts == rv.MAX_NOTE_ATTEMPTS


def test_process_pending_only_touches_pending_sessions(tmp_path, monkeypatch):
    s = _sess()
    _seeded(s)
    monkeypatch.setattr(rv, "_analyse", lambda *a, **k: "### What changed\nX.\n")
    assert rv.process_pending(s, _home(tmp_path)) == 1
    assert rv.process_pending(s, _home(tmp_path)) == 0


def test_file_list_is_rendered_from_the_record_not_the_model(tmp_path, monkeypatch):
    """The changed-file list must come from the database, never from a model.

    A small model asked for prose will sometimes echo the listing it was given
    and corrupt a path doing it. A wrong path inside a document that reads like
    a record is worse than no document, so the facts are rendered here and the
    model is never in that path.
    """
    s = _sess()
    sess = _seeded(s)
    monkeypatch.setattr(rv, "_analyse", lambda *a, **k: "### What changed\nProse.\n")
    body, _ = rv.compose(s, sess, _home(tmp_path))
    for path in ("/x/a.py", "/x/b.py", "/x/c.py"):
        assert path in body
    # Per-file attribution travels with each line, not only in the summary.
    assert "agent:claude-code" in body
    assert "+40 −3" in body


def test_a_model_echoing_the_listing_cannot_corrupt_the_record(tmp_path, monkeypatch):
    """Observed live: tinyllama echoed the listing back with `observer` -> `observor`."""
    s = _sess()
    sess = _seeded(s)
    monkeypatch.setattr(
        rv, "_analyse", lambda *a, **k: "- modified /x/CORRUPTED.py (+1 -0) [nobody]"
    )
    body, state = rv.compose(s, sess, _home(tmp_path))
    assert "/x/a.py" in body           # the real record survives
    assert state == rv.UNANALYSED      # and the echo is not accepted as analysis


def test_analysis_without_the_expected_heading_is_not_counted_as_written(
    tmp_path, monkeypatch
):
    s = _sess()
    sess = _seeded(s)
    monkeypatch.setattr(rv, "_analyse", lambda *a, **k: "Sure! Here is the summary.")
    body, state = rv.compose(s, sess, _home(tmp_path))
    assert state == rv.UNANALYSED
    assert "analysis skipped" in body
    assert "/x/a.py" in body           # facts still recorded


def test_valid_analysis_is_kept_and_marked_written(tmp_path, monkeypatch):
    s = _sess()
    sess = _seeded(s)
    monkeypatch.setattr(
        rv, "_analyse",
        lambda *a, **k: "### What changed\nReal prose.\n### Worth another look\n- a.py",
    )
    body, state = rv.compose(s, sess, _home(tmp_path))
    assert state == rv.WRITTEN
    assert "Real prose." in body


def test_review_target_prefers_a_capable_local_model(tmp_path, monkeypatch):
    """qwen3:0.6b outranks tinyllama:1.1b despite fewer parameters.

    Writing a note is instruction-following, not recall, and tinyllama was
    observed echoing its input instead of answering.
    """
    from tawn.observer import config as ocfg

    class _Fake:
        def installed_models(self):
            return [
                {"name": "tinyllama:1.1b", "size": 1},
                {"name": "qwen3:0.6b", "size": 2},
                {"name": "nomic-embed-text:latest", "size": 3},
            ]

    monkeypatch.setattr("tawn.model.providers.ollama.OllamaProvider", lambda *a, **k: _Fake())
    assert rv.review_target(tmp_path, use_cloud=False) == "ollama/qwen3:0.6b"
    # Embedding models can't answer a prompt and must never be selected.
    assert ocfg.is_chat_capable("nomic-embed-text:latest") is False


def test_explicit_model_beats_cloud_and_config(tmp_path):
    assert rv.review_target(tmp_path, use_cloud=True, model="ollama/x") == "ollama/x"
    assert rv.review_target(tmp_path, use_cloud=False, model="anthropic/y") == "anthropic/y"


def test_cloud_defers_to_the_router_chain(tmp_path):
    """None means "normal preference + failover" — naming a provider here would
    break as soon as its key is removed."""
    assert rv.review_target(tmp_path, use_cloud=True) is None


def test_configured_review_model_wins_over_autodetection(tmp_path):
    (tmp_path / "config.yaml").write_text("observer:\n  review_model: ollama/pinned\n")
    assert rv.review_target(tmp_path, use_cloud=False) == "ollama/pinned"


def test_no_installed_model_degrades_to_the_default_chain(tmp_path, monkeypatch):
    class _None:
        def installed_models(self):
            return []

    monkeypatch.setattr("tawn.model.providers.ollama.OllamaProvider", lambda *a, **k: _None())
    assert rv.review_target(tmp_path, use_cloud=False) is None


def test_openrouter_model_ids_survive_the_provider_split(tmp_path):
    """OpenRouter model ids contain a slash — `anthropic/claude-3.5-sonnet` — so a
    naive `provider/model` split would route to provider "openrouter" and model
    "anthropic", silently using the wrong model."""
    from tawn.model.router import split_preference

    target = "openrouter/anthropic/claude-3.5-sonnet"
    assert rv.review_target(tmp_path, use_cloud=False, model=target) == target
    assert split_preference(target) == ("openrouter", "anthropic/claude-3.5-sonnet")


def test_a_bare_provider_still_routes_to_its_default(tmp_path):
    from tawn.model.router import split_preference

    assert split_preference("openrouter") == ("openrouter", None)
