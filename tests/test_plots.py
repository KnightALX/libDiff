"""Offscreen PlotCanvas smoke tests (matplotlib Agg, no display)."""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from libdiff.gui.plots import PlotCanvas, _apply_theme, save_figure


def test_plot_theme_and_draws(tmp_path):
    _apply_theme()
    canvas = PlotCanvas()
    canvas.draw_empty("muted empty")
    canvas.draw_bar(["a", "b", "c"], [1.0, None, 3.5], title="bars", ylabel="v")
    canvas.draw_heatmap(
        [[0.1, -0.2], [None, 0.0]],
        xlabels=["x0", "x1"],
        ylabels=["y0", "y1"],
        title="delta",
        cbar_label="delta",
    )
    canvas.draw_lut_heatmap([[0.1, 0.2], [0.3, 0.4]], index_1=[1, 2], index_2=[3, 4], title="lut")
    canvas.draw_delay_curves(
        [0.01, 0.1, 1.0],
        {"left": [0.1, 0.2, None], "right": [0.12, 0.22, 0.3]},
        title="curves",
    )
    out = tmp_path / "plot.png"
    save_figure(canvas.figure, str(out))
    assert out.exists() and out.stat().st_size > 0
