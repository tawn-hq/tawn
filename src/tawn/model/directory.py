"""Live Ollama directory — populate the explore list from ollama.com itself.

ollama.com has no JSON API, so this parses the library HTML: /library for
model names, /library/<name>/tags for tag + download size. Callers fall
back to the curated catalog when offline or if the markup shifts.
"""

import re

import httpx

LIBRARY_URL = "https://ollama.com/library"

_HREF_RE = re.compile(r'href="/library/([a-z0-9][a-z0-9._-]*)"')
_TAG_SIZE_RE = re.compile(
    r">\s*([a-z0-9][a-z0-9._-]*:[a-z0-9._-]+)\s*<|>\s*([\d.]+)\s*(GB|MB)\s*<"
)

# RAM floor ladder (GB): a q4 model comfortably needs ~2× its download size,
# rounded up to a realistic machine tier.
_TIERS = [4, 6, 8, 12, 16, 24, 32, 48, 64]


def estimate_min_ram_gb(download_gb: float) -> int:
    need = download_gb * 2.2
    for tier in _TIERS:
        if need <= tier:
            return tier
    return _TIERS[-1]


def _get(url: str, client: httpx.Client | None) -> str:
    if client is not None:
        resp = client.get(url)
    else:
        resp = httpx.get(url, timeout=20.0, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def fetch_library(client: httpx.Client | None = None) -> list[str]:
    """Model names on ollama.com/library, page order, deduped."""
    html = _get(LIBRARY_URL, client)
    seen: dict[str, None] = {}
    for name in _HREF_RE.findall(html):
        seen.setdefault(name)
    return list(seen)


def fetch_tags(model: str, client: httpx.Client | None = None) -> list[dict]:
    """[{name, download_gb}] for one model's tags page, deduped."""
    html = _get(f"{LIBRARY_URL}/{model}/tags", client)
    tags: dict[str, float] = {}
    current: str | None = None
    for m in _TAG_SIZE_RE.finditer(html):
        tag, num, unit = m.groups()
        if tag:
            current = tag
        elif current and current not in tags:
            size = float(num)
            tags[current] = size if unit == "GB" else size / 1024
    return [{"name": n, "download_gb": round(s, 3)} for n, s in tags.items()]


def live_explore(
    ram_bytes: int,
    installed: set[str],
    models: list[str] | None = None,
    client: httpx.Client | None = None,
) -> list[dict]:
    """Directory-backed explore rows, same shape as catalog.explore.

    Network errors propagate — the CLI catches them and falls back to the
    curated catalog.
    """
    GB = 1024**3
    names = models if models is not None else fetch_library(client)
    rows: list[dict] = []
    for model in names:
        for tag in fetch_tags(model, client):
            min_ram = estimate_min_ram_gb(tag["download_gb"])
            rows.append(
                {
                    "name": tag["name"],
                    "download_gb": tag["download_gb"],
                    "min_ram_gb": min_ram,
                    "category": "",
                    "blurb": "",
                    "fits": ram_bytes >= min_ram * GB,
                    "installed": tag["name"] in installed,
                    "recommended": False,
                }
            )
    rows.sort(key=lambda r: (not r["fits"], r["min_ram_gb"], r["name"]))
    return rows
