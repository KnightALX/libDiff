"""Reusable chart-first layout helpers for libDiff Fluent GUI."""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import SimpleCardWidget, StrongBodyLabel


PLOT_MIN_H = 160
TABLE_MIN_H = 64

# Subtle drag handle: visible bar + hover accent (vertical & horizontal)
_SPLITTER_HANDLE_STYLE = """
QSplitter::handle {
    background-color: rgba(128, 128, 128, 0.40);
    border-radius: 2px;
}
QSplitter::handle:hover {
    background-color: rgba(0, 120, 215, 0.80);
}
QSplitter::handle:pressed {
    background-color: rgba(0, 90, 180, 0.95);
}
QSplitter::handle:vertical {
    margin: 2px 8px;
    min-height: 6px;
}
QSplitter::handle:horizontal {
    margin: 8px 2px;
    min-width: 6px;
}
"""


def _style_splitter(split: QSplitter) -> None:
    split.setHandleWidth(10)
    split.setStyleSheet(_SPLITTER_HANDLE_STYLE)


def apply_split_ratio(
    splitter: QSplitter,
    top_ratio: float = 0.78,
) -> None:
    """Apply a chart-heavy size ratio after the splitter has a real geometry."""
    if splitter is None:
        return
    sizes = splitter.sizes()
    total = sum(sizes)
    if total <= 0:
        # Fallbacks before first layout pass
        if splitter.orientation() == Qt.Vertical:
            total = max(splitter.height(), 960)
        else:
            total = max(splitter.width(), 960)
    if total <= 0:
        total = 960
    ratio = min(max(float(top_ratio), 0.05), 0.95)
    top = max(1, int(round(total * ratio)))
    bottom = max(1, total - top)
    splitter.setSizes([top, bottom])


def make_v_splitter(
    top: QWidget,
    bottom: QWidget,
    top_stretch: int = 4,
    bottom_stretch: int = 1,
    initial_sizes: Optional[Sequence[int]] = None,
    top_min: int = PLOT_MIN_H,
    bottom_min: int = TABLE_MIN_H,
) -> QSplitter:
    """Vertical splitter with chart-heavy stretch (top=chart, bottom=table)."""
    split = QSplitter(Qt.Vertical)
    split.setChildrenCollapsible(True)
    _style_splitter(split)
    top.setMinimumHeight(max(0, int(top_min)))
    bottom.setMinimumHeight(max(0, int(bottom_min)))
    split.addWidget(top)
    split.addWidget(bottom)
    split.setStretchFactor(0, int(top_stretch))
    split.setStretchFactor(1, int(bottom_stretch))
    if initial_sizes is not None:
        split.setSizes([int(s) for s in initial_sizes])
    else:
        # Prefer ~80/20 until the user drags / showEvent applies ratio
        split.setSizes([780, 180])
    return split


def make_h_splitter(
    left: QWidget,
    right: QWidget,
    left_stretch: int = 1,
    right_stretch: int = 1,
    initial_sizes: Optional[Sequence[int]] = None,
    left_min: int = 160,
    right_min: int = 160,
) -> QSplitter:
    """Horizontal splitter for side-by-side plots."""
    split = QSplitter(Qt.Horizontal)
    split.setChildrenCollapsible(True)
    _style_splitter(split)
    left.setMinimumWidth(max(0, int(left_min)))
    right.setMinimumWidth(max(0, int(right_min)))
    split.addWidget(left)
    split.addWidget(right)
    split.setStretchFactor(0, int(left_stretch))
    split.setStretchFactor(1, int(right_stretch))
    if initial_sizes is not None:
        split.setSizes([int(s) for s in initial_sizes])
    else:
        split.setSizes([500, 500])
    return split


def wrap_card(
    title: Optional[str],
    widget: QWidget,
    *,
    margins: Tuple[int, int, int, int] = (12, 12, 12, 12),
    stretch_widget: bool = True,
) -> SimpleCardWidget:
    """Wrap a widget in a SimpleCardWidget with an optional title label."""
    card = SimpleCardWidget()
    layout = QVBoxLayout(card)
    layout.setContentsMargins(*margins)
    layout.setSpacing(8)
    if title:
        layout.addWidget(StrongBodyLabel(title))
    widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    layout.addWidget(widget, 1 if stretch_widget else 0)
    return card


def labeled_pane(
    title: Optional[str],
    widget: QWidget,
    *,
    min_height: int = 0,
) -> QWidget:
    """Plain (non-card) pane with optional title — for nested splitter children."""
    pane = QWidget()
    layout = QVBoxLayout(pane)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    if title:
        layout.addWidget(StrongBodyLabel(title))
    if min_height > 0:
        widget.setMinimumHeight(min_height)
    widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    layout.addWidget(widget, 1)
    return pane


class ChartTableSection(QWidget):
    """Vertical chart-top / table-bottom section with stretch ~4:1."""

    def __init__(
        self,
        chart_widget: QWidget,
        table_widget: QWidget,
        chart_title: str = "Chart",
        table_title: str = "Table",
        parent: Optional[QWidget] = None,
        top_stretch: int = 4,
        bottom_stretch: int = 1,
        initial_sizes: Optional[Sequence[int]] = None,
        top_ratio: float = 0.78,
    ):
        super().__init__(parent=parent)
        self._top_ratio = float(top_ratio)
        self._ratio_applied = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        chart_pane = labeled_pane(chart_title, chart_widget, min_height=PLOT_MIN_H)
        table_pane = labeled_pane(table_title, table_widget, min_height=TABLE_MIN_H)
        chart_pane.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table_pane.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.splitter = make_v_splitter(
            chart_pane,
            table_pane,
            top_stretch=top_stretch,
            bottom_stretch=bottom_stretch,
            initial_sizes=initial_sizes if initial_sizes is not None else [780, 180],
            top_min=PLOT_MIN_H,
            bottom_min=TABLE_MIN_H,
        )
        root.addWidget(self.splitter, 1)

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if self._ratio_applied:
            return
        self._ratio_applied = True
        QTimer.singleShot(0, lambda: apply_split_ratio(self.splitter, self._top_ratio))
