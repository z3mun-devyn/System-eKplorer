"""FileEntry dataclass — shared between directory backend, file view, and Properties panel."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileEntry:
    name: str
    path: Path
    size: int | None        # None for directories
    modified: float         # mtime as epoch seconds
    mime_type: str          # e.g. "inode/directory", "text/plain"
    is_dir: bool
    is_hidden: bool         # name starts with "."
    item_count: int | None = None  # subdirectory item count (dirs only)


def fmt_size(n: int | None) -> str:
    """Human-readable file size.  None (directory) → empty string."""
    if n is None:
        return ""
    units = ("B", "KB", "MB", "GB", "TB")
    val = float(n)
    for unit in units[:-1]:
        if val < 1024:
            return f"{val:.1f} {unit}"
        val /= 1024
    return f"{val:.1f} {units[-1]}"


def mime_label(mime_type: str, is_dir: bool = False) -> str:
    """Convert a MIME type to a short human-readable description."""
    if is_dir:
        return "Folder"
    _MAP = {
        "inode/directory":            "Folder",
        "text/plain":                 "Text File",
        "text/html":                  "HTML File",
        "text/css":                   "CSS File",
        "text/javascript":            "JavaScript File",
        "application/pdf":            "PDF Document",
        "application/zip":            "ZIP Archive",
        "application/x-tar":          "TAR Archive",
        "application/gzip":           "GZipped Archive",
        "application/x-bzip2":        "BZ2 Archive",
        "application/x-7z-compressed":"7-Zip Archive",
        "application/json":           "JSON File",
        "application/xml":            "XML File",
        "application/octet-stream":   "Binary File",
        "image/jpeg":                 "JPEG Image",
        "image/png":                  "PNG Image",
        "image/gif":                  "GIF Image",
        "image/svg+xml":              "SVG Image",
        "image/webp":                 "WebP Image",
        "audio/mpeg":                 "MP3 Audio",
        "audio/ogg":                  "OGG Audio",
        "audio/flac":                 "FLAC Audio",
        "video/mp4":                  "MP4 Video",
        "video/x-matroska":           "MKV Video",
        "video/webm":                 "WebM Video",
    }
    if mime_type in _MAP:
        return _MAP[mime_type]
    if "/" in mime_type:
        _, sub = mime_type.split("/", 1)
        return sub.replace("-", " ").replace("x.", "").replace("+", " ").title()
    return mime_type
