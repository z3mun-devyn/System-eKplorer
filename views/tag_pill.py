"""TagPill — toggle button used inside the tag editor modal."""

from __future__ import annotations

import strings
from models.tag import Tag

from PyQt6.QtWidgets import QPushButton, QWidget


class TagPill(QPushButton):
    """Pill-shaped toggle representing a single tag in the editor modal."""

    def __init__(self, tag: Tag, assigned: bool,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tag = tag
        self._assigned = assigned
        self._refresh()
        self.setCheckable(True)
        self.setChecked(assigned)
        self.clicked.connect(self._on_click)

    def _on_click(self) -> None:
        self._assigned = not self._assigned
        self._refresh()

    def is_assigned(self) -> bool:
        return self._assigned

    def _refresh(self) -> None:
        bg = self.tag.color_hex
        fg = strings.contrast_color(bg)
        border = f"3px solid {fg}" if self._assigned else "2px solid transparent"
        self.setText(("✓ " if self._assigned else "") + self.tag.name)
        self.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {bg}; color: {fg};"
            f"  border: {border}; border-radius: 10px;"
            f"  padding: 2px 10px; font-size: 12px;"
            f"}}"
        )
        self.adjustSize()
