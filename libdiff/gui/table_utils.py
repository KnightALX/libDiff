"""Adaptive visible-row helpers for Fluent/Qt tables."""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QEvent, QObject
from PyQt5.QtWidgets import QHeaderView, QTableWidget


class _ParentResizeFilter(QObject):
    def __init__(self, table: QTableWidget, apply_cb):
        super().__init__(table)
        self._table = table
        self._apply = apply_cb

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize:
            self._apply()
        return super().eventFilter(obj, event)


def configure_adaptive_row_height(
    table: QTableWidget,
    default_visible_rows: int = 6,
    min_rows: int = 4,
    max_rows: Optional[int] = None,
    row_height: int = 28,
    watch_parent: bool = True,
    enforce_minimum: bool = True,
) -> None:
    """Show ~default_visible_rows by default; grow with available height.

    Sets a fixed row height and optionally a minimumHeight based on header + N rows.
    When enforce_minimum is False, skips the hard minimum (or uses a tiny header+2
    rows floor) so QSplitter can shrink the table. Does not cap maximum height.
    """
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    table.setWordWrap(False)
    # Prefer Interactive/stretch for columns; rows stay fixed height for predictability
    try:
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    except Exception:
        pass

    def _header_h() -> int:
        hh = table.horizontalHeader().height()
        if hh <= 0:
            hh = table.horizontalHeader().sizeHint().height()
        return max(hh, 24)

    def _frame() -> int:
        return max(table.frameWidth() * 2, 2) + 4

    def apply_min_height() -> None:
        # Ensure existing rows use fixed height
        for r in range(table.rowCount()):
            table.setRowHeight(r, row_height)

        if not enforce_minimum:
            # Tiny floor only — do not fight QSplitter drag range
            table.setMinimumHeight(_header_h() + 2 * row_height + _frame())
            return

        rows = max(default_visible_rows, min_rows)
        if max_rows is not None:
            rows = min(rows, max_rows)
        table.setMinimumHeight(_header_h() + rows * row_height + _frame())

    apply_min_height()
    table._libdiff_apply_row_height = apply_min_height  # type: ignore[attr-defined]

    if watch_parent:
        parent = table.parentWidget()
        if parent is not None:
            filt = _ParentResizeFilter(table, apply_min_height)
            parent.installEventFilter(filt)
            table._libdiff_resize_filter = filt  # type: ignore[attr-defined]
