from __future__ import annotations

from pathlib import Path

from models.database import open_db


class SettingsRepository:
    """Generic key-value store backed by the settings table (schema v3)."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path

    def get(self, key: str) -> str | None:
        with open_db(self._db_path) as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else None

    def set(self, key: str, value: str) -> None:
        with open_db(self._db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
