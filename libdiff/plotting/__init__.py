"""Optional plotting helpers (re-exports GUI PlotCanvas helpers for CLI/scripts)."""

from libdiff.gui.plots import (
    PlotCanvas,
    _apply_theme,
    save_figure,
    figure_to_png_base64,
)

__all__ = [
    "PlotCanvas",
    "_apply_theme",
    "save_figure",
    "figure_to_png_base64",
]
