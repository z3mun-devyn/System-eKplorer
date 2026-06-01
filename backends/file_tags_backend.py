"""File tag persistence — assigns tags (from the shared `tags` table) to file paths."""
from __future__ import annotations

from pathlib import Path

from models.database import open_db
from models.tag import Tag


class FileTagRepository:
    """Stateless CRUD helper for file-path → tag assignments.

    Tags themselves (name + color) live in the shared `tags` table.
    `file_tags` is the junction table: (path, tag_name).
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path

    def tags_for_path(self, path: str) -> list[Tag]:
        with open_db(self._db_path) as conn:
            rows = conn.execute(
                "SELECT t.name, t.color_hex"
                " FROM tags t JOIN file_tags ft ON ft.tag_name = t.name"
                " WHERE ft.path = ?"
                " ORDER BY t.name",
                (path,),
            ).fetchall()
        return [Tag(name=r["name"], color_hex=r["color_hex"]) for r in rows]

    def bulk_load(self, paths: list[str]) -> dict[str, list[Tag]]:
        """Return {path: [Tag, ...]} for every path that has at least one tag."""
        if not paths:
            return {}
        placeholders = ",".join("?" * len(paths))
        with open_db(self._db_path) as conn:
            rows = conn.execute(
                f"SELECT ft.path, t.name, t.color_hex"
                f" FROM file_tags ft JOIN tags t ON t.name = ft.tag_name"
                f" WHERE ft.path IN ({placeholders})"
                f" ORDER BY ft.path, t.name",
                paths,
            ).fetchall()
        result: dict[str, list[Tag]] = {}
        for r in rows:
            result.setdefault(r["path"], []).append(
                Tag(name=r["name"], color_hex=r["color_hex"])
            )
        return result

    def set_assignments(self, path: str, assigned_names: set[str]) -> None:
        """Replace all tag assignments for a file path with the given name set."""
        with open_db(self._db_path) as conn:
            conn.execute("DELETE FROM file_tags WHERE path = ?", (path,))
            for tag_name in assigned_names:
                conn.execute(
                    "INSERT OR IGNORE INTO file_tags (path, tag_name) VALUES (?, ?)",
                    (path, tag_name),
                )
