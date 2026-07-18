import httpx
import respx

from tawn.model.directory import (
    LIBRARY_URL,
    estimate_min_ram_gb,
    fetch_library,
    fetch_tags,
    live_explore,
)

GB = 1024**3

LIBRARY_HTML = """
<html><body>
<a href="/library/qwen2.5">qwen2.5</a>
<a href="/library/deepseek-r1">deepseek-r1</a>
<a href="/library/nomic-embed-text">nomic-embed-text</a>
<a href="/library/qwen2.5">qwen2.5</a>
<a href="/blog/something">blog</a>
</body></html>
"""

TAGS_HTML = """
<html><body>
<span>qwen2.5:latest</span><span>4.7GB</span>
<span>qwen2.5:0.5b</span><span>398MB</span>
<span>qwen2.5:7b</span><span>4.7GB</span>
<span>qwen2.5:7b</span><span>4.7GB</span>
</body></html>
"""


@respx.mock
def test_fetch_library_parses_unique_names():
    respx.get(LIBRARY_URL).mock(return_value=httpx.Response(200, text=LIBRARY_HTML))
    names = fetch_library()
    assert names == ["qwen2.5", "deepseek-r1", "nomic-embed-text"]


@respx.mock
def test_fetch_tags_parses_sizes_and_dedupes():
    respx.get(f"{LIBRARY_URL}/qwen2.5/tags").mock(
        return_value=httpx.Response(200, text=TAGS_HTML)
    )
    tags = fetch_tags("qwen2.5")
    by_name = {t["name"]: t for t in tags}
    assert by_name["qwen2.5:7b"]["download_gb"] == 4.7
    assert abs(by_name["qwen2.5:0.5b"]["download_gb"] - 0.398) < 0.01
    assert len(tags) == len(by_name)  # deduped


def test_estimate_min_ram_scales_with_download():
    assert estimate_min_ram_gb(0.4) == 4
    assert estimate_min_ram_gb(4.7) == 12
    assert estimate_min_ram_gb(9.0) == 24
    assert estimate_min_ram_gb(20.0) == 48


@respx.mock
def test_live_explore_annotates_fit_and_installed():
    respx.get(LIBRARY_URL).mock(return_value=httpx.Response(200, text=LIBRARY_HTML))
    respx.get(f"{LIBRARY_URL}/qwen2.5/tags").mock(
        return_value=httpx.Response(200, text=TAGS_HTML)
    )
    rows = live_explore(
        ram_bytes=16 * GB, installed={"qwen2.5:7b"}, models=["qwen2.5"]
    )
    by_name = {r["name"]: r for r in rows}
    assert by_name["qwen2.5:7b"]["installed"] is True
    assert by_name["qwen2.5:7b"]["fits"] is True
    assert by_name["qwen2.5:0.5b"]["fits"] is True


@respx.mock
def test_live_explore_offline_raises_for_fallback():
    import pytest

    respx.get(LIBRARY_URL).mock(side_effect=httpx.ConnectError("offline"))
    with pytest.raises(httpx.ConnectError):
        live_explore(ram_bytes=16 * GB, installed=set())
