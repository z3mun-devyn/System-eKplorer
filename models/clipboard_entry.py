from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClipboardEntry:
    id: int
    content: str
    captured_at: str  # ISO-8601 UTC
    pinned: bool
