"""The tool creator: static verification, and the disabled-by-default rule."""

import pytest
import yaml

from tawn.capability.grants import Grants
from tawn.tools.creator import (
    MANIFEST, CapabilityMismatch, ToolGenerationError, generate_tool,
    inspect_source, list_tools, read_manifest, read_source, remove_tool,
    set_enabled, tool_dir, write_tool,
)
from tawn.tools.loader import load_tools

SAFE = "def run(x: str) -> str:\n    return x.upper()\n"


class FakeRouter:
    def __init__(self, text):
        self.text = text

    def complete(self, msgs, sensitive=True):
        class R:
            pass

        r = R()
        r.text = self.text
        return r


def _payload(**kw):
    import json

    base = {
        "name": "shout",
        "description": "Uppercase a string.",
        "parameters": {"type": "object", "properties": {"x": {"type": "string"}},
                       "required": ["x"]},
        "capabilities": [],
        "impl": SAFE,
        "test": "def test_run():\n    assert True\n",
    }
    base.update(kw)
    return json.dumps(base)


# ── static analysis ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("src,expected", [
    ("import subprocess\ndef run(): subprocess.run(['ls'])", {"shell"}),
    ("import os\ndef run(): os.system('ls')", {"shell"}),
    ("import httpx\ndef run(): httpx.get('http://x')", {"net"}),
    ("import requests\ndef run(): requests.post('http://x')", {"net"}),
    ("from urllib.request import urlopen\ndef run(): urlopen('http://x')", {"net"}),
    ("def run(p): open(p, 'w').write('x')", {"write"}),
    ("def run(p): open(p, 'a').write('x')", {"write"}),
    ("def run(p): return open(p).read()", {"read"}),
    ("def run(p): return open(p, mode='w')", {"write"}),
    ("def run(): return 2 + 2", set()),
])
def test_inspect_source_detects_capabilities(src, expected):
    assert inspect_source(src) == expected


def test_indirect_execution_is_caught():
    assert "shell" in inspect_source("def run(s): eval(s)")
    assert "shell" in inspect_source("def run(s): exec(s)")


def test_pathlib_writes_are_caught():
    src = "from pathlib import Path\ndef run(p): Path(p).write_text('x')"
    assert "write" in inspect_source(src)


def test_unparseable_source_is_an_error():
    with pytest.raises(ToolGenerationError, match="does not parse"):
        inspect_source("def run(:\n  broken")


# ── the verification gate ────────────────────────────────────────────────────

def test_a_manifest_that_under_declares_is_rejected(tmp_path):
    """A model's account of what its own code does is not evidence."""
    with pytest.raises(CapabilityMismatch) as exc:
        write_tool(
            tmp_path, "sneaky",
            {"name": "sneaky", "capabilities": []},
            "import subprocess\ndef run(): subprocess.run(['ls'])",
        )
    assert "shell" in str(exc.value)
    assert not tool_dir(tmp_path, "sneaky").exists()


def test_over_declaring_is_allowed(tmp_path):
    """Claiming more than you need is the safe direction."""
    write_tool(tmp_path, "cautious",
               {"name": "cautious", "capabilities": ["read", "net", "shell"]}, SAFE)
    assert read_manifest(tmp_path, "cautious")["capabilities"] == ["read", "net", "shell"]


def test_declaring_exactly_what_is_used_passes(tmp_path):
    src = "import httpx\ndef run(u): return httpx.get(u).text"
    write_tool(tmp_path, "fetch", {"name": "fetch", "capabilities": ["net"]}, src)
    assert read_source(tmp_path, "fetch") == src


# ── disabled on creation ─────────────────────────────────────────────────────

def test_a_generated_tool_is_written_disabled(tmp_path):
    write_tool(tmp_path, "shout", {"name": "shout", "capabilities": []}, SAFE)
    raw = yaml.safe_load((tool_dir(tmp_path, "shout") / MANIFEST).read_text())
    assert raw["enabled"] is False


def test_an_enabled_flag_from_the_generator_is_ignored(tmp_path):
    """A generator must not be able to enable its own output."""
    write_tool(tmp_path, "shout",
               {"name": "shout", "capabilities": [], "enabled": True}, SAFE)
    assert read_manifest(tmp_path, "shout")["enabled"] is False


def test_a_disabled_tool_is_not_loaded(tmp_path):
    write_tool(tmp_path, "shout", {"name": "shout", "capabilities": []}, SAFE)
    assert load_tools(tmp_path, Grants()) == []


def test_enabling_makes_it_loadable(tmp_path):
    write_tool(tmp_path, "shout", {"name": "shout", "capabilities": []}, SAFE)
    assert set_enabled(tmp_path, "shout", True) is True
    loaded = load_tools(tmp_path, Grants())
    assert [s.name for s, _ in loaded] == ["shout"]
    spec, run = loaded[0]
    assert run(x="hi") == "HI"
    assert spec.source == "local:shout"


def test_enabling_an_absent_tool_reports_it(tmp_path):
    assert set_enabled(tmp_path, "ghost", True) is False


# ── the grant gate, on top of enabling ───────────────────────────────────────

def test_an_enabled_tool_needing_an_ungranted_capability_is_not_loaded(tmp_path):
    src = "import httpx\ndef run(u): return httpx.get(u).text"
    write_tool(tmp_path, "fetch", {"name": "fetch", "capabilities": ["net"]}, src)
    set_enabled(tmp_path, "fetch", True)
    assert load_tools(tmp_path, Grants(net=False)) == []
    assert len(load_tools(tmp_path, Grants(net=True))) == 1


def test_both_gates_are_required(tmp_path):
    src = "import httpx\ndef run(u): return httpx.get(u).text"
    write_tool(tmp_path, "fetch", {"name": "fetch", "capabilities": ["net"]}, src)
    # granted but not enabled
    assert load_tools(tmp_path, Grants(net=True)) == []
    set_enabled(tmp_path, "fetch", True)
    # enabled but not granted
    assert load_tools(tmp_path, Grants(net=False)) == []


def test_a_tool_that_fails_to_import_is_skipped_not_crashed(tmp_path):
    d = tool_dir(tmp_path, "broken")
    d.mkdir(parents=True)
    (d / MANIFEST).write_text(
        yaml.safe_dump({"name": "broken", "capabilities": [], "enabled": True})
    )
    (d / "impl.py").write_text("raise RuntimeError('boom at import')\n")
    assert load_tools(tmp_path, Grants()) == []


# ── generation ───────────────────────────────────────────────────────────────

def test_generation_parses_the_model_payload():
    manifest, impl, test = generate_tool("uppercase a string", FakeRouter(_payload()))
    assert manifest["name"] == "shout"
    assert manifest["enabled"] is False
    assert "def run" in impl
    assert test


def test_generation_tolerates_fences_and_prose():
    router = FakeRouter(f"Sure!\n```json\n{_payload()}\n```\nHope that helps.")
    manifest, _, _ = generate_tool("x", router)
    assert manifest["name"] == "shout"


def test_generation_rejects_output_with_no_run_function():
    with pytest.raises(ToolGenerationError, match="run"):
        generate_tool("x", FakeRouter(_payload(impl="x = 1\n")))


def test_generation_rejects_non_json():
    with pytest.raises(ToolGenerationError):
        generate_tool("x", FakeRouter("I would rather not."))


def test_generation_drops_unknown_capabilities():
    router = FakeRouter(_payload(capabilities=["read", "telepathy"]))
    manifest, _, _ = generate_tool("x", router)
    assert manifest["capabilities"] == ["read"]


# ── listing and removal ──────────────────────────────────────────────────────

def test_listing_and_removal(tmp_path):
    write_tool(tmp_path, "a", {"name": "a", "capabilities": []}, SAFE)
    write_tool(tmp_path, "b", {"name": "b", "capabilities": []}, SAFE)
    assert {m["name"] for m in list_tools(tmp_path)} == {"a", "b"}
    assert remove_tool(tmp_path, "a") is True
    assert remove_tool(tmp_path, "a") is False
    assert [m["name"] for m in list_tools(tmp_path)] == ["b"]


def test_an_empty_store_lists_nothing(tmp_path):
    assert list_tools(tmp_path) == []
    assert read_manifest(tmp_path, "ghost") is None
    assert read_source(tmp_path, "ghost") is None


def test_the_generated_test_runs(tmp_path):
    from tawn.tools.loader import run_tool_test

    write_tool(
        tmp_path, "shout", {"name": "shout", "capabilities": []}, SAFE,
        test="def test_smoke():\n    assert 1 + 1 == 2\n",
    )
    ok, output = run_tool_test(tmp_path, "shout")
    assert ok is True, output


def test_a_tool_with_no_test_says_so(tmp_path):
    from tawn.tools.loader import run_tool_test

    write_tool(tmp_path, "shout", {"name": "shout", "capabilities": []}, SAFE)
    ok, msg = run_tool_test(tmp_path, "shout")
    assert ok is False
    assert "no generated test" in msg


# ── parsing a model's reply, in whatever shape it arrives ────────────────────

SECTIONED = '''NAME: shout
DESCRIPTION: Uppercase a string.
CAPABILITIES: none
PARAMETERS:
```json
{"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
```
IMPL:
```python
def run(x: str) -> str:
    return x.upper()
```
TEST:
```python
def test_run():
    assert run("a") == "A"
```'''


class ScriptedRouter:
    """Returns each queued reply in turn, recording the prompts it saw."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def complete(self, msgs, sensitive=True):
        self.prompts.append(msgs[0].content)

        class R:
            pass

        r = R()
        r.text = self.replies.pop(0) if self.replies else "unparseable"
        return r


def test_the_sectioned_format_parses():
    from tawn.tools.creator import parse_sections

    data = parse_sections(SECTIONED)
    assert data["name"] == "shout"
    assert data["description"] == "Uppercase a string."
    assert data["capabilities"] == []
    assert data["parameters"]["required"] == ["x"]
    assert "def run" in data["impl"]
    assert "def test_run" in data["test"]


def test_sectioned_python_needs_no_escaping():
    """The reason the format exists: source with quotes and newlines survives
    verbatim, where a JSON string would need every one escaped."""
    from tawn.tools.creator import parse_sections

    tricky = '''NAME: q
DESCRIPTION: d
CAPABILITIES: none
IMPL:
```python
def run(p: str) -> str:
    msg = "it's \\"quoted\\" and multi-line"
    return f"{msg}\\n{p}"
```'''
    impl = parse_sections(tricky)["impl"]
    assert 'it\'s \\"quoted\\"' in impl
    assert impl.count("\n") >= 2


def test_capabilities_parse_from_a_comma_list():
    from tawn.tools.creator import parse_sections

    text = SECTIONED.replace("CAPABILITIES: none", "CAPABILITIES: read, net")
    assert parse_sections(text)["capabilities"] == ["read", "net"]


def test_prose_around_the_sections_is_tolerated():
    from tawn.tools.creator import parse_sections

    assert parse_sections("Sure!\n\n" + SECTIONED + "\n\nHope that helps.")["name"] == "shout"


def test_sections_without_a_name_or_impl_are_not_a_tool():
    from tawn.tools.creator import parse_sections

    assert parse_sections("DESCRIPTION: only this") == {}
    assert parse_sections("just prose") == {}


# ── the JSON failure the user actually hit ───────────────────────────────────

def test_unquoted_keys_are_repaired():
    """The exact reply that failed: 'Expecting property name enclosed in
    double quotes: line 2 column 5'."""
    from tawn.tools.creator import parse_reply

    reply = """{
    name: "shout",
    'description': 'Uppercase.',
    "capabilities": [],
    "impl": "def run(x):\\n    return x.upper()\\n",
}"""
    data = parse_reply(reply)
    assert data["name"] == "shout"
    assert data["description"] == "Uppercase."
    assert "def run" in data["impl"]


@pytest.mark.parametrize("raw,key", [
    ('{name: "a", "impl": "def run(): pass"}', "name"),
    ("{'name': 'a', 'impl': 'def run(): pass'}", "name"),
    ('{"name": "a", "impl": "def run(): pass",}', "name"),
    ('{"name": "a", "enabled": True, "impl": "def run(): pass"}', "name"),
    ('// a comment\n{"name": "a", "impl": "def run(): pass"}', "name"),
])
def test_near_json_variants_are_repaired(raw, key):
    from tawn.tools.creator import parse_reply

    assert parse_reply(raw)[key] == "a"


def test_trailing_prose_is_not_swallowed_into_the_payload():
    """A greedy brace regex would run to the last `}` anywhere in the reply."""
    from tawn.tools.creator import parse_reply

    reply = '{"name": "a", "impl": "def run(): pass"}\n\nLet me know if {this} helps!'
    assert parse_reply(reply)["name"] == "a"


def test_a_genuinely_unparseable_reply_still_errors():
    from tawn.tools.creator import parse_reply

    with pytest.raises(ToolGenerationError):
        parse_reply("I would rather not write that.")


# ── retry ────────────────────────────────────────────────────────────────────

def test_an_unparseable_reply_is_retried_with_the_error():
    router = ScriptedRouter("total nonsense", SECTIONED)
    manifest, impl, _ = generate_tool("uppercase", router)
    assert manifest["name"] == "shout"
    assert len(router.prompts) == 2
    # The second prompt must tell the model what went wrong.
    assert "could not be parsed" in router.prompts[1]


def test_retries_are_bounded():
    router = ScriptedRouter("nonsense", "still nonsense", "and again")
    with pytest.raises(ToolGenerationError):
        generate_tool("x", router, retries=1)
    assert len(router.prompts) == 2


def test_a_good_first_reply_is_not_retried():
    router = ScriptedRouter(SECTIONED)
    generate_tool("uppercase", router)
    assert len(router.prompts) == 1


# ── validation ───────────────────────────────────────────────────────────────

def test_generated_code_that_does_not_parse_is_rejected_at_generation():
    """Better a clear generation failure than a mysterious import error later."""
    broken = SECTIONED.replace("    return x.upper()", "    return x.upper(")
    with pytest.raises(ToolGenerationError, match="does not parse"):
        generate_tool("x", ScriptedRouter(broken), retries=0)


def test_a_name_with_spaces_or_punctuation_is_normalised():
    text = SECTIONED.replace("NAME: shout", "NAME: Shout It Loudly!")
    manifest, _, _ = generate_tool("x", ScriptedRouter(text))
    assert manifest["name"] == "shout_it_loudly"


def test_the_sectioned_prompt_is_what_the_model_is_asked_for():
    router = ScriptedRouter(SECTIONED)
    generate_tool("uppercase a string", router)
    prompt = router.prompts[0]
    for heading in ("NAME:", "DESCRIPTION:", "CAPABILITIES:", "IMPL:", "TEST:"):
        assert heading in prompt
    assert "uppercase a string" in prompt


# ── a model too small for the job ────────────────────────────────────────────

ECHOED = '''NAME: snake_case_name
DESCRIPTION: one sentence
CAPABILITIES: none
IMPL:
```python
def run(arg: str) -> str:
    return "result"
```'''


def test_the_placeholder_name_is_rejected():
    """A weak model echoes the template. It parses perfectly and does nothing,
    which looks like success — the worst failure mode there is."""
    with pytest.raises(ToolGenerationError, match="placeholder name"):
        generate_tool("count words", ScriptedRouter(ECHOED), retries=0)


def test_the_example_body_echoed_back_is_rejected():
    text = ECHOED.replace("NAME: snake_case_name", "NAME: word_counter")
    with pytest.raises(ToolGenerationError, match="verbatim"):
        generate_tool("count words", ScriptedRouter(text), retries=0)


def test_a_real_body_that_happens_to_return_result_is_allowed():
    """The check must not reject genuine code that uses the word."""
    text = '''NAME: word_counter
DESCRIPTION: Count words.
CAPABILITIES: none
IMPL:
```python
def run(text: str) -> str:
    words = text.split()
    result = len(words)
    if result == 0:
        return "no words"
    return "result: " + str(result)
```'''
    manifest, impl, _ = generate_tool("count words", ScriptedRouter(text), retries=0)
    assert manifest["name"] == "word_counter"
    assert "text.split()" in impl


def test_the_first_error_is_reported_not_the_last():
    """A retry often drifts further from the format; the first failure is the
    diagnostic one."""
    router = ScriptedRouter(ECHOED, "complete gibberish with no structure")
    with pytest.raises(ToolGenerationError) as exc:
        generate_tool("count words", router, retries=1)
    assert "placeholder name" in str(exc.value)


def test_a_local_failure_points_at_the_cloud_option():
    router = ScriptedRouter("nonsense", "nonsense")
    with pytest.raises(ToolGenerationError) as exc:
        generate_tool("x", router, allow_cloud=False, retries=1)
    assert "--cloud" in str(exc.value)


def test_a_cloud_failure_does_not_suggest_the_cloud():
    router = ScriptedRouter("nonsense", "nonsense")
    with pytest.raises(ToolGenerationError) as exc:
        generate_tool("x", router, allow_cloud=True, retries=1)
    assert "--cloud" not in str(exc.value)
