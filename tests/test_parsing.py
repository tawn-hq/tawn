"""Document parsing: every format, and every way a document can be hostile."""

import json
import zipfile

import pytest

from tawn.parsing import (
    ParseError, UnsafeDocument, detect_format, parse_file, supported_formats,
)
from tawn.parsing.harness import Limits, safe_xml, safe_zip

TINY = Limits(
    max_file_bytes=10_000,
    max_expanded_bytes=50_000,
    max_compression_ratio=10,
    max_archive_entries=5,
    max_text_chars=200,
)


# ── builders for real files of each format ───────────────────────────────────

def _docx(path, paragraphs):
    body = "".join(
        f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs
    )
    xml = (
        '<?xml version="1.0"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", xml)
        zf.writestr("[Content_Types].xml", "<Types/>")
    return path


def _xlsx(path, rows):
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    body = "".join(
        "<row>" + "".join(f"<c><v>{c}</v></c>" for c in row) + "</row>"
        for row in rows
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("xl/workbook.xml", f'<workbook xmlns="{ns}"/>')
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            f'<?xml version="1.0"?><worksheet xmlns="{ns}"><sheetData>{body}</sheetData></worksheet>',
        )
    return path


def _pptx(path, slides):
    ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("ppt/presentation.xml", "<presentation/>")
        for i, lines in enumerate(slides, 1):
            body = "".join(f'<a:t xmlns:a="{ns}">{line}</a:t>' for line in lines)
            zf.writestr(
                f"ppt/slides/slide{i}.xml",
                f'<?xml version="1.0"?><sld xmlns:a="{ns}">{body}</sld>',
            )
    return path


def _odt(path, paragraphs):
    ns = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    body = "".join(f"<text:p>{p}</text:p>" for p in paragraphs)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        zf.writestr(
            "content.xml",
            f'<?xml version="1.0"?><doc xmlns:text="{ns}">{body}</doc>',
        )
    return path


def _epub(path, chapters):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        for i, text in enumerate(chapters, 1):
            zf.writestr(f"ch{i}.xhtml", f"<html><body><p>{text}</p></body></html>")
    return path


# ── tier 0 formats all work with no dependencies ─────────────────────────────

def test_plain_text(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello world")
    doc = parse_file(f)
    assert doc.format == "text"
    assert doc.text == "hello world"
    assert doc.tier == 0


def test_markdown(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("# Title\n\nBody.")
    assert "# Title" in parse_file(f).text


def test_csv_becomes_readable_rows(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("name,role\nAda,engineer\nGrace,admiral\n")
    text = parse_file(f).text
    assert "name | role" in text
    assert "Ada | engineer" in text


def test_json_is_pretty_printed(tmp_path):
    f = tmp_path / "a.json"
    f.write_text('{"b":2,"a":1}')
    assert '"a": 1' in parse_file(f).text


def test_malformed_json_still_returns_its_text(tmp_path):
    f = tmp_path / "a.json"
    f.write_text('{"a": 1}\n{"a": 2}\n')  # JSONL
    assert '"a": 1' in parse_file(f).text


def test_html_markup_is_stripped(tmp_path):
    f = tmp_path / "a.html"
    f.write_text(
        "<html><head><style>p{color:red}</style></head>"
        "<body><script>evil()</script><p>Real content</p></body></html>"
    )
    text = parse_file(f).text
    assert "Real content" in text
    assert "evil()" not in text
    assert "color:red" not in text


def test_html_entities_are_decoded(tmp_path):
    f = tmp_path / "a.html"
    f.write_text("<p>caf&eacute; &amp; bar</p>")
    assert "café & bar" in parse_file(f).text


def test_docx(tmp_path):
    doc = parse_file(_docx(tmp_path / "a.docx", ["First para", "Second para"]))
    assert doc.format == "docx"
    assert doc.tier == 0  # stdlib only — no python-docx needed
    assert "First para" in doc.text
    assert "Second para" in doc.text


def test_xlsx(tmp_path):
    doc = parse_file(_xlsx(tmp_path / "a.xlsx", [["a", "b"], ["1", "2"]]))
    assert doc.format == "xlsx"
    assert "a | b" in doc.text
    assert "1 | 2" in doc.text


def test_pptx_marks_each_slide(tmp_path):
    doc = parse_file(_pptx(tmp_path / "a.pptx", [["Slide one"], ["Slide two"]]))
    assert doc.format == "pptx"
    assert "--- slide 1 ---" in doc.text
    assert "Slide two" in doc.text


def test_odt(tmp_path):
    doc = parse_file(_odt(tmp_path / "a.odt", ["Open document text"]))
    assert doc.format == "odt"
    assert "Open document text" in doc.text


def test_epub(tmp_path):
    doc = parse_file(_epub(tmp_path / "a.epub", ["Chapter one", "Chapter two"]))
    assert doc.format == "epub"
    assert "Chapter one" in doc.text
    assert "Chapter two" in doc.text


# ── detection trusts bytes over names ────────────────────────────────────────

def test_a_mislabelled_docx_is_still_parsed(tmp_path):
    """A file's name is a claim; its bytes are evidence."""
    f = _docx(tmp_path / "actually.txt", ["Real content"])
    assert detect_format(f) == "docx"
    assert "Real content" in parse_file(f).text


def test_an_extensionless_pdf_is_detected(tmp_path):
    f = tmp_path / "download"
    f.write_bytes(b"%PDF-1.4\nnot really a pdf")
    assert detect_format(f) == "pdf"


def test_extensionless_html_and_json(tmp_path):
    h = tmp_path / "page"
    h.write_bytes(b"<!DOCTYPE html><html><body>hi</body></html>")
    assert detect_format(h) == "html"
    j = tmp_path / "data"
    j.write_bytes(b'{"a": 1}')
    assert detect_format(j) == "json"


def test_source_code_is_treated_as_text(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("def hello():\n    return 1\n")
    assert parse_file(f).format == "text"
    assert "def hello()" in parse_file(f).text


# ── the harness ──────────────────────────────────────────────────────────────

def test_a_missing_file_is_a_clear_error(tmp_path):
    with pytest.raises(ParseError, match="no such file"):
        parse_file(tmp_path / "ghost.txt")


def test_an_empty_file_is_reported(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("")
    with pytest.raises(ParseError, match="empty file"):
        parse_file(f)


def test_an_oversized_file_is_refused(tmp_path):
    f = tmp_path / "big.txt"
    f.write_text("x" * 20_000)
    with pytest.raises(UnsafeDocument, match="over the"):
        parse_file(f, limits=TINY)


def test_a_symlink_is_refused(tmp_path):
    real = tmp_path / "real.txt"
    real.write_text("secret")
    link = tmp_path / "link.txt"
    link.symlink_to(real)
    with pytest.raises(UnsafeDocument, match="symlink"):
        parse_file(link)


def test_a_zip_bomb_is_refused(tmp_path):
    """Highly compressible content that expands far past its stored size."""
    f = tmp_path / "bomb.docx"
    with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", "0" * (5 * 1024 * 1024))
    with pytest.raises(UnsafeDocument, match="zip bomb"):
        parse_file(f)


def test_an_archive_with_too_many_entries_is_refused(tmp_path):
    f = tmp_path / "many.zip"
    with zipfile.ZipFile(f, "w") as zf:
        for i in range(20):
            zf.writestr(f"f{i}.txt", "x")
    with pytest.raises(UnsafeDocument, match="entries"):
        safe_zip(f, TINY)


def test_an_archive_entry_escaping_its_root_is_refused(tmp_path):
    f = tmp_path / "evil.zip"
    with zipfile.ZipFile(f, "w") as zf:
        zf.writestr("../../etc/passwd", "pwned")
    with pytest.raises(UnsafeDocument, match="escapes"):
        safe_zip(f)


def test_billion_laughs_is_refused():
    """Internal entity expansion, the classic XML memory bomb."""
    payload = b"""<?xml version="1.0"?>
    <!DOCTYPE lolz [
      <!ENTITY lol "lol">
      <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
    ]>
    <lolz>&lol2;</lolz>"""
    with pytest.raises((UnsafeDocument, ParseError)):
        safe_xml(payload)


def test_an_xxe_external_entity_does_not_read_a_file(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET")
    payload = f"""<?xml version="1.0"?>
    <!DOCTYPE d [<!ENTITY xxe SYSTEM "file://{secret}">]>
    <d>&xxe;</d>""".encode()
    try:
        root = safe_xml(payload)
    except (UnsafeDocument, ParseError):
        return  # refused outright, which is the preferred outcome
    assert "TOP SECRET" not in "".join(root.itertext())


def test_malformed_xml_is_a_parse_error():
    with pytest.raises(ParseError, match="malformed XML"):
        safe_xml(b"<unclosed>")


def test_a_corrupt_archive_is_a_clear_error(tmp_path):
    f = tmp_path / "a.docx"
    f.write_bytes(b"PK\x03\x04garbage that is not a zip")
    with pytest.raises(ParseError):
        parse_file(f, fmt="docx")


def test_a_zip_without_the_expected_part_says_so(tmp_path):
    f = tmp_path / "a.docx"
    with zipfile.ZipFile(f, "w") as zf:
        zf.writestr("other.xml", "<x/>")
    with pytest.raises(ParseError, match="not a Word document"):
        parse_file(f, fmt="docx")


def test_long_text_is_capped_and_says_so(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("y" * 5_000)
    doc = parse_file(f, limits=Limits(max_text_chars=200, max_file_bytes=10_000))
    assert doc.truncated is True
    assert "truncated" in doc.text


# ── degradation ──────────────────────────────────────────────────────────────

def test_a_pdf_without_a_library_names_what_to_install(tmp_path, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _no_pdf_libs(name, *args, **kwargs):
        if name in ("fitz", "pypdf", "pdfminer.high_level"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_pdf_libs)
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-1.4\ncontent")
    with pytest.raises(ParseError) as exc:
        parse_file(f)
    assert "pip install" in str(exc.value)


def test_an_unsupported_format_is_named(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(ParseError, match="unsupported format"):
        parse_file(f, fmt="hologram")


def test_a_document_with_no_extractable_text_warns_rather_than_lying(tmp_path):
    doc = parse_file(_docx(tmp_path / "blank.docx", [""]))
    assert doc.ok is False
    assert doc.warnings


# ── the cost ladder is honest ────────────────────────────────────────────────

def test_office_formats_are_tier_zero():
    """The point of the stdlib-first design: no dependency for the common case."""
    tiers = {f["format"]: f["tier"] for f in supported_formats()}
    for fmt in ("docx", "xlsx", "pptx", "odt", "epub", "csv", "html", "json"):
        assert tiers[fmt] == 0, fmt
    assert tiers["pdf"] == 1


def test_every_format_declares_its_cost():
    for row in supported_formats():
        assert row["cost"]
        assert row["label"]


# ── the OCR tier ─────────────────────────────────────────────────────────────

def test_images_are_detected_by_magic_bytes(tmp_path):
    f = tmp_path / "shot"          # no extension
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    assert detect_format(f) == "image"


def test_image_extensions_map_to_the_ocr_tier():
    tiers = {r["format"]: r for r in supported_formats()}
    assert tiers["image"]["tier"] == 2
    assert "OCR" in tiers["image"]["cost"] or "local" in tiers["image"]["cost"]


def test_ocr_availability_reports_what_is_missing():
    from tawn.parsing.ocr import ocr_available

    ok, hint = ocr_available()
    if not ok:
        # The message must tell the user how to fix it, not just that it failed.
        assert "install" in hint.lower()


def test_an_image_without_ocr_names_what_to_install(tmp_path, monkeypatch):
    from tawn.parsing import ocr as ocr_mod

    monkeypatch.setattr(ocr_mod, "ocr_available", lambda: (False, "pip install 'tawn[ocr]'"))
    f = tmp_path / "scan.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    with pytest.raises(ParseError) as exc:
        parse_file(f)
    assert "install" in str(exc.value)


def test_a_scanned_pdf_escalates_to_ocr(tmp_path, monkeypatch):
    """An empty text layer is the signature of a scan, so OCR is the next step."""
    import tawn.parsing as parsing_mod
    from tawn.parsing import extractors, ocr as ocr_mod

    monkeypatch.setattr(extractors, "extract_pdf", lambda p, limits: "")
    monkeypatch.setitem(parsing_mod.FORMATS, "pdf", (lambda p, limits: "", 1, "PDF"))
    monkeypatch.setattr(ocr_mod, "ocr_pdf", lambda p, limits: "text from the scan")

    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4\nfake")
    doc = parse_file(f)
    assert doc.tier == 2
    assert "text from the scan" in doc.text
    assert any("OCR" in w for w in doc.warnings)


def test_ocr_can_be_declined(tmp_path, monkeypatch):
    import tawn.parsing as parsing_mod

    monkeypatch.setitem(parsing_mod.FORMATS, "pdf", (lambda p, limits: "", 1, "PDF"))
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4\nfake")
    doc = parse_file(f, use_ocr=False)
    assert doc.ok is False
    assert any("use_ocr=True" in w for w in doc.warnings)


def test_the_model_tier_is_never_reached_automatically(tmp_path, monkeypatch):
    """Tier 3 costs money and leaves the machine, so it needs saying yes."""
    import tawn.parsing as parsing_mod
    from tawn.parsing import ocr as ocr_mod

    called = []
    monkeypatch.setattr(
        ocr_mod, "model_read",
        lambda *a, **k: called.append(1) or "model text",
    )
    monkeypatch.setitem(parsing_mod.FORMATS, "pdf", (lambda p, limits: "", 1, "PDF"))
    monkeypatch.setattr(ocr_mod, "ocr_pdf", lambda p, limits: "")

    f = tmp_path / "hard.pdf"
    f.write_bytes(b"%PDF-1.4\nfake")
    parse_file(f)
    assert called == []  # not without allow_model


def test_the_model_tier_runs_when_permitted(tmp_path, monkeypatch):
    import tawn.parsing as parsing_mod
    from tawn.parsing import ocr as ocr_mod

    monkeypatch.setattr(ocr_mod, "model_read", lambda *a, **k: "read by the model")
    monkeypatch.setitem(parsing_mod.FORMATS, "pdf", (lambda p, limits: "", 1, "PDF"))
    monkeypatch.setattr(ocr_mod, "ocr_pdf", lambda p, limits: "")

    f = tmp_path / "hard.pdf"
    f.write_bytes(b"%PDF-1.4\nfake")
    doc = parse_file(f, allow_model=True)
    assert doc.tier == 3
    assert "read by the model" in doc.text


class _VisionClient:
    """Records what it was sent and returns scripted transcriptions."""

    def __init__(self, *texts, fail_after=None):
        self.texts = list(texts)
        self.fail_after = fail_after
        self.seen = []

    def complete(self, msgs, sensitive=True):
        self.seen.append(msgs[0])
        if self.fail_after is not None and len(self.seen) > self.fail_after:
            raise RuntimeError("provider exploded")

        class R:
            pass

        r = R()
        r.text = self.texts.pop(0) if self.texts else "transcribed"
        return r


def test_model_read_transcribes_an_image(tmp_path):
    from tawn.parsing.ocr import model_read

    f = tmp_path / "note.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    client = _VisionClient("handwritten note text")
    assert model_read(f, TINY, client=client) == "handwritten note text"


def test_the_image_actually_reaches_the_model(tmp_path):
    """The point of tier 3 is that the model *sees* the page."""
    from tawn.parsing.ocr import model_read

    f = tmp_path / "note.png"
    payload = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    f.write_bytes(payload)
    client = _VisionClient("text")
    model_read(f, TINY, client=client)

    msg = client.seen[0]
    assert msg.images, "no image was attached to the request"
    import base64
    assert base64.b64decode(msg.images[0]["data"]) == payload
    assert msg.images[0]["media_type"] == "image/png"


def test_the_prompt_asks_for_transcription_not_summary(tmp_path):
    from tawn.parsing.ocr import model_read

    f = tmp_path / "note.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    client = _VisionClient("x")
    model_read(f, TINY, client=client)
    prompt = client.seen[0].content.lower()
    assert "transcribe" in prompt
    assert "do not summarise" in prompt


def test_model_read_refuses_formats_it_cannot_help_with(tmp_path):
    from tawn.parsing.ocr import model_read

    f = tmp_path / "a.txt"
    f.write_text("plain text")
    with pytest.raises(ParseError, match="cannot help"):
        model_read(f, TINY, client=_VisionClient())


def test_partial_pages_survive_a_mid_document_failure(tmp_path, monkeypatch):
    """Pages already read are still useful; the failure is reported, not hidden."""
    from tawn.parsing import ocr as ocr_mod

    monkeypatch.setattr(ocr_mod, "_render_pages", lambda p, fmt: [b"a", b"b", b"c"])
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4\nfake")
    client = _VisionClient("page one", "page two", fail_after=2)
    text = ocr_mod.model_read(f, TINY, client=client)
    assert "page one" in text
    assert "stopped at page 3" in text


def test_a_first_page_failure_is_an_error_not_a_silent_empty(tmp_path, monkeypatch):
    from tawn.parsing import ocr as ocr_mod

    monkeypatch.setattr(ocr_mod, "_render_pages", lambda p, fmt: [b"a"])
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4\nfake")
    with pytest.raises(ParseError, match="could not read"):
        ocr_mod.model_read(f, TINY, client=_VisionClient(fail_after=0))


def test_an_empty_model_response_is_reported(tmp_path, monkeypatch):
    from tawn.parsing import ocr as ocr_mod

    monkeypatch.setattr(ocr_mod, "_render_pages", lambda p, fmt: [b"a"])
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4\nfake")
    with pytest.raises(ParseError, match="no text"):
        ocr_mod.model_read(f, TINY, client=_VisionClient(""))


def test_model_pages_are_capped(tmp_path, monkeypatch):
    """Each page is a paid request, so the cap is far lower than OCR's."""
    from tawn.parsing import ocr as ocr_mod

    assert ocr_mod.MAX_MODEL_PAGES < ocr_mod.MAX_OCR_PAGES


def test_parse_file_reaches_the_model_tier_end_to_end(tmp_path, monkeypatch):
    import tawn.parsing as parsing_mod
    from tawn.parsing import ocr as ocr_mod

    monkeypatch.setitem(parsing_mod.FORMATS, "pdf", (lambda p, limits: "", 1, "PDF"))
    monkeypatch.setattr(ocr_mod, "ocr_pdf", lambda p, limits: "")
    monkeypatch.setattr(ocr_mod, "_render_pages", lambda p, fmt: [b"page"])

    f = tmp_path / "hard.pdf"
    f.write_bytes(b"%PDF-1.4\nfake")
    monkeypatch.setattr(
        ocr_mod, "model_read",
        lambda path, limits, **kw: ocr_mod.model_read.__wrapped__(path, limits)
        if hasattr(ocr_mod.model_read, "__wrapped__") else "model transcription",
    )
    doc = parse_file(f, allow_model=True)
    assert doc.tier == 3
    assert "model transcription" in doc.text


# ── Mistral document OCR ─────────────────────────────────────────────────────

class _FakeHTTP:
    """Stands in for httpx, recording the request."""

    def __init__(self, body=None, error=None):
        self.body = body or {"pages": [{"index": 0, "markdown": "# Heading\n\nBody."}]}
        self.error = error
        self.requests = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.requests.append({"url": url, "headers": headers, "json": json})
        if self.error:
            raise self.error

        outer = self

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return outer.body

        return R()


def _pdf(tmp_path, name="doc.pdf"):
    f = tmp_path / name
    f.write_bytes(b"%PDF-1.4\nfake pdf content")
    return f


def test_mistral_ocr_returns_markdown_per_page(tmp_path):
    from tawn.parsing.mistral_ocr import ocr_document

    http = _FakeHTTP({"pages": [
        {"index": 0, "markdown": "# Page one"},
        {"index": 1, "markdown": "## Page two"},
    ]})
    text = ocr_document(_pdf(tmp_path), TINY, key="k", http=http)
    assert "--- page 1 ---" in text
    assert "# Page one" in text
    assert "## Page two" in text


def test_the_document_is_sent_as_a_base64_data_uri(tmp_path):
    import base64

    from tawn.parsing.mistral_ocr import OCR_MODEL, ocr_document

    f = _pdf(tmp_path)
    http = _FakeHTTP()
    ocr_document(f, TINY, key="k", http=http)

    body = http.requests[0]["json"]
    assert body["model"] == OCR_MODEL
    assert body["document"]["type"] == "document_url"
    encoded = body["document"]["document_url"].split("base64,")[1]
    assert base64.b64decode(encoded) == f.read_bytes()


def test_an_image_is_sent_on_the_image_channel(tmp_path):
    from tawn.parsing.mistral_ocr import ocr_document

    f = tmp_path / "scan.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    http = _FakeHTTP()
    ocr_document(f, TINY, key="k", http=http)
    assert http.requests[0]["json"]["document"]["type"] == "image_url"


def test_the_key_travels_in_the_auth_header(tmp_path):
    from tawn.parsing.mistral_ocr import ocr_document

    http = _FakeHTTP()
    ocr_document(_pdf(tmp_path), TINY, key="sk-secret", http=http)
    assert http.requests[0]["headers"]["Authorization"] == "Bearer sk-secret"


def test_the_key_is_never_leaked_through_an_error(tmp_path):
    from tawn.parsing.mistral_ocr import ocr_document

    http = _FakeHTTP(error=RuntimeError("401 for key sk-secret"))
    with pytest.raises(ParseError) as exc:
        ocr_document(_pdf(tmp_path), TINY, key="sk-secret", http=http)
    assert "sk-secret" not in str(exc.value)
    assert "***" in str(exc.value)


def test_a_missing_key_says_how_to_set_one(tmp_path, monkeypatch):
    from tawn.parsing import mistral_ocr

    monkeypatch.setattr(mistral_ocr, "api_key", lambda home=None: None)
    with pytest.raises(ParseError) as exc:
        mistral_ocr.ocr_document(_pdf(tmp_path), TINY, http=_FakeHTTP())
    assert "tawn key set mistral" in str(exc.value)


def test_an_oversized_document_is_refused_before_upload(tmp_path, monkeypatch):
    from tawn.parsing import mistral_ocr

    monkeypatch.setattr(mistral_ocr, "MAX_DOCUMENT_BYTES", 10)
    http = _FakeHTTP()
    with pytest.raises(ParseError, match="over Mistral OCR"):
        mistral_ocr.ocr_document(_pdf(tmp_path), TINY, key="k", http=http)
    assert http.requests == []  # nothing was uploaded


def test_an_empty_response_is_reported(tmp_path):
    from tawn.parsing.mistral_ocr import ocr_document

    with pytest.raises(ParseError, match="no pages"):
        ocr_document(_pdf(tmp_path), TINY, key="k", http=_FakeHTTP({"pages": []}))


def test_mistral_is_preferred_over_generic_vision_when_a_key_exists(tmp_path, monkeypatch):
    """One request with real layout beats one chat call per page image."""
    from tawn.parsing import mistral_ocr
    from tawn.parsing import ocr as ocr_mod

    monkeypatch.setattr(mistral_ocr, "available", lambda home=None: True)
    monkeypatch.setattr(
        mistral_ocr, "ocr_document",
        lambda p, limits, home=None: "read by mistral ocr",
    )
    rendered = []
    monkeypatch.setattr(
        ocr_mod, "_render_pages",
        lambda p, fmt: rendered.append(1) or [b"x"],
    )
    assert ocr_mod.model_read(_pdf(tmp_path), TINY) == "read by mistral ocr"
    assert rendered == []  # the generic path was never touched


def test_a_mistral_failure_falls_through_to_generic_vision(tmp_path, monkeypatch):
    from tawn.parsing import mistral_ocr
    from tawn.parsing import ocr as ocr_mod

    monkeypatch.setattr(mistral_ocr, "available", lambda home=None: True)

    def _fail(p, limits, home=None):
        raise ParseError("mistral is down")

    monkeypatch.setattr(mistral_ocr, "ocr_document", _fail)
    monkeypatch.setattr(ocr_mod, "_render_pages", lambda p, fmt: [b"x"])
    monkeypatch.setattr(
        ocr_mod, "default_router" if hasattr(ocr_mod, "default_router") else "MODEL_DPI",
        ocr_mod.MODEL_DPI,
    )

    text = ocr_mod.model_read(_pdf(tmp_path), TINY, client=_VisionClient("vision fallback"))
    assert "vision fallback" in text


def test_without_a_key_mistral_is_skipped(tmp_path, monkeypatch):
    from tawn.parsing import mistral_ocr

    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr(mistral_ocr, "api_key", lambda home=None: None)
    assert mistral_ocr.available() is False
