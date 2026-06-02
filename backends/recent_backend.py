"""Recent paths backend — records and retrieves recently visited locations/files.

Trim policy (enforced on each insert):
    locations → keep newest 5
    files     → keep newest 10
"""
from __future__ import annotations

import time

from models.database import open_db

_MAX_LOCATIONS = 5
_MAX_FILES = 10


class RecentPathsBackend:
    def record_location(self, path: str) -> None:
        with open_db() as conn:
            conn.execute(
                "INSERT INTO recent_paths (path, type, last_accessed) VALUES (?, 'location', ?)"
                " ON CONFLICT(path, type) DO UPDATE SET last_accessed = excluded.last_accessed",
                (path, int(time.time())),
            )
            conn.execute(
                "DELETE FROM recent_paths WHERE type = 'location'"
                " AND path NOT IN ("
                "   SELECT path FROM recent_paths WHERE type = 'location'"
                "   ORDER BY last_accessed DESC LIMIT ?"
                ")",
                (_MAX_LOCATIONS,),
            )

    def list_locations(self, limit: int = _MAX_LOCATIONS) -> list[str]:
        with open_db() as conn:
            rows = conn.execute(
                "SELECT path FROM recent_paths WHERE type = 'location'"
                " ORDER BY last_accessed DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [row[0] for row in rows]

    def record_file(self, path: str) -> None:
        with open_db() as conn:
            conn.execute(
                "INSERT INTO recent_paths (path, type, last_accessed) VALUES (?, 'file', ?)"
                " ON CONFLICT(path, type) DO UPDATE SET last_accessed = excluded.last_accessed",
                (path, int(time.time())),
            )
            conn.execute(
                "DELETE FROM recent_paths WHERE type = 'file'"
                " AND path NOT IN ("
                "   SELECT path FROM recent_paths WHERE type = 'file'"
                "   ORDER BY last_accessed DESC LIMIT ?"
                ")",
                (_MAX_FILES,),
            )

    def list_files(self, limit: int = _MAX_FILES) -> list[str]:
        with open_db() as conn:
            rows = conn.execute(
                "SELECT path FROM recent_paths WHERE type = 'file'"
                " ORDER BY last_accessed DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [row[0] for row in rows]
