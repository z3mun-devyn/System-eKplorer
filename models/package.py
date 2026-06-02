from dataclasses import dataclass, field
from datetime import datetime


def _fmt_kb(kb: int) -> str:
    if kb < 1024:
        return f"{kb} KB"
    mb = kb / 1024
    if mb < 1024:
        return f"{mb:.1f} MB"
    return f"{mb / 1024:.1f} GB"


@dataclass
class Package:
    name: str
    version: str
    installed_size_kb: int
    section: str
    source: str = field(default="apt")
    display_name: str = field(default="")  # flatpak friendly name; "" = use name
    installed_on: datetime | None = field(default=None)
    update_version: str | None = field(default=None)

    @property
    def size_str(self) -> str:
        return _fmt_kb(self.installed_size_kb)
