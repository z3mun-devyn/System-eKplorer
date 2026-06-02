from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from backends.settings_backend import SettingsRepository
from models.clipboard_entry import ClipboardEntry
from models.database import open_db

_DEFAULT_MAX = 10
_SETTINGS_KEY = "clipboard.max_entries"


class ClipboardBackend:
    """Synchronous clipboard history store (called on the main thread)."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path
        self._settings = SettingsRepository(db_path)

    # ── Settings ──────────────────────────────────────────────────────────────

    @property
    def max_entries(self) -> int:
        v = self._settings.get(_SETTINGS_KEY)
        if v is None:
            return _DEFAULT_MAX
        try:
            return max(1, int(v))
        except ValueError:
            return _DEFAULT_MAX

    @max_entries.setter
    def max_entries(self, value: int) -> None:
        self._settings.set(_SETTINGS_KEY, str(max(1, value)))

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add_entry(self, content: str) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        limit = self.max_entries
        with open_db(self._db_path) as conn:
            conn.execute(
                "INSERT INTO clipboard_history (content, captured_at, pinned)"
                " VALUES (?, ?, 0)",
                (content, now),
            )
            # Evict oldest non-pinned rows beyond the limit.
            # LIMIT -1 OFFSET n is a SQLite idiom for "all rows after the n-th".
            conn.execute(
                """
                DELETE FROM clipboard_history
                WHERE id IN (
                    SELECT id FROM clipboard_history
                    WHERE pinned = 0
                    ORDER BY id DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (limit,),
            )

    def list_entries(self) -> list[ClipboardEntry]:
        """Return all entries, pinned first then newest-first within each group."""
        with open_db(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id, content, captured_at, pinned"
                " FROM clipboard_history"
                " ORDER BY pinned DESC, id DESC"
            ).fetchall()
        return [
            ClipboardEntry(
                id=r["id"],
                content=r["content"],
                captured_at=r["captured_at"],
                pinned=bool(r["pinned"]),
            )
            for r in rows
        ]

    def delete_entry(self, entry_id: int) -> None:
        with open_db(self._db_path) as conn:
            conn.execute(
                "DELETE FROM clipboard_history WHERE id = ?", (entry_id,)
            )

    def toggle_pin(self, entry_id: int) -> None:
        with open_db(self._db_path) as conn:
            conn.execute(
                "UPDATE clipboard_history SET pinned = 1 - pinned WHERE id = ?",
                (entry_id,),
            )

    def clear_unpinned(self) -> None:
        with open_db(self._db_path) as conn:
            conn.execute("DELETE FROM clipboard_history WHERE pinned = 0")

    def enforce_limit(self) -> None:
        """Evict oldest non-pinned entries beyond current max_entries."""
        limit = self.max_entries
        with open_db(self._db_path) as conn:
            conn.execute(
                """
                DELETE FROM clipboard_history
                WHERE id IN (
                    SELECT id FROM clipboard_history
                    WHERE pinned = 0
                    ORDER BY id DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (limit,),
            )
