from __future__ import annotations

from pathlib import Path

from models.database import open_db
from models.tag import Tag


class TagRepository:
    """Stateless CRUD helper for tags and package_tag assignments."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path

    def all_tags(self) -> list[Tag]:
        with open_db(self._db_path) as conn:
            rows = conn.execute(
                "SELECT name, color_hex FROM tags ORDER BY name"
            ).fetchall()
        return [Tag(name=r["name"], color_hex=r["color_hex"]) for r in rows]

    def tags_for_package(self, source: str, name: str) -> list[Tag]:
        with open_db(self._db_path) as conn:
            rows = conn.execute(
                "SELECT t.name, t.color_hex"
                " FROM tags t JOIN package_tags pt ON pt.tag_name = t.name"
                " WHERE pt.package_source = ? AND pt.package_name = ?"
                " ORDER BY t.name",
                (source, name),
            ).fetchall()
        return [Tag(name=r["name"], color_hex=r["color_hex"]) for r in rows]

    def tag_counts(self) -> dict[str, int]:
        """Return {tag_name: count} for tags with at least one assignment."""
        with open_db(self._db_path) as conn:
            rows = conn.execute(
                "SELECT tag_name, COUNT(*) AS cnt FROM package_tags GROUP BY tag_name"
            ).fetchall()
        return {r["tag_name"]: r["cnt"] for r in rows}

    def load_all_assignments(self) -> dict[tuple[str, str], list[Tag]]:
        """Bulk-load all assignments. Returns {(source, pkg_name): [Tag, ...]}."""
        with open_db(self._db_path) as conn:
            rows = conn.execute(
                "SELECT pt.package_source, pt.package_name,"
                "       t.name, t.color_hex"
                " FROM package_tags pt JOIN tags t ON t.name = pt.tag_name"
                " ORDER BY pt.package_name, t.name"
            ).fetchall()
        result: dict[tuple[str, str], list[Tag]] = {}
        for r in rows:
            key = (r["package_source"], r["package_name"])
            result.setdefault(key, []).append(
                Tag(name=r["name"], color_hex=r["color_hex"])
            )
        return result

    def create_tag(self, name: str, color_hex: str) -> None:
        """Insert a new tag. Raises sqlite3.IntegrityError on duplicate name."""
        with open_db(self._db_path) as conn:
            conn.execute(
                "INSERT INTO tags (name, color_hex) VALUES (?, ?)", (name, color_hex)
            )

    def set_assignments(
        self, source: str, pkg_name: str, assigned_names: set[str]
    ) -> None:
        """Replace all tag assignments for a package with the given name set."""
        with open_db(self._db_path) as conn:
            conn.execute(
                "DELETE FROM package_tags"
                " WHERE package_source = ? AND package_name = ?",
                (source, pkg_name),
            )
            for tag_name in assigned_names:
                conn.execute(
                    "INSERT OR IGNORE INTO package_tags"
                    " (package_source, package_name, tag_name) VALUES (?, ?, ?)",
                    (source, pkg_name, tag_name),
                )
