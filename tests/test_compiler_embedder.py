import pytest
from pathlib import Path
from unittest.mock import patch
from tawn.compiler.embedder import embed_text, EmbedError, NO_EMBED_WARNING, get_embed_config


@pytest.fixture()
def home(tmp_path):
    h = tmp_path / "tawn"
    h.mkdir()
    return h


def test_no_embed_model_raises(home):
    with patch("tawn.compiler.embedder._ollama_embed_model", side_effect=EmbedError("no ollama")):
        with patch("tawn.compiler.embedder._openai_embed", side_effect=EmbedError("no openai")):
            with patch("tawn.compiler.embedder._gemini_embed", side_effect=EmbedError("no gemini")):
                with pytest.raises(EmbedError):
                    embed_text("hello", home)
    assert "No embedding model available" in NO_EMBED_WARNING


def test_embed_uses_ollama_when_available(home):
    fake_vec = [0.1] * 1024
    with patch("tawn.compiler.embedder._ollama_embed_model", return_value=fake_vec):
        result = embed_text("hello world", home)
    assert result == fake_vec
    assert len(result) == 1024


def test_embed_locks_dims_in_config(home):
    fake_vec = [0.1] * 1024
    with patch("tawn.compiler.embedder._ollama_embed_model", return_value=fake_vec):
        embed_text("hello", home)
    model, dims = get_embed_config(home)
    assert model == "nomic-embed-text"  # first in priority list
    assert dims == 1024


def test_embed_dim_mismatch_reconciles_config(home):
    """Superseded contract: a width mismatch used to raise "run rebuild".

    That guard existed because the storage column had a fixed width, so a
    differently-sized vector could not be inserted. The column is
    dimensionless now, and each row records its own width, so a mismatch
    means config drifted — reconcile it and carry on. Recall filters by
    width, so older rows are simply not compared until re-embedded.
    """
    (home / "config.yaml").write_text("embed_model: nomic-embed-text\nembed_dims: 1024\n")
    wrong_vec = [0.1] * 768
    with patch("tawn.compiler.embedder._ollama_embed_model", return_value=wrong_vec):
        vec = embed_text("hello", home)

    assert len(vec) == 768
    _, dims = get_embed_config(home)
    assert dims == 768


def test_embed_falls_back_to_openai_when_ollama_absent(home):
    """Cloud fallback still works — but only once explicitly permitted."""
    (home / "config.yaml").write_text("embed_allow_cloud: true\n")
    fake_vec = [0.1] * 1536
    with patch("tawn.compiler.embedder._ollama_embed_model", side_effect=EmbedError("no ollama")):
        with patch("tawn.compiler.embedder._openai_embed", return_value=fake_vec):
            result = embed_text("hello", home)
    assert len(result) == 1536
    _, dims = get_embed_config(home)
    assert dims == 1536


def test_locked_model_used_on_second_call(home):
    fake_vec = [0.1] * 1024
    with patch("tawn.compiler.embedder._ollama_embed_model", return_value=fake_vec):
        embed_text("first", home)
    # Second call: nomic-embed-text locked — _ollama_embed_model called with that model
    with patch("tawn.compiler.embedder._ollama_embed_model", return_value=fake_vec) as mock:
        embed_text("second", home)
        mock.assert_called_once()


def test_embed_falls_back_to_next_ollama_model(home):
    """If nomic-embed-text missing, tries mxbai-embed-large next."""
    fake_vec = [0.1] * 1024

    def side_effect(text, model):
        if model == "nomic-embed-text":
            raise EmbedError("not installed")
        return fake_vec

    with patch("tawn.compiler.embedder._ollama_embed_model", side_effect=side_effect):
        result = embed_text("hello", home)
    assert len(result) == 1024
    model, _ = get_embed_config(home)
    assert model == "mxbai-embed-large"


# ── Stage 7: embedder provenance ──────────────────────────────────────────────

def test_embed_text_with_meta_reports_model_and_dims(tmp_path, monkeypatch):
    """Callers persist which embedder made each vector, so recall knows what is comparable."""
    import tawn.compiler.embedder as emb

    monkeypatch.setattr(emb, "_chain", lambda home=None: [("fake-model", 4, lambda t: [0.1, 0.2, 0.3, 0.4])])
    vec, model, dims = emb.embed_text_with_meta("hello", tmp_path)

    assert vec == [0.1, 0.2, 0.3, 0.4]
    assert model == "fake-model"
    assert dims == 4


def test_embed_text_still_returns_bare_vector(tmp_path, monkeypatch):
    import tawn.compiler.embedder as emb

    monkeypatch.setattr(emb, "_chain", lambda home=None: [("fake-model", 3, lambda t: [1.0, 2.0, 3.0])])
    assert emb.embed_text("hello", tmp_path) == [1.0, 2.0, 3.0]


def test_stale_config_dims_are_corrected_not_fatal(tmp_path, monkeypatch):
    """The column is dimensionless now, so a stale width updates config rather than raising."""
    import yaml

    import tawn.compiler.embedder as emb

    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump({"embed_model": "fake-model", "embed_dims": 999})
    )
    monkeypatch.setattr(emb, "_chain", lambda home=None: [("fake-model", 999, lambda t: [0.5, 0.5])])

    vec, model, dims = emb.embed_text_with_meta("hello", tmp_path)

    assert dims == 2
    cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert cfg["embed_dims"] == 2


# ── Stage 7: batch embedding ──────────────────────────────────────────────────

def test_embed_texts_batches_and_preserves_order(tmp_path, monkeypatch):
    import tawn.compiler.embedder as emb

    seen: list[list[str]] = []

    def fake_batch(texts):
        seen.append(list(texts))
        return [[float(len(t))] * 3 for t in texts]

    monkeypatch.setattr(emb, "_chain", lambda home=None: [("fake-model", 3, lambda t: [float(len(t))] * 3)])
    monkeypatch.setattr(emb, "_batch_fn_for", lambda name: fake_batch)

    texts = ["a", "bb", "ccc", "dddd"]
    vecs, model, dims = emb.embed_texts(texts, tmp_path, batch_size=2)

    assert model == "fake-model"
    assert dims == 3
    assert [v[0] for v in vecs] == [1.0, 2.0, 3.0, 4.0]  # order preserved
    # First text goes through the single-call path to establish the model.
    assert seen == [["bb", "ccc"], ["dddd"]]


def test_embed_texts_falls_back_when_batch_fails(tmp_path, monkeypatch):
    """A provider hiccup should cost throughput, not correctness."""
    import tawn.compiler.embedder as emb

    def broken_batch(texts):
        raise emb.EmbedError("batch endpoint down")

    monkeypatch.setattr(emb, "_chain", lambda home=None: [("fake-model", 3, lambda t: [float(len(t))] * 3)])
    monkeypatch.setattr(emb, "_batch_fn_for", lambda name: broken_batch)

    vecs, _, _ = emb.embed_texts(["a", "bb", "ccc"], tmp_path, batch_size=2)
    assert [v[0] for v in vecs] == [1.0, 2.0, 3.0]


def test_embed_texts_empty_input(tmp_path):
    import tawn.compiler.embedder as emb

    assert emb.embed_texts([], tmp_path) == ([], "", 0)


# ── Stage 7 follow-up: cloud embedding is opt-in ──────────────────────────────

def test_cloud_providers_absent_from_chain_by_default(home):
    """Embedding sends the whole corpus, so a drifted config must not leak it."""
    import tawn.compiler.embedder as emb

    names = [n for n, _, _ in emb._chain(home)]
    assert emb._OPENAI_MODEL not in names
    assert emb._GEMINI_MODEL not in names
    assert "nomic-embed-text" in names


def test_cloud_providers_present_when_opted_in_via_config(home):
    import tawn.compiler.embedder as emb

    (home / "config.yaml").write_text("embed_allow_cloud: true\n")
    names = [n for n, _, _ in emb._chain(home)]
    assert emb._OPENAI_MODEL in names


def test_cloud_providers_present_when_opted_in_via_env(home, monkeypatch):
    import tawn.compiler.embedder as emb

    monkeypatch.setenv("TAWN_EMBED_ALLOW_CLOUD", "1")
    names = [n for n, _, _ in emb._chain(home)]
    assert emb._OPENAI_MODEL in names


def test_no_local_model_and_no_cloud_opt_in_raises(home):
    """Failing loudly beats silently reaching for a paid remote provider."""
    import tawn.compiler.embedder as emb

    with patch.object(emb, "_ollama_embed_model", side_effect=EmbedError("no ollama")):
        with pytest.raises(EmbedError):
            embed_text("hello", home)


def test_empty_text_does_not_poison_a_batch(tmp_path, monkeypatch):
    """One blank chunk must not fail the whole batch.

    Gemini rejects an entire request with `content contains an empty Part`,
    so a single blank row out of thousands aborted an 8,586-chunk run.
    """
    import tawn.compiler.embedder as emb

    seen: list[list[str]] = []

    def fake_batch(texts):
        seen.append(list(texts))
        assert all(t.strip() for t in texts), "provider received an empty part"
        return [[float(len(t))] * 3 for t in texts]

    monkeypatch.setattr(emb, "_chain", lambda home=None: [("fake-model", 3, lambda t: [float(len(t))] * 3)])
    monkeypatch.setattr(emb, "_batch_fn_for", lambda name: fake_batch)

    vecs, _, _ = emb.embed_texts(["real text", "", "   ", "more text"], tmp_path, batch_size=8)
    assert len(vecs) == 4  # one vector per input, order preserved


# ── Stage 8: embed calls reach the ledger ─────────────────────────────────────

def test_embed_texts_records_one_entry_per_text(tmp_path, monkeypatch):
    """Embeddings were invisible: ~12k calls per rebuild, none recorded."""
    import tawn.compiler.embedder as emb
    from tawn.model.ledger import Ledger

    monkeypatch.setattr(emb, "_chain", lambda home=None: [("nomic-embed-text", 3, lambda t: [1.0, 2.0, 3.0])])
    monkeypatch.setattr(emb, "_batch_fn_for", lambda name: (lambda texts: [[1.0, 2.0, 3.0] for _ in texts]))

    emb.embed_texts(["alpha", "beta", "gamma"], tmp_path, batch_size=2)

    entries = Ledger(tmp_path / "ledger.jsonl").entries()
    assert len(entries) == 3
    assert all(e["operation"] == "embed" for e in entries)


def test_local_embeds_are_free_but_counted(tmp_path, monkeypatch):
    """Call volume is what explains a slow compile, so free still gets logged."""
    import tawn.compiler.embedder as emb
    from tawn.model.ledger import Ledger

    monkeypatch.setattr(emb, "_chain", lambda home=None: [("nomic-embed-text", 3, lambda t: [1.0, 2.0, 3.0])])
    monkeypatch.setattr(emb, "_batch_fn_for", lambda name: None)

    emb.embed_texts(["alpha"], tmp_path)
    e = Ledger(tmp_path / "ledger.jsonl").entries()[-1]
    assert float(e["cost_usd"]) == 0
    assert e["priced"] is True      # genuinely free, not unknown
    assert e["locality"] == "local"


def test_texts_in_one_batch_share_a_batch_id(tmp_path, monkeypatch):
    """The batch is what took the time; the text is what carries the cost."""
    import tawn.compiler.embedder as emb
    from tawn.model.ledger import Ledger

    monkeypatch.setattr(emb, "_chain", lambda home=None: [("nomic-embed-text", 3, lambda t: [1.0, 2.0, 3.0])])
    monkeypatch.setattr(emb, "_batch_fn_for", lambda name: (lambda texts: [[1.0, 2.0, 3.0] for _ in texts]))

    emb.embed_texts(["a", "b", "c", "d", "e"], tmp_path, batch_size=4)
    entries = Ledger(tmp_path / "ledger.jsonl").entries()
    batch_ids = [e["batch_id"] for e in entries]
    assert len(set(batch_ids)) >= 2          # more than one round trip
    assert all(b for b in batch_ids)         # every entry names its batch


def test_ledger_failure_never_breaks_embedding(tmp_path, monkeypatch):
    """Observability must not break the thing it observes."""
    import tawn.compiler.embedder as emb

    monkeypatch.setattr(emb, "_chain", lambda home=None: [("nomic-embed-text", 3, lambda t: [1.0, 2.0, 3.0])])
    monkeypatch.setattr(emb, "_batch_fn_for", lambda name: None)
    monkeypatch.setattr(emb, "_record_embed", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))

    vecs, model, dims = emb.embed_texts(["alpha"], tmp_path)
    assert vecs == [[1.0, 2.0, 3.0]]
