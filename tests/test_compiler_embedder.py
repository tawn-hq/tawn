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


def test_embed_dim_mismatch_raises(home):
    (home / "config.yaml").write_text("embed_model: nomic-embed-text\nembed_dims: 1024\n")
    wrong_vec = [0.1] * 768
    with patch("tawn.compiler.embedder._ollama_embed_model", return_value=wrong_vec):
        with pytest.raises(EmbedError, match="rebuild"):
            embed_text("hello", home)


def test_embed_falls_back_to_openai_when_ollama_absent(home):
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
