"""Model daftar pesan untuk ListView di QML."""
from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, Slot

ROLE = Qt.ItemDataRole.UserRole + 1
TEXT = Qt.ItemDataRole.UserRole + 2


class MessageModel(QAbstractListModel):
    """Setiap pesan punya role: "user", "ai", atau "system", dan teks."""

    def __init__(self, limit: int = 200, parent=None) -> None:
        super().__init__(parent)
        self._items: list[tuple[str, str]] = []
        self._limit = limit

    def roleNames(self):  # noqa: N802 (nama dari Qt)
        return {ROLE: b"role", TEXT: b"text"}

    def rowCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        kind, text = self._items[index.row()]
        return kind if role == ROLE else text if role == TEXT else None

    def append(self, kind: str, text: str) -> None:
        if len(self._items) >= self._limit:
            self.beginRemoveRows(QModelIndex(), 0, 0)
            self._items.pop(0)
            self.endRemoveRows()
        row = len(self._items)
        self.beginInsertRows(QModelIndex(), row, row)
        self._items.append((kind, text))
        self.endInsertRows()

    @Slot(result=int)
    def count(self) -> int:
        return len(self._items)
