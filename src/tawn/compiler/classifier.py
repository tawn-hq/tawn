"""Domain classifier — infer domain from file content and path heuristics.

Used for external (granted-path) files that have no frontmatter domain tag.
"""

from __future__ import annotations

from pathlib import Path

_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "wealth": [
        "portfolio", "stock", "invest", "dividend", "equity", "ngx", "asset",
        "net worth", "networth", "bank account", "balance", "finance", "budget",
        "salary", "income", "expense", "profit", "loss", "trade", "fund",
        "bond", "forex", "crypto", "savings", "debt", "loan", "mortgage",
    ],
    "work": [
        "project", "task", "meeting", "deadline", "client", "sprint",
        "pull request", "commit", "deploy", "ticket", "bug", "feature",
        "employer", "contract", "deliverable", "roadmap", "standup",
        "retrospective", "milestone", "jira", "github", "slack",
    ],
    "research": [
        "paper", "arxiv", "hypothesis", "experiment", "dataset", "benchmark",
        "citation", "literature", "abstract", "journal", "conference",
        "methodology", "findings", "evaluation", "baseline", "ablation",
        "corpus", "annotation", "inference", "training", "fine-tuning",
    ],
    "academic": [
        "thesis", "dissertation", "phd", "msc", "professor", "supervisor",
        "scholarship", "campus", "lecture", "coursework", "semester",
        "application", "statement of purpose", "transcript", "gre",
        "research proposal", "defense", "committee",
    ],
}

# Path fragment → domain hint
_PATH_HINTS: dict[str, str] = {
    "work": "work",
    "job": "work",
    "projects": "work",
    "clients": "work",
    "wealth": "wealth",
    "finance": "wealth",
    "investing": "wealth",
    "portfolio": "wealth",
    "research": "research",
    "papers": "research",
    "arxiv": "research",
    "phd": "academic",
    "msc": "academic",
    "thesis": "academic",
    "academic": "academic",
    "university": "academic",
}


def classify(path: Path, content: str) -> str | None:
    """Return best-guess domain for an external file, or None if unclear."""
    text = content.lower()
    path_lower = str(path).lower()

    # Path hint wins if unambiguous
    for fragment, domain in _PATH_HINTS.items():
        if f"/{fragment}/" in path_lower or path_lower.endswith(f"/{fragment}"):
            return domain

    # Keyword scoring
    scores: dict[str, int] = {d: 0 for d in _DOMAIN_KEYWORDS}
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[domain] += 1

    best = max(scores, key=lambda d: scores[d])
    if scores[best] >= 2:
        return best

    return None
