"""Query parser for the Packages search bar.

Converts the user's search string into a frozen PackageQuery dataclass.
No Qt dependency — pure Python.

Syntax:
  firefox                  → name contains "firefox"
  tagged:essential         → tag contains "essential"
  tagged: essential        → same (lenient space after colon)
  source:flatpak category:games  → two modifiers, AND-combined
  TAGGED:essential         → modifier names are case-insensitive
  colour:red firefox       → unknown modifier "colour:red" → free-text name
  tagged:                  → trailing colon, no value → empty (no crash)
"""
from __future__ import annotations

from dataclasses import dataclass

import strings

# Map of lowercase modifier token → PackageQuery field name
_TOKEN_MAP: dict[str, str] = {
    strings.QUERY_TOKEN_TAGGED:   "tag",
    strings.QUERY_TOKEN_CATEGORY: "category",
    strings.QUERY_TOKEN_SOURCE:   "source",
    strings.QUERY_TOKEN_VERSION:  "version",
    strings.QUERY_TOKEN_SIZE:     "size",
}


@dataclass(frozen=True)
class PackageQuery:
    name: str = ""      # free-text; matches display_name or name
    tag: str = ""       # from tagged:
    category: str = ""  # from category:
    source: str = ""    # from source:
    version: str = ""   # from version:
    size: str = ""      # from size:


EMPTY = PackageQuery()


def parse(text: str) -> PackageQuery:
    """Parse a search string and return a frozen PackageQuery."""
    tokens = text.split()
    kw: dict[str, str] = {}
    name_parts: list[str] = []
    pending_field: str | None = None

    for token in tokens:
        if pending_field is not None:
            kw[pending_field] = token.lower()
            pending_field = None
            continue

        if ":" in token:
            prefix, _, rest = token.partition(":")
            field = _TOKEN_MAP.get(prefix.lower())
            if field is not None:
                if rest:
                    kw[field] = rest.lower()
                else:
                    # "tagged:" with no value yet — consume next token
                    pending_field = field
                continue
            # Unknown modifier → whole token is free text

        name_parts.append(token)

    return PackageQuery(
        name=" ".join(name_parts).lower(),
        tag=kw.get("tag", ""),
        category=kw.get("category", ""),
        source=kw.get("source", ""),
        version=kw.get("version", ""),
        size=kw.get("size", ""),
    )
