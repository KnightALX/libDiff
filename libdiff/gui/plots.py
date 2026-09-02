"""Matplotlib canvas helpers for libDiff GUI."""

from __future__ import annotations

import io
from typing import Any, Dict, List, Optional, Sequence, Union

import matplotlib as mpl
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib import colors as mcolors

# Colorblind-friendly qualitative palette (Okabe-Ito inspired)
_CB_COLORS = [
    "#0072B2",  # blue
    "#E69F00",  # orange
    "#009E73",  # bluish green
    "#CC79A7",  # reddish purple
    "#56B4E9",  # sky blue
    "#D55E00",  # vermillion
    "#F0E442",  # yellow
    "#000000",  # black
]

_THEME_APPLIED = False


def _apply_theme() -> None:
    """Apply a unified soft theme once via matplotlib.rcParams."""
    global _THEME_APPLIED
    if _THEME_APPLIED:
        return
    mpl.rcParams.update(
        {
            "figure.facecolor": "#F7F8FA",
            "axes.facecolor": "#FFFFFF",
            "axes.edgecolor": "#B0B7C3",
            "axes.labelcolor": "#2B2F36",
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "axes.titleweight": "medium",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.color": "#4A5568",
            "ytick.color": "#4A5568",
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "grid.color": "#D0D5DD",
            "grid.linestyle": "--",
            "grid.linewidth": 0.6,
            "grid.alpha": 0.45,
            "legend.fontsize": 8,
            "legend.framealpha": 0.92,
            "font.size": 9,
            "font.family": "sans-serif",
            "savefig.facecolor": "#F7F8FA",
            "savefig.dpi": 120,
            "image.cmap": "viridis",
        }
    )
    _THEME_APPLIED = True


def save_figure(fig: Figure, path: str, *, dpi: int = 120, transparent: bool = False) -> str:
    """Save a matplotlib Figure to PNG or SVG (by extension). Returns path."""
    _apply_theme()
    fig.savefig(path, dpi=dpi, transparent=transparent, bbox_inches="tight")
    return path


def figure_to_png_base64(fig: Figure, *, dpi: int = 100) -> str:
    """Encode a figure as a base64 PNG string (no data: prefix)."""
    import base64

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


class PlotCanvas(FigureCanvasQTAgg):
    def __init__(self, parent=None):
        _apply_theme()
        self.figure = Figure(tight_layout=True)
        super().__init__(self.figure)
        if parent is not None:
            self.setParent(parent)
        self._style_axes_defaults()

    def _style_axes_defaults(self) -> None:
        self.figure.patch.set_facecolor("#F7F8FA")
        self.figure.patch.set_alpha(1.0)

    def _cleanup_spines(self, ax) -> None:
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#B0B7C3")
        ax.tick_params(colors="#4A5568", labelsize=8)

    def _finish(self, ax=None) -> None:
        try:
            self.figure.tight_layout()
        except Exception:
            pass
        self.draw()

    def save_figure(self, path: str, **kwargs) -> str:
        """Save this canvas figure to PNG/SVG."""
        return save_figure(self.figure, path, **kwargs)

    def draw_empty(self, text: str = "No data"):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.text(
            0.5,
            0.5,
            text,
            ha="center",
            va="center",
            fontsize=12,
            color="#6B7280",
            alpha=0.85,
            transform=ax.transAxes,
        )
        ax.set_axis_off()
        self._finish(ax)

    def draw_bar(
        self,
        labels: Sequence[str],
        values: Sequence[Optional[float]],
        title: str = "",
        ylabel: str = "",
        annotate: bool = True,
    ):
        """Bar chart: None values are skipped/annotated as missing, not plotted as zero."""
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        xs: List[int] = []
        ys: List[float] = []
        tick_labels: List[str] = []
        gap_x: List[int] = []
        for i, (lab, v) in enumerate(zip(labels, values)):
            tick_labels.append(str(lab))
            if v is None:
                gap_x.append(i)
                continue
            xs.append(i)
            ys.append(float(v))

        bar_colors = [_CB_COLORS[i % len(_CB_COLORS)] for i in range(len(xs))]
        if xs:
            bars = ax.bar(
                xs,
                ys,
                color=bar_colors,
                edgecolor="#2B2F36",
                linewidth=0.5,
                alpha=0.92,
            )
            if annotate:
                for rect, val in zip(bars, ys):
                    ax.annotate(
                        ("%.4g" % val),
                        xy=(rect.get_x() + rect.get_width() / 2, rect.get_height()),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha="center",
                        va="bottom",
                        fontsize=8,
                        color="#2B2F36",
                    )
        # Hatch markers for None gaps (height 0, not treated as numeric zero bar)
        for gx in gap_x:
            ax.bar(
                [gx],
                [0],
                color="none",
                edgecolor="#9CA3AF",
                hatch="///",
                linewidth=0.9,
                label="_gap",
            )
            ax.annotate(
                "N/A",
                xy=(gx, 0),
                xytext=(0, 6),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=7,
                color="#9CA3AF",
            )

        ax.set_xticks(range(len(tick_labels)))
        ax.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=8)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.yaxis.grid(True, alpha=0.45)
        ax.set_axisbelow(True)
        self._cleanup_spines(ax)
        if not xs and not gap_x:
            ax.text(
                0.5,
                0.5,
                "No data",
                ha="center",
                va="center",
                transform=ax.transAxes,
                color="#6B7280",
            )
        self._finish(ax)

    def draw_heatmap(
        self,
        matrix: Sequence[Sequence[Optional[float]]],
        xlabels: Optional[Sequence[Any]] = None,
        ylabels: Optional[Sequence[Any]] = None,
        title: str = "",
        cmap: str = "RdBu_r",
        center: Optional[float] = 0,
        colorbar: bool = True,
        xlabel: str = "",
        ylabel: str = "",
        cbar_label: str = "",
    ):
        """2D heatmap for delta / %%diff / value matrices. None -> NaN (gray)."""
        self.figure.clear()
        if not matrix:
            self.draw_empty("Empty matrix")
            return
        try:
            import numpy as np
        except ImportError:
            self.draw_empty("numpy required for heatmap")
            return

        rows = []
        for row in matrix:
            rows.append([(np.nan if c is None else float(c)) for c in row])
        arr = np.array(rows, dtype=float)
        if arr.size == 0:
            self.draw_empty("Empty matrix")
            return

        z = np.ma.masked_invalid(arr)
        ax = self.figure.add_subplot(111)

        # Gray for missing / NaN
        try:
            base_cmap = mpl.colormaps[cmap]
        except Exception:
            base_cmap = mpl.cm.get_cmap(cmap)
        cmap_obj = base_cmap.copy() if hasattr(base_cmap, "copy") else mpl.cm.get_cmap(cmap)
        try:
            cmap_obj.set_bad(color="#D1D5DB")
        except Exception:
            pass

        if center is not None and z.count():
            vmax = float(np.nanmax(np.abs(arr))) if np.isfinite(np.nanmax(np.abs(arr))) else 1.0
            if vmax == 0:
                vmax = 1.0
            norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=float(center), vmax=vmax)
            im = ax.imshow(z, aspect="auto", cmap=cmap_obj, norm=norm, interpolation="nearest")
            default_cbar = cbar_label or "\\u0394"
        else:
            im = ax.imshow(
                z,
                aspect="auto",
                cmap=cmap_obj if cmap else "viridis",
                interpolation="nearest",
            )
            default_cbar = cbar_label or "value"

        max_ticks = 24
        if xlabels is not None and len(xlabels) == z.shape[1] and z.shape[1] <= max_ticks:
            ax.set_xticks(range(z.shape[1]))
            ax.set_xticklabels([str(x) for x in xlabels], rotation=45, ha="right", fontsize=7)
        elif z.shape[1] > max_ticks:
            ax.set_xticks([])
        if ylabels is not None and len(ylabels) == z.shape[0] and z.shape[0] <= max_ticks:
            ax.set_yticks(range(z.shape[0]))
            ax.set_yticklabels([str(y) for y in ylabels], fontsize=7)
        elif z.shape[0] > max_ticks:
            ax.set_yticks([])

        ax.set_title(title)
        if xlabel:
            ax.set_xlabel(xlabel)
        if ylabel:
            ax.set_ylabel(ylabel)
        if colorbar:
            cbar = self.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label(default_cbar, fontsize=8)
            cbar.ax.tick_params(labelsize=7)
        self._cleanup_spines(ax)
        self._finish(ax)

    def draw_lut_heatmap(
        self,
        values: Sequence[Sequence[Optional[float]]],
        index_1: Optional[Sequence[Any]] = None,
        index_2: Optional[Sequence[Any]] = None,
        title: str = "",
        cmap: str = "viridis",
    ):
        """Heatmap of a raw NLDM LUT (sequential, not diverging)."""
        self.draw_heatmap(
            values,
            xlabels=index_2,
            ylabels=index_1,
            title=title,
            cmap=cmap,
            center=None,
            colorbar=True,
            xlabel="index_2",
            ylabel="index_1",
            cbar_label="value",
        )

    def draw_delay_curves(
        self,
        index_vals: Sequence[float],
        series_dict: Dict[str, Sequence[Optional[float]]],
        title: str = "",
        xlabel: str = "load / index",
        ylabel: str = "delay",
    ):
        """Overlay delay (or transition) curves vs one axis (e.g. load at fixed slew)."""
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        if not index_vals or not series_dict:
            self.draw_empty("No curves")
            return
        for i, (name, ys) in enumerate(series_dict.items()):
            xs: List[float] = []
            vs: List[float] = []
            for x, y in zip(index_vals, ys):
                if y is None:
                    continue
                xs.append(float(x))
                vs.append(float(y))
            if not xs:
                continue
            ax.plot(
                xs,
                vs,
                marker="o",
                linewidth=1.8,
                markersize=5,
                label=str(name),
                color=_CB_COLORS[i % len(_CB_COLORS)],
            )
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.45)
        ax.set_axisbelow(True)
        ax.legend(loc="best", frameon=True)
        self._cleanup_spines(ax)
        self._finish(ax)

    def draw_lut_surface(self, index_1, index_2, values, title: str = ""):
        """Prefer 2D heatmap; optional 3D only for tiny grids (<= 6x6)."""
        self.figure.clear()
        if not values:
            self.draw_empty("Empty LUT")
            return
        nrows = len(values)
        ncols = max((len(r) for r in values), default=0)
        # Prefer heatmap for readability; keep small-grid 3D as optional
        if nrows > 6 or ncols > 6:
            self.draw_lut_heatmap(values, index_1=index_1, index_2=index_2, title=title)
            return
        try:
            from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
            import numpy as np

            ax = self.figure.add_subplot(111, projection="3d")
            z = np.array(
                [[(np.nan if c is None else float(c)) for c in row] for row in values],
                dtype=float,
            )
            x = np.arange(z.shape[1])
            y = np.arange(z.shape[0])
            X, Y = np.meshgrid(x, y)
            ax.plot_surface(X, Y, np.nan_to_num(z, nan=0.0), cmap="viridis", alpha=0.92)
            ax.set_title(title, fontsize=11)
            self._finish(ax)
        except Exception:
            self.draw_lut_heatmap(values, index_1=index_1, index_2=index_2, title=title)


__all__ = [
    "PlotCanvas",
    "_apply_theme",
    "save_figure",
    "figure_to_png_base64",
]
