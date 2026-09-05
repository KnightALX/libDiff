"""Plotting helpers for libDiff (matplotlib only; no Plotly).

GUI PlotCanvas lives in libdiff.gui.plots; PPA chart builders are Qt-free so
CLI HTML export does not require PyQt / Fluent.
"""

from libdiff.plotting.ppa_charts import (
    figure_area_series_bars,
    figure_delay_load_overlay,
    figure_ppa_radar,
    figure_to_png_base64,
)

__all__ = [
    "figure_area_series_bars",
    "figure_delay_load_overlay",
    "figure_ppa_radar",
    "figure_to_png_base64",
]

# Optional re-export of GUI helpers when Qt stack is present
try:
    from libdiff.gui.plots import PlotCanvas, _apply_theme, save_figure  # noqa: F401

    __all__ += ["PlotCanvas", "_apply_theme", "save_figure"]
except Exception:
    pass
