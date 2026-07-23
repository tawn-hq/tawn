"""ConvTurn dataclass and BaseAdapter ABC for all federation adapters."""

from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConvTurn:
    role: str                                  # "user" | "assistant" | "system"
    content: str
    timestamp: datetime.datetime | None = None
    source: str = ""                           # adapter name
    metadata: dict = field(default_factory=dict)
    sensitive: bool = False


class BaseAdapter(ABC):
    """Base class for all federation source adapters."""

    name: str = ""
    default_domain: str = "unknown"
    DETECT_PATHS: list[str] = []   # known install dirs (expanduser'd at check time)
    DETECT_BINS: list[str] = []    # known executables to check in $PATH

    @abstractmethod
    def can_handle(self, path: Path) -> bool:
        """Return True if this adapter can parse the given file."""

    @abstractmethod
    def parse(self, path: Path) -> list[ConvTurn]:
        """Parse path into a list of ConvTurn. Never raises — return [] on error."""
