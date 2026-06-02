import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path.home() / ".local" / "share" / "ekplorer" / "data.db"

CURRENT_VERSION = 6

_V1_DDL = [
    """
    CREATE TABLE IF NOT EXISTS drive_labels (
        device_id TEXT PRIMARY KEY,
        label     TEXT NOT NULL,
        color_hex TEXT,
        updated_at TEXT NOT NULL
    )
    """,
]

_V2_DDL = [
    """
    CREATE TABLE IF NOT EXISTS tags (
        name      TEXT PRIMARY KEY,
        color_hex TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS package_tags (
        package_source TEXT NOT NULL,
        package_name   TEXT NOT NULL,
        tag_name       TEXT NOT NULL REFERENCES tags(name) ON DELETE CASCADE,
        PRIMARY KEY (package_source, package_name, tag_name)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_pkg_tags
        ON package_tags (package_source, package_name)
    """,
]

_V3_DDL = [
    """
    CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
]

_V4_DDL = [
    """
    CREATE TABLE IF NOT EXISTS recent_paths (
        path          TEXT    NOT NULL,
        type          TEXT    NOT NULL CHECK(type IN ('file', 'location')),
        last_accessed INTEGER NOT NULL,
        PRIMARY KEY (path, type)
    )
    """,
]

_V5_DDL = [
    """
    CREATE TABLE IF NOT EXISTS file_tags (
        path     TEXT NOT NULL,
        tag_name TEXT NOT NULL REFERENCES tags(name) ON DELETE CASCADE,
        PRIMARY KEY (path, tag_name)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_file_tags_path
        ON file_tags (path)
    """,
]

_V6_DDL = [
    """
    CREATE TABLE IF NOT EXISTS clipboard_history (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        content     TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        pinned      INTEGER DEFAULT 0
    )
    """,
]


def _apply_schema(conn: sqlite3.Connection) -> None:
    uv = conn.execute("PRAGMA user_version").fetchone()[0]
    if uv >= CURRENT_VERSION:
        return

    if uv == 0:
        # Detect v1 DB from M2 by presence of legacy schema_version table.
        # If absent this is a fresh DB; create V1 tables first.
        has_legacy = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        ).fetchone() is not None
        if not has_legacy:
            for stmt in _V1_DDL:
                conn.execute(stmt)

    if uv < 2:
        # IF NOT EXISTS makes V2 DDL safe for both fresh and v1 upgrade paths.
        for stmt in _V2_DDL:
            conn.execute(stmt)

    if uv < 3:
        for stmt in _V3_DDL:
            conn.execute(stmt)

    if uv < 4:
        for stmt in _V4_DDL:
            conn.execute(stmt)

    if uv < 5:
        for stmt in _V5_DDL:
            conn.execute(stmt)

    if uv < 6:
        for stmt in _V6_DDL:
            conn.execute(stmt)

    conn.execute(f"PRAGMA user_version = {CURRENT_VERSION}")
    conn.commit()


@contextmanager
def open_db(path: Path | None = None):
    target = path if path is not None else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.parent.chmod(0o700)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        _apply_schema(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
