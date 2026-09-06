"""Matplotlib PPA charts (no Qt / Plotly). Used by HTML report and GUI."""

from __future__ import annotations

import base64
import io
from typing import Any, Dict, List, Optional, Sequence, Tuple

from matplotlib.figure import Figure

# Keep theme soft without importing GUI (avoids Fluent/Qt on CLI paths)
_CB = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442", "#000000"]
_THEME = False


def _theme() -> None:
    global _THEME
    if _THEME:
        return
    import matplotlib as mpl

    mpl.rcParams.update(
        {
            "figure.facecolor": "#F7F8FA",
            "axes.facecolor": "#FFFFFF",
            "axes.edgecolor": "#B0B7C3",
            "axes.labelcolor": "#2B2F36",
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "grid.color": "#D0D5DD",
            "grid.linestyle": "--",
            "grid.linewidth": 0.6,
            "grid.alpha": 0.45,
            "legend.fontsize": 8,
            "font.size": 9,
            "savefig.facecolor": "#F7F8FA",
        }
    )
    _THEME = True


def figure_to_png_base64(fig: Figure, *, dpi: int = 100) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def _cleanup(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors="#4A5568", labelsize=8)
    ax.yaxis.grid(True, alpha=0.45)
    ax.set_axisbelow(True)


def figure_area_series_bars(
    report: Dict[str, Any],
    metric: str = "area",
    family: Optional[str] = None,
    fig: Optional[Figure] = None,
) -> Optional[Figure]:
    """Grouped bars: baseline vs right Area (or Leakage) across drive family.

    If family is None, pick the first non-_other series with members; else all cells.
    """
    _theme()
    series = report.get("series") or {}
    members: List[dict] = []
    title_fam = family
    if family and family in series and series[family].get("members"):
        members = list(series[family]["members"])
    else:
        for fam, payload in series.items():
            if fam == "_other":
                continue
            if payload.get("members"):
                members = list(payload["members"])
                title_fam = fam
                break
    if not members:
        # fall back: flat cells sorted by name
        cells = report.get("cells") or {}
        for name in sorted(cells.keys()):
            members.append(
                {
                    "drive": cells[name].get("drive"),
                    "cell": name,
                    metric: cells[name].get(metric),
                }
            )
    if not members:
        return None

    labels = [m.get("cell") or ("X%s" % m.get("drive")) for m in members]
    left_vals: List[Optional[float]] = []
    right_vals: List[Optional[float]] = []
    for m in members:
        d = m.get(metric) or {}
        left_vals.append(d.get("left"))
        right_vals.append(d.get("right"))

    if fig is None:
        fig = Figure(figsize=(6.2, 3.4), tight_layout=True)
    else:
        fig.clear()
    ax = fig.add_subplot(111)
    import numpy as np

    x = np.arange(len(labels))
    width = 0.36
    l_y = [0.0 if v is None else float(v) for v in left_vals]
    r_y = [0.0 if v is None else float(v) for v in right_vals]
    # hatch for missing
    bars_l = ax.bar(
        x - width / 2,
        l_y,
        width,
        label="baseline",
        color=_CB[0],
        edgecolor="#2B2F36",
        linewidth=0.4,
        alpha=0.92,
    )
    bars_r = ax.bar(
        x + width / 2,
        r_y,
        width,
        label="compare",
        color=_CB[1],
        edgecolor="#2B2F36",
        linewidth=0.4,
        alpha=0.92,
    )
    for i, v in enumerate(left_vals):
        if v is None:
            bars_l[i].set_hatch("///")
            bars_l[i].set_facecolor("none")
            bars_l[i].set_edgecolor("#9CA3AF")
    for i, v in enumerate(right_vals):
        if v is None:
            bars_r[i].set_hatch("///")
            bars_r[i].set_facecolor("none")
            bars_r[i].set_edgecolor("#9CA3AF")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ylab = "Area" if metric == "area" else ("Leakage" if metric == "leakage" else metric)
    ax.set_ylabel(ylab)
    ttl = "%s across drive family" % ylab
    if title_fam and title_fam != "_other":
        ttl = "%s — family %s" % (ttl, title_fam)
    ax.set_title(ttl)
    ax.legend(loc="best", frameon=True)
    _cleanup(ax)
    return fig


def _delay_row_vs_load(cell_view, table_type: str = "cell_rise", slew_index: Optional[int] = None):
    """Return (load_index, values_row, slew_used) for overlay charts."""
    from libdiff.compare.ppa import mid_index

    for t in cell_view.timing_tables():
        if t.get("table_type") != table_type:
            continue
        values = t.get("values") or []
        if not values:
            continue
        idx2 = t.get("index_2") or list(range(len(values[0])))
        si = mid_index(len(values)) if slew_index is None else slew_index
        si = max(0, min(si, len(values) - 1))
        row = list(values[si])
        while len(row) < len(idx2):
            row.append(None)
        return list(idx2), row[: len(idx2)], si
    return None, None, None


def figure_delay_load_overlay(
    report: Dict[str, Any],
    *,
    cells: Optional[Sequence[str]] = None,
    show_pct: bool = True,
    table_type: str = "cell_rise",
    fig: Optional[Figure] = None,
) -> Optional[Figure]:
    """Overlay delay vs load for multi-drive (or left/right) at mid slew.

    Loads libraries from report paths. Picks up to 4 cells from the largest family
    when cells is None.
    """
    _theme()
    left_path = report.get("left")
    right_path = report.get("right")
    if not left_path or not right_path:
        return None
    try:
        from libdiff.model.library import load_library

        left_lib = load_library(left_path)
        right_lib = load_library(right_path)
    except Exception:
        return None

    pick: List[str] = list(cells) if cells else []
    if not pick:
        series = report.get("series") or {}
        best = []
        for fam, payload in series.items():
            if fam == "_other":
                continue
            mem = payload.get("members") or []
            if len(mem) > len(best):
                best = [m["cell"] for m in mem]
        pick = best[:4] or sorted((report.get("cells") or {}).keys())[:3]
    if not pick:
        return None

    if fig is None:
        fig = Figure(figsize=(6.4, 3.6), tight_layout=True)
    else:
        fig.clear()
    ax = fig.add_subplot(111)
    drew = 0
    for i, name in enumerate(pick):
        if name not in left_lib.cell_names() or name not in right_lib.cell_names():
            continue
        idx, row_l, si = _delay_row_vs_load(left_lib.cell(name), table_type=table_type)
        _, row_r, _ = _delay_row_vs_load(right_lib.cell(name), table_type=table_type)
        if not idx or row_l is None or row_r is None:
            continue
        xs = [float(x) for x in idx]
        yl = [None if v is None else float(v) for v in row_l]
        yr = [None if v is None else float(v) for v in row_r]
        color = _CB[i % len(_CB)]
        ax.plot(
            xs,
            [v if v is not None else float("nan") for v in yl],
            marker="o",
            linewidth=1.6,
            markersize=4,
            color=color,
            linestyle="-",
            label="%s baseline" % name,
        )
        ax.plot(
            xs,
            [v if v is not None else float("nan") for v in yr],
            marker="s",
            linewidth=1.6,
            markersize=4,
            color=color,
            linestyle="--",
            label="%s compare" % name,
        )
        drew += 1
        if show_pct and drew == 1:
            # annotate %Δ at mid load for first series
            from libdiff.compare.ppa import mid_index

            mi = mid_index(len(xs))
            if yl[mi] is not None and yr[mi] is not None and yl[mi] != 0:
                pct = 100.0 * (yr[mi] - yl[mi]) / yl[mi]
                ax.annotate(
                    "%+.1f%%" % pct,
                    xy=(xs[mi], yr[mi]),
                    xytext=(6, 8),
                    textcoords="offset points",
                    fontsize=8,
                    color=color,
                )

    if not drew:
        ax.text(0.5, 0.5, "No delay LUT data", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
        return fig

    ax.set_title("Delay vs load (mid slew, %s)" % table_type)
    ax.set_xlabel("load (index_2)")
    ax.set_ylabel("delay")
    ax.legend(loc="best", frameon=True, fontsize=7)
    _cleanup(ax)
    return fig


def figure_ppa_radar(report: Dict[str, Any], fig: Optional[Figure] = None) -> Optional[Figure]:
    """Compact multi-axis summary: baseline=1.0 vs mean right/left ratios for A/L/D.

    Uses mean of per-cell (right/left) when both present; missing metrics omitted.
    """
    _theme()
    cells = report.get("cells") or {}
    if not cells:
        return None

    def mean_ratio(metric: str) -> Optional[float]:
        rs = []
        for c in cells.values():
            m = c.get(metric) or {}
            left, right = m.get("left"), m.get("right")
            if left is None or right is None or left == 0:
                continue
            rs.append(right / left)
        return (sum(rs) / len(rs)) if rs else None

    axes_labels = []
    baseline = []
    compare = []
    for label, key in (("Area", "area"), ("Leakage", "leakage"), ("Delay", "delay")):
        r = mean_ratio(key)
        if r is None:
            continue
        axes_labels.append(label)
        baseline.append(1.0)
        compare.append(float(r))
    if len(axes_labels) < 2:
        # still draw if only one metric — pad with dummy
        if len(axes_labels) == 1:
            axes_labels.append("(n/a)")
            baseline.append(1.0)
            compare.append(1.0)
        else:
            return None

    import numpy as np

    n = len(axes_labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]
    b = baseline + baseline[:1]
    c = compare + compare[:1]

    if fig is None:
        fig = Figure(figsize=(4.2, 4.0), tight_layout=True)
    else:
        fig.clear()
    ax = fig.add_subplot(111, polar=True)
    ax.plot(angles, b, "o-", linewidth=1.6, color=_CB[0], label="baseline")
    ax.fill(angles, b, color=_CB[0], alpha=0.08)
    ax.plot(angles, c, "s-", linewidth=1.6, color=_CB[1], label="compare / baseline")
    ax.fill(angles, c, color=_CB[1], alpha=0.12)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(axes_labels)
    ax.set_title("PPA radar (ratio vs baseline)", pad=16)
    ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.1), fontsize=7)
    return fig


__all__ = [
    "figure_area_series_bars",
    "figure_delay_load_overlay",
    "figure_ppa_radar",
    "figure_to_png_base64",
]
