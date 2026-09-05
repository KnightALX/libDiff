"""Reusable chart-first layout helpers for libDiff Fluent GUI."""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import SimpleCardWidget, StrongBodyLabel


PLOT_MIN_H = 280
TABLE_MIN_H = 120


def make_v_splitter(
    top: QWidget,
    bottom: QWidget,
    top_stretch: int = 3,
    bottom_stretch: int = 2,
    initial_sizes: Optional[Sequence[int]] = None,
    top_min: int = PLOT_MIN_H,
    bottom_min: int = TABLE_MIN_H,
) -> QSplitter:
    """Vertical splitter with chart-heavy stretch (top=chart, bottom=table)."""
    split = QSplitter(Qt.Vertical)
    split.setChildrenCollapsible(False)
    split.setHandleWidth(6)
    top.setMinimumHeight(max(0, int(top_min)))
    bottom.setMinimumHeight(max(0, int(bottom_min)))
    split.addWidget(top)
    split.addWidget(bottom)
    split.setStretchFactor(0, int(top_stretch))
    split.setStretchFactor(1, int(bottom_stretch))
    if initial_sizes is not None:
        split.setSizes([int(s) for s in initial_sizes])
    else:
        # Prefer ~60/40 until the user drags
        split.setSizes([600, 400])
    return split


def make_h_splitter(
    left: QWidget,
    right: QWidget,
    left_stretch: int = 1,
    right_stretch: int = 1,
    initial_sizes: Optional[Sequence[int]] = None,
    left_min: int = 200,
    right_min: int = 200,
) -> QSplitter:
    """Horizontal splitter for side-by-side plots."""
    split = QSplitter(Qt.Horizontal)
    split.setChildrenCollapsible(False)
    split.setHandleWidth(6)
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
    """Vertical chart-top / table-bottom section with stretch ~3:2."""

    def __init__(
        self,
        chart_widget: QWidget,
        table_widget: QWidget,
        chart_title: str = "Chart",
        table_title: str = "Table",
        parent: Optional[QWidget] = None,
        top_stretch: int = 3,
        bottom_stretch: int = 2,
        initial_sizes: Optional[Sequence[int]] = None,
    ):
        super().__init__(parent=parent)
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
            initial_sizes=initial_sizes,
            top_min=PLOT_MIN_H,
            bottom_min=TABLE_MIN_H,
        )
        root.addWidget(self.splitter, 1)
