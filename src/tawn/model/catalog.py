"""Curated Ollama model catalog — explore what to run locally.

Ollama has no public library-listing API, so this is hand-curated:
download size and a realistic RAM floor per model, so `tawn model explore`
can say what actually fits the user's machine. Sizes are the default q4
quantizations from ollama.com/library.
"""

from pydantic import BaseModel

from tawn.model.providers.ollama import recommend_model

GB = 1024**3


class ModelInfo(BaseModel):
    name: str  # ollama tag, e.g. "qwen2.5:7b"
    download_gb: float  # approximate q4 download size
    min_ram_gb: float  # comfortable total-RAM floor to run it
    category: str  # chat | code | reasoning | vision | embedding
    blurb: str


def _m(name: str, dl: float, ram: float, cat: str, blurb: str) -> ModelInfo:
    return ModelInfo(name=name, download_gb=dl, min_ram_gb=ram, category=cat, blurb=blurb)


CATALOG: list[ModelInfo] = [
    # --- general chat ---
    _m("qwen2.5:1.5b", 1.0, 4, "chat", "tiny generalist — fine on any box"),
    _m("qwen2.5:3b", 1.9, 6, "chat", "small generalist, quick answers"),
    _m("qwen2.5:7b", 4.7, 12, "chat", "tawn's default — strong all-rounder"),
    _m("qwen2.5:14b", 9.0, 24, "chat", "sharper reasoning, needs headroom"),
    _m("qwen2.5:32b", 20.0, 48, "chat", "best qwen2.5 quality, workstation class"),
    _m("qwen3:0.6b", 0.5, 4, "chat", "newest qwen, smallest cut"),
    _m("qwen3:4b", 2.6, 6, "chat", "newest qwen, laptop friendly"),
    _m("qwen3:8b", 5.2, 12, "chat", "newest qwen mid-size"),
    _m("qwen3:14b", 9.3, 24, "chat", "newest qwen, strong tier"),
    _m("qwen3:32b", 20.0, 48, "chat", "newest qwen flagship dense"),
    _m("llama3.2:1b", 1.3, 4, "chat", "Meta's smallest, very fast"),
    _m("llama3.2:3b", 2.0, 6, "chat", "small Meta generalist"),
    _m("llama3.1:8b", 4.9, 12, "chat", "Meta 8B, solid and well-known"),
    _m("llama3.3:70b", 43.0, 64, "chat", "Meta's big one — server hardware"),
    _m("mistral:7b", 4.4, 12, "chat", "fast European generalist"),
    _m("mistral-nemo:12b", 7.1, 16, "chat", "Mistral × NVIDIA, 128k context"),
    _m("mistral-small:24b", 14.0, 32, "chat", "near-frontier local quality"),
    _m("mixtral:8x7b", 26.0, 48, "chat", "MoE classic, wide knowledge"),
    _m("gemma2:2b", 1.6, 4, "chat", "Google's small model"),
    _m("gemma2:9b", 5.4, 16, "chat", "Google mid-size, strong chat"),
    _m("gemma2:27b", 16.0, 32, "chat", "Google's big gemma2"),
    _m("gemma3:1b", 0.8, 4, "chat", "newest gemma, tiny"),
    _m("gemma3:4b", 3.3, 8, "chat", "newest gemma, laptop friendly"),
    _m("gemma3:12b", 8.1, 16, "chat", "newest gemma mid-size"),
    _m("gemma3:27b", 17.0, 32, "chat", "newest gemma flagship"),
    _m("smollm2:1.7b", 1.8, 4, "chat", "HuggingFace tiny, surprisingly able"),
    _m("tinyllama:1.1b", 0.6, 4, "chat", "smallest usable llama"),
    _m("command-r:35b", 20.0, 48, "chat", "Cohere, RAG/citation focused"),
    # --- reasoning ---
    _m("deepseek-r1:1.5b", 1.1, 4, "reasoning", "tiny thinker — shows its work"),
    _m("deepseek-r1:7b", 4.7, 12, "reasoning", "reasoning-tuned, thinks out loud"),
    _m("deepseek-r1:8b", 4.9, 12, "reasoning", "llama-based R1 distill"),
    _m("deepseek-r1:14b", 9.0, 24, "reasoning", "bigger reasoning tier"),
    _m("deepseek-r1:32b", 20.0, 48, "reasoning", "strongest local reasoner"),
    _m("phi4:14b", 9.1, 24, "reasoning", "Microsoft, strong reasoning per GB"),
    _m("phi4-mini:3.8b", 2.5, 6, "reasoning", "Microsoft small reasoner"),
    # --- code ---
    _m("qwen2.5-coder:1.5b", 1.0, 4, "code", "code autocomplete on anything"),
    _m("qwen2.5-coder:7b", 4.7, 12, "code", "code-tuned qwen — great default"),
    _m("qwen2.5-coder:14b", 9.0, 24, "code", "stronger code reasoning"),
    _m("qwen2.5-coder:32b", 20.0, 48, "code", "best local coder"),
    _m("codellama:7b", 3.8, 12, "code", "Meta's code classic"),
    _m("codellama:13b", 7.4, 16, "code", "bigger codellama"),
    _m("codegemma:7b", 5.0, 12, "code", "Google code model"),
    _m("starcoder2:3b", 1.7, 6, "code", "lightweight completion engine"),
    _m("deepseek-coder-v2:16b", 8.9, 24, "code", "MoE coder, fast for its size"),
    # --- vision ---
    _m("llava:7b", 4.7, 12, "vision", "describes and reads images"),
    _m("llava:13b", 8.0, 16, "vision", "sharper image understanding"),
    _m("moondream:1.8b", 1.7, 4, "vision", "tiny vision — runs anywhere"),
    _m("minicpm-v:8b", 5.5, 12, "vision", "strong OCR and charts"),
    # --- embeddings (memory search, stage 3) ---
    _m("nomic-embed-text:latest", 0.3, 4, "embedding", "embeddings for memory search"),
    _m("mxbai-embed-large:latest", 0.7, 4, "embedding", "high-quality embeddings"),
    _m("all-minilm:latest", 0.1, 4, "embedding", "smallest embedder, instant"),
    _m("snowflake-arctic-embed:latest", 0.7, 4, "embedding", "retrieval-tuned embeddings"),
]


def explore(ram_bytes: int, installed: set[str]) -> list[dict]:
    """Catalog annotated for this machine: fits / installed / recommended."""
    recommended = recommend_model(ram_bytes)
    rows = [
        {
            "name": m.name,
            "download_gb": m.download_gb,
            "min_ram_gb": m.min_ram_gb,
            "category": m.category,
            "blurb": m.blurb,
            "fits": ram_bytes >= m.min_ram_gb * GB,
            "installed": m.name in installed,
            "recommended": m.name == recommended,
        }
        for m in CATALOG
    ]
    rows.sort(key=lambda r: (not r["fits"], r["min_ram_gb"], r["name"]))
    return rows
