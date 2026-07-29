import pytest

from tawn.artifacts import artifact_dir, read_artifact
from tawn.model.diagrams import (
    FORMATS, DiagramError, _strip_fences, draft, generate_source, render,
    revise, save, validate,
)

MERMAID = "graph TD\n  A[Start] --> B[End]"
TIKZ = "\\begin{tikzpicture}\n\\node (a) {A};\n\\end{tikzpicture}"
DOT = "digraph G {\n  a -> b;\n}"
PUML = "@startuml\nAlice -> Bob: hi\n@enduml"


class FakeClient:
    def __init__(self, text):
        self.text = text
        self.prompts = []

    def complete(self, msgs, sensitive=True):
        self.prompts.append(msgs[0].content)

        class R:
            pass

        r = R()
        r.text = self.text
        return r


# ── validation ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("fmt,src", [
    ("mermaid", MERMAID), ("tikz", TIKZ), ("dot", DOT), ("plantuml", PUML),
])
def test_valid_sources_pass(fmt, src):
    validate(src, fmt)


def test_empty_source_is_rejected():
    with pytest.raises(DiagramError, match="empty"):
        validate("   ", "mermaid")


def test_wrong_format_content_is_rejected():
    with pytest.raises(DiagramError, match="does not look like"):
        validate(DOT, "plantuml")


def test_unbalanced_braces_are_rejected():
    with pytest.raises(DiagramError, match="unbalanced"):
        validate("digraph G {\n a -> b;", "dot")


def test_unknown_format_is_rejected():
    with pytest.raises(DiagramError, match="unknown format"):
        validate(MERMAID, "visio")


def test_fences_are_stripped():
    assert _strip_fences("```mermaid\ngraph TD\n  A-->B\n```") == "graph TD\n  A-->B"
    assert _strip_fences("graph TD") == "graph TD"


# ── generation ───────────────────────────────────────────────────────────────

def test_generation_strips_fences_the_model_added():
    client = FakeClient(f"```mermaid\n{MERMAID}\n```")
    assert generate_source("a flow", "mermaid", client) == MERMAID


def test_generation_rejects_invalid_output_rather_than_saving_it():
    with pytest.raises(DiagramError):
        generate_source("x", "dot", FakeClient("this is just prose"))


def test_tikz_prompt_forbids_a_preamble():
    client = FakeClient(TIKZ)
    generate_source("a node", "tikz", client)
    assert "No preamble" in client.prompts[0]
    assert "documentclass" in client.prompts[0]


def test_context_material_reaches_the_prompt():
    client = FakeClient(MERMAID)
    generate_source("x", "mermaid", client, context="finding: latency doubled")
    assert "latency doubled" in client.prompts[0]


# ── saving, versioning, revising ─────────────────────────────────────────────

def test_draft_saves_source_to_disk(tmp_path):
    d = draft(tmp_path, "my flow", "a flow", fmt="mermaid", client=FakeClient(MERMAID))
    assert d.is_new is True
    assert d.version == 1
    assert d.path.read_text() == MERMAID
    assert d.path.suffix == ".mmd"


def test_revising_creates_a_new_version_and_keeps_the_old(tmp_path):
    draft(tmp_path, "flow", "a flow", client=FakeClient(MERMAID))
    revised = "graph TD\n  A[Start] --> C[Changed]"
    d = revise(tmp_path, "flow", "rename the end node", client=FakeClient(revised))
    assert d.version == 2
    _, v1, old = read_artifact(tmp_path, "diagrams", "flow", version=1)
    assert old == MERMAID  # untouched
    assert read_artifact(tmp_path, "diagrams", "flow")[2] == revised


def test_the_revision_instruction_is_recorded_as_the_version_note(tmp_path):
    draft(tmp_path, "flow", "a flow", client=FakeClient(MERMAID))
    revise(tmp_path, "flow", "make it left-to-right",
           client=FakeClient("graph LR\n  A-->B"))
    art, _, _ = read_artifact(tmp_path, "diagrams", "flow")
    assert art.versions[1].note == "make it left-to-right"


def test_revising_an_absent_diagram_is_an_error(tmp_path):
    with pytest.raises(DiagramError, match="no diagram"):
        revise(tmp_path, "ghost", "x", client=FakeClient(MERMAID))


def test_an_invalid_revision_does_not_replace_the_good_version(tmp_path):
    draft(tmp_path, "flow", "a flow", client=FakeClient(MERMAID))
    with pytest.raises(DiagramError):
        revise(tmp_path, "flow", "break it", client=FakeClient("nonsense prose"))
    art, v, source = read_artifact(tmp_path, "diagrams", "flow")
    assert source == MERMAID
    assert len(art.versions) == 1


def test_redrafting_identical_content_does_not_add_a_version(tmp_path):
    draft(tmp_path, "flow", "a flow", client=FakeClient(MERMAID))
    d = draft(tmp_path, "flow", "a flow", client=FakeClient(MERMAID))
    assert d.is_new is False
    assert d.version == 1


@pytest.mark.parametrize("fmt,src,ext", [
    ("mermaid", MERMAID, ".mmd"), ("tikz", TIKZ, ".tex"),
    ("dot", DOT, ".dot"), ("plantuml", PUML, ".puml"),
])
def test_each_format_saves_with_its_own_extension(tmp_path, fmt, src, ext):
    d = save(tmp_path, f"d-{fmt}", src, fmt)
    assert d.path.suffix == ext
    assert d.path.exists()


def test_saving_invalid_source_writes_nothing(tmp_path):
    with pytest.raises(DiagramError):
        save(tmp_path, "bad", "prose", "dot")
    assert not artifact_dir(tmp_path, "diagrams", "bad").exists()


# ── rendering is optional, never destructive ─────────────────────────────────

def test_a_missing_renderer_reports_it_and_keeps_the_source(tmp_path, monkeypatch):
    draft(tmp_path, "flow", "a flow", client=FakeClient(MERMAID))
    monkeypatch.setattr("shutil.which", lambda name: None)
    ok, msg = render(tmp_path, "flow")
    assert ok is False
    assert "not installed" in msg
    assert read_artifact(tmp_path, "diagrams", "flow")[2] == MERMAID


def test_rendering_an_absent_diagram(tmp_path):
    ok, msg = render(tmp_path, "ghost")
    assert ok is False and "no diagram" in msg


def test_every_format_declares_a_use_and_an_extension():
    for fmt, meta in FORMATS.items():
        assert meta["ext"] and meta["use"] and meta["opens"]
