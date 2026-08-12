"""A corrupt history file must cost less than the whole history.

Regression cover for a live 500: an attachment defect wrote ~760 KB of binary
into one session's JSONL, and every `/api/history` request then died with a
`JSONDecodeError` — one bad file taking down a page that had nothing to do with
it.
"""

import json

from tawn.history import MAX_LINE_BYTES, Session, get_session, list_sessions, read_entries


def _write(home, name, lines):
    d = home / "history"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _turn(role, content, ts="2026-07-27T12:00:00+00:00"):
    return json.dumps({"ts": ts, "role": role, "content": content, "model": "m"})


def test_good_lines_survive_a_corrupt_neighbour(tmp_path):
    _write(tmp_path, "s1", [_turn("user", "real question"), "{not json at all", _turn("assistant", "answer")])
    entries, skipped = read_entries(tmp_path / "history" / "s1.jsonl")
    assert [e["role"] for e in entries] == ["user", "assistant"]
    assert skipped == 1


def test_binary_garbage_does_not_raise(tmp_path):
    """The observed failure: raw bytes on a line where a turn should be."""
    _write(tmp_path, "s1", ["\x00\x1e\xff garbage \x7f", _turn("user", "still here")])
    entries, skipped = read_entries(tmp_path / "history" / "s1.jsonl")
    assert len(entries) == 1
    assert skipped == 1


def test_absurdly_long_line_is_skipped_without_parsing(tmp_path):
    _write(tmp_path, "s1", ["x" * (MAX_LINE_BYTES + 1), _turn("user", "ok")])
    entries, skipped = read_entries(tmp_path / "history" / "s1.jsonl")
    assert len(entries) == 1
    assert skipped == 1


def test_json_that_is_not_an_object_is_skipped(tmp_path):
    _write(tmp_path, "s1", ["[1, 2, 3]", '"a string"', _turn("user", "ok")])
    entries, skipped = read_entries(tmp_path / "history" / "s1.jsonl")
    assert len(entries) == 1
    assert skipped == 2


def test_list_sessions_reports_corruption_instead_of_failing(tmp_path):
    _write(tmp_path, "20260101-000000-aaaaaaaa", [_turn("user", "hello there"), "broken{"])
    rows = list_sessions(tmp_path)
    assert len(rows) == 1
    assert rows[0]["title"] == "hello there"
    assert rows[0]["turns"] == 1
    assert rows[0]["corrupt_lines"] == 1


def test_a_wholly_unreadable_session_is_flagged_not_hidden(tmp_path):
    """Dropping it would make lost history indistinguishable from history that
    never existed."""
    _write(tmp_path, "20260101-000000-bbbbbbbb", ["\xff\xfe not json", "also not json"])
    rows = list_sessions(tmp_path)
    assert len(rows) == 1
    assert rows[0]["corrupt_lines"] == 2
    assert rows[0]["turns"] == 0
    assert "unreadable" in rows[0]["title"]


def test_empty_session_file_is_omitted(tmp_path):
    _write(tmp_path, "20260101-000000-cccccccc", [])
    assert list_sessions(tmp_path) == []


def test_get_session_recovers_what_it_can(tmp_path):
    _write(tmp_path, "s1", ["junk", _turn("user", "q"), "more junk", _turn("assistant", "a")])
    assert [e["role"] for e in get_session(tmp_path, "s1")] == ["user", "assistant"]


def test_missing_session_is_empty_not_an_error(tmp_path):
    assert get_session(tmp_path, "nope") == []


def test_session_entries_uses_the_same_tolerant_read(tmp_path):
    s = Session(tmp_path, "s1")
    s.append("user", "one")
    with (tmp_path / "history" / "s1.jsonl").open("a", encoding="utf-8") as f:
        f.write("corrupt line\n")
    s.append("assistant", "two")
    assert [e["role"] for e in s.entries()] == ["user", "assistant"]
