import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path.home() / ".local" / "share" / "ekploiter" / "data.db"

CURRENT_VERSION = 1

_V1_DDL = [
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS drive_labels (
        device_id TEXT PRIMARY KEY,
        label TEXT NOT NULL,
        color_hex TEXT,
        updated_at TEXT NOT NULL
    )
    """,
]


def _apply_schema(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if row is None:
        for stmt in _V1_DDL:
            conn.execute(stmt)
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (CURRENT_VERSION,))
        conn.commit()
        return

    version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    # Future migrations go here: if version < 2: _migrate_v2(conn); ...
    _ = version  # nothing to migrate in v1


@contextmanager
def open_db(path: Path | None = None):
    target = path if path is not None else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.parent.chmod(0o700)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        _apply_schema(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
