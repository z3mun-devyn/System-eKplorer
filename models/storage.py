from dataclasses import dataclass


def _fmt_bytes(n: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    val = float(n)
    for unit in units[:-1]:
        if val < 1024:
            return f"{val:.1f} {unit}"
        val /= 1024
    return f"{val:.1f} {units[-1]}"


@dataclass
class Drive:
    name: str
    device: str
    mount_point: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    fs_type: str
    device_id: str = ""
    label: str | None = None
    color_hex: str | None = None

    @property
    def used_pct(self) -> float:
        if self.total_bytes == 0:
            return 0.0
        return self.used_bytes / self.total_bytes

    @property
    def total_str(self) -> str:
        return _fmt_bytes(self.total_bytes)

    @property
    def used_str(self) -> str:
        return _fmt_bytes(self.used_bytes)

    @property
    def free_str(self) -> str:
        return _fmt_bytes(self.free_bytes)


@dataclass
class UnmountedDrive:
    name: str
    device: str
    size_bytes: int
    fs_type: str
    fs_label: str
    is_encrypted: bool
    device_id: str = ""

    @property
    def size_str(self) -> str:
        return _fmt_bytes(self.size_bytes)
