from __future__ import annotations

from dataclasses import dataclass, field

from models.package import Package


@dataclass
class Tag:
    name: str
    color_hex: str


@dataclass
class PackageEntry:
    package: Package
    tags: list[Tag] = field(default_factory=list)
