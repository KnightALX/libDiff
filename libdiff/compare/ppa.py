"""Standard-cell PPA compare: Area / Leakage / typical Delay vs baseline.

Phase A focuses on stdcell library review quality (baseline-normalized KPIs,
abs Δ and %Δ, series-aware grouping). SRAM mode is stubbed for a later phase.
"""

from __future__ import annotations

import csv
import io
import json
import os
from typing import Any, Dict, List, Optional, Sequence, Union

from libdiff.model.library import CellView, Library, load_library
from libdiff.series import DEFAULT_SERIES_PATTERNS, group_cells_by_series, match_cell_series

# Unit notes for report cover / KPI cards (library units still authoritative)
PPA_UNIT_NOTES = {
    "area": "Library area attribute (typically um^2); not normalized to gate equivalents.",
    "leakage": "Sum of leakage_power() values when present; else cell_leakage_power if exposed.",
    "delay": (
        "Typical delay = mid-slew / mid-load sample from the first cell_rise NLDM LUT "
        "(fallback: cell_fall). Mid index = len//2."
    ),
}

DELAY_TABLE_PREFERENCE = ("cell_rise", "cell_fall")


def _delta(left: Optional[float], right: Optional[float]) -> Dict[str, Any]:
    """Baseline-normalized delta: abs = right-left, pct = 100*(right-left)/left."""
    if left is None or right is None:
        return {
            "left": left,
            "right": right,
            "abs": None,
            "pct": None,
            "rel": None,
            "status": "missing",
        }
    abs_d = right - left
    if left == 0:
        rel = None
        pct = None
    else:
        rel = abs_d / left
        pct = 100.0 * rel
    return {
        "left": left,
        "right": right,
        "abs": abs_d,
        "pct": pct,
        "rel": rel,
        "status": "ok",
    }


def mid_index(n: int) -> int:
    """Mid sample index for length n (0 if empty)."""
    if n <= 0:
        return 0
    return n // 2


def lut_mid_sample(values: Sequence[Sequence[Optional[float]]]) -> Optional[float]:
    """Pick mid-row / mid-col LUT sample; None if missing."""
    if not values:
        return None
    ri = mid_index(len(values))
    row = values[ri] if ri < len(values) else None
    if not row:
        return None
    ci = mid_index(len(row))
    if ci >= len(row):
        return None
    v = row[ci]
    return None if v is None else float(v)


def typical_delay(cell: CellView, table_types: Sequence[str] = DELAY_TABLE_PREFERENCE) -> Optional[float]:
    """Typical delay from mid-slew/mid-load of preferred NLDM delay tables."""
    tables = cell.timing_tables()
    by_type: Dict[str, List[dict]] = {}
    for t in tables:
        tt = t.get("table_type")
        if tt in table_types:
            by_type.setdefault(tt, []).append(t)
    for tt in table_types:
        for t in by_type.get(tt) or []:
            sample = lut_mid_sample(t.get("values") or [])
            if sample is not None:
                return sample
    return None


def cell_leakage_total(cell: CellView) -> Optional[float]:
    """Aggregate leakage: sum of leakage_power entries; skip None values."""
    entries = cell.leakage_entries()
    vals = [e["value"] for e in entries if e.get("value") is not None]
    if not vals:
        return None
    return float(sum(vals))


def cell_ppa_metrics(cell: CellView) -> Dict[str, Optional[float]]:
    return {
        "area": cell.area,
        "leakage": cell_leakage_total(cell),
        "delay": typical_delay(cell),
    }


def _empty_summary() -> Dict[str, Any]:
    return {
        "mode": "stdcell",
        "n_cells_compared": 0,
        "n_cells_left_only": 0,
        "n_cells_right_only": 0,
        "n_area_ok": 0,
        "n_leakage_ok": 0,
        "n_delay_ok": 0,
        "mean_area_pct": None,
        "mean_leakage_pct": None,
        "mean_delay_pct": None,
    }


def compare_ppa(
    left: Union[str, Library],
    right: Union[str, Library],
    cells: Optional[Sequence[str]] = None,
    cell_pattern: Optional[str] = None,
    mode: str = "stdcell",
    notes: str = "",
) -> Dict[str, Any]:
    """Compare PPA metrics (Area / Leakage / typical Delay) vs baseline (left).

    mode:
      - ``stdcell`` (default): full Phase A metrics + series grouping
      - ``sram``: stub only (empty cells, note that SRAM is later)
    """
    left_lib = left if isinstance(left, Library) else load_library(left)
    right_lib = right if isinstance(right, Library) else load_library(right)

    unit_notes = dict(PPA_UNIT_NOTES)
    unit_notes["left_units"] = left_lib.units()
    unit_notes["right_units"] = right_lib.units()

    if mode == "sram":
        return {
            "left": left_lib.key,
            "right": right_lib.key,
            "mode": "sram",
            "notes": notes
            or "SRAM PPA mode is planned for a later phase (stub only in Phase A).",
            "unit_notes": unit_notes,
            "cells": {},
            "series": {},
            "summary": {**_empty_summary(), "mode": "sram", "stub": True},
            "kpis": {
                "area_pct": None,
                "leakage_pct": None,
                "delay_pct": None,
            },
        }

    left_names = set(left_lib.cell_names())
    right_names = set(right_lib.cell_names())
    common = sorted(left_names & right_names)
    only_left = sorted(left_names - right_names)
    only_right = sorted(right_names - left_names)

    if cell_pattern:
        common = sorted(
            set(left_lib.select_cells(cell_pattern)) & set(right_lib.select_cells(cell_pattern))
        )
    if cells:
        wanted = set(cells)
        common = [c for c in common if c in wanted]

    cell_reports: Dict[str, Any] = {}
    area_pcts: List[float] = []
    leak_pcts: List[float] = []
    delay_pcts: List[float] = []
    n_area = n_leak = n_delay = 0

    for name in common:
        lc = left_lib.cell(name)
        rc = right_lib.cell(name)
        lm = cell_ppa_metrics(lc)
        rm = cell_ppa_metrics(rc)
        area_d = _delta(lm["area"], rm["area"])
        leak_d = _delta(lm["leakage"], rm["leakage"])
        delay_d = _delta(lm["delay"], rm["delay"])
        series_hit = match_cell_series(name)
        entry = {
            "name": name,
            "series_family": series_hit[0] if series_hit else None,
            "drive": series_hit[1] if series_hit else None,
            "area": area_d,
            "leakage": leak_d,
            "delay": delay_d,
            "status": "ok",
        }
        cell_reports[name] = entry
        if area_d["status"] == "ok":
            n_area += 1
            if area_d["pct"] is not None:
                area_pcts.append(area_d["pct"])
        if leak_d["status"] == "ok":
            n_leak += 1
            if leak_d["pct"] is not None:
                leak_pcts.append(leak_d["pct"])
        if delay_d["status"] == "ok":
            n_delay += 1
            if delay_d["pct"] is not None:
                delay_pcts.append(delay_d["pct"])

    grouped = group_cells_by_series(common)
    series_payload: Dict[str, Any] = {}
    for fam, items in grouped.items():
        if fam == "_other":
            series_payload[fam] = {"cells": items}
            continue
        members = []
        for size, cname in items:
            if cname in cell_reports:
                members.append(
                    {
                        "drive": size,
                        "cell": cname,
                        "area": cell_reports[cname]["area"],
                        "leakage": cell_reports[cname]["leakage"],
                        "delay": cell_reports[cname]["delay"],
                    }
                )
        series_payload[fam] = {"members": members}

    def _mean(xs: List[float]) -> Optional[float]:
        return (sum(xs) / len(xs)) if xs else None

    summary = {
        "mode": "stdcell",
        "n_cells_compared": len(common),
        "n_cells_left_only": len(only_left),
        "n_cells_right_only": len(only_right),
        "n_area_ok": n_area,
        "n_leakage_ok": n_leak,
        "n_delay_ok": n_delay,
        "mean_area_pct": _mean(area_pcts),
        "mean_leakage_pct": _mean(leak_pcts),
        "mean_delay_pct": _mean(delay_pcts),
    }
    kpis = {
        "area_pct": summary["mean_area_pct"],
        "leakage_pct": summary["mean_leakage_pct"],
        "delay_pct": summary["mean_delay_pct"],
    }

    return {
        "left": left_lib.key,
        "right": right_lib.key,
        "mode": "stdcell",
        "notes": notes,
        "unit_notes": unit_notes,
        "cells": cell_reports,
        "series": series_payload,
        "cells_left_only": only_left,
        "cells_right_only": only_right,
        "summary": summary,
        "kpis": kpis,
    }


def format_ppa_summary(report: Dict[str, Any]) -> str:
    s = report.get("summary") or {}
    lines = [
        "PPA compare (stdcell Phase A)",
        "left (baseline): %s" % report.get("left"),
        "right           : %s" % report.get("right"),
        "mode            : %s" % (report.get("mode") or s.get("mode")),
        "cells compared  : %s" % s.get("n_cells_compared"),
        "mean Area %%Δ    : %s" % _fmt_pct(s.get("mean_area_pct")),
        "mean Leakage %%Δ : %s" % _fmt_pct(s.get("mean_leakage_pct")),
        "mean Delay %%Δ   : %s" % _fmt_pct(s.get("mean_delay_pct")),
        "ok counts A/L/D : %s / %s / %s"
        % (s.get("n_area_ok"), s.get("n_leakage_ok"), s.get("n_delay_ok")),
    ]
    if report.get("mode") == "sram" or s.get("stub"):
        lines.append("note: SRAM mode stub — full SRAM PPA is a later phase.")
    if report.get("notes"):
        lines.append("notes: %s" % report.get("notes"))
    return "\n".join(lines)


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "N/A"
    return "%+.3f%%" % v


def export_ppa_json(report: Dict[str, Any], path: Optional[str] = None, indent: int = 2) -> str:
    text = json.dumps(report, indent=indent, default=str)
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return text


def export_ppa_csv(report: Dict[str, Any], path: Optional[str] = None) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "cell",
            "series_family",
            "drive",
            "metric",
            "left",
            "right",
            "abs_delta",
            "pct_delta",
            "status",
        ]
    )
    for name, cell in (report.get("cells") or {}).items():
        for metric in ("area", "leakage", "delay"):
            m = cell.get(metric) or {}
            writer.writerow(
                [
                    name,
                    cell.get("series_family") or "",
                    cell.get("drive") if cell.get("drive") is not None else "",
                    metric,
                    m.get("left"),
                    m.get("right"),
                    m.get("abs"),
                    m.get("pct"),
                    m.get("status"),
                ]
            )
    text = buf.getvalue()
    if path:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    return text


def _html_escape(s: Any) -> str:
    t = "" if s is None else str(s)
    return (
        t.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def export_ppa_html(
    report: Dict[str, Any],
    path: Optional[str] = None,
    embed_plots: bool = True,
) -> str:
    """One-page review-grade PPA HTML: cover, KPI cards, PNGs, baseline/%Δ table."""
    s = report.get("summary") or {}
    kpis = report.get("kpis") or {}
    unit_notes = report.get("unit_notes") or {}

    plot_blocks: List[str] = []
    if embed_plots and report.get("mode") != "sram":
        try:
            from libdiff.plotting.ppa_charts import (
                figure_area_series_bars,
                figure_delay_load_overlay,
                figure_ppa_radar,
                figure_to_png_base64,
            )
            from matplotlib import pyplot as plt

            figs = []
            figs.append(("Area by drive family", figure_area_series_bars(report, metric="area")))
            figs.append(("Leakage by drive family", figure_area_series_bars(report, metric="leakage")))
            figs.append(("Delay vs load overlay", figure_delay_load_overlay(report)))
            figs.append(("PPA radar vs baseline", figure_ppa_radar(report)))
            for title, fig in figs:
                if fig is None:
                    continue
                b64 = figure_to_png_base64(fig, dpi=110)
                try:
                    plt.close(fig)
                except Exception:
                    pass
                if b64:
                    plot_blocks.append(
                        '<div class="plot"><h3>%s</h3>'
                        '<img alt="%s" src="data:image/png;base64,%s"/></div>'
                        % (_html_escape(title), _html_escape(title), b64)
                    )
        except Exception:
            plot_blocks.append(
                "<p class='muted'>Plots unavailable (matplotlib error); table still below.</p>"
            )

    # KPI cards
    def card(label: str, value: Any, hint: str = "") -> str:
        return (
            "<div class='card'><div class='n'>%s</div><div class='l'>%s</div>"
            "%s</div>"
            % (
                _html_escape(value),
                _html_escape(label),
                ("<div class='h'>%s</div>" % _html_escape(hint)) if hint else "",
            )
        )

    cards = [
        card("Cells", s.get("n_cells_compared")),
        card("Mean Area %Δ", _fmt_pct(kpis.get("area_pct")), "vs baseline"),
        card("Mean Leakage %Δ", _fmt_pct(kpis.get("leakage_pct")), "vs baseline"),
        card("Mean Delay %Δ", _fmt_pct(kpis.get("delay_pct")), "mid LUT sample"),
    ]

    # Table rows
    rows_html = [
        "<table><thead><tr>",
        "<th>Cell</th><th>Family</th><th>Drive</th>",
        "<th>Area L</th><th>Area R</th><th>Area abs</th><th>Area %</th>",
        "<th>Leak L</th><th>Leak R</th><th>Leak %</th>",
        "<th>Delay L</th><th>Delay R</th><th>Delay %</th>",
        "</tr></thead><tbody>",
    ]
    for name in sorted((report.get("cells") or {}).keys()):
        c = report["cells"][name]
        a, lk, d = c.get("area") or {}, c.get("leakage") or {}, c.get("delay") or {}

        def f(v, pct=False):
            if v is None:
                return "N/A"
            return ("%.4g" % v) if not pct else ("%+.3f%%" % v)

        rows_html.append("<tr>")
        for val in (
            name,
            c.get("series_family") or "",
            "" if c.get("drive") is None else c.get("drive"),
            f(a.get("left")),
            f(a.get("right")),
            f(a.get("abs")),
            f(a.get("pct"), pct=True) if a.get("pct") is not None else "N/A",
            f(lk.get("left")),
            f(lk.get("right")),
            f(lk.get("pct"), pct=True) if lk.get("pct") is not None else "N/A",
            f(d.get("left")),
            f(d.get("right")),
            f(d.get("pct"), pct=True) if d.get("pct") is not None else "N/A",
        ):
            rows_html.append("<td>%s</td>" % _html_escape(val))
        rows_html.append("</tr>")
    rows_html.append("</tbody></table>")

    css = (
        "body{font-family:Segoe UI,Helvetica,Arial,sans-serif;margin:24px;color:#1f2937;background:#f8fafc}"
        "h1{font-size:1.45rem;margin:0 0 8px}"
        "h2{font-size:1.1rem;margin:28px 0 10px;border-bottom:1px solid #e5e7eb;padding-bottom:4px}"
        ".meta{color:#4b5563;font-size:0.9rem;margin-bottom:16px;line-height:1.45}"
        ".cards{display:flex;flex-wrap:wrap;gap:12px;margin:12px 0 20px}"
        ".card{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;min-width:130px}"
        ".card .n{font-size:1.25rem;font-weight:600}"
        ".card .l{font-size:0.72rem;color:#6b7280;text-transform:uppercase}"
        ".card .h{font-size:0.7rem;color:#9ca3af;margin-top:2px}"
        "table{border-collapse:collapse;width:100%;background:#fff;font-size:0.8rem}"
        "th,td{border:1px solid #e5e7eb;padding:5px 7px;text-align:left}"
        "th{background:#f3f4f6}"
        ".muted{color:#6b7280}"
        ".plot{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:12px;margin:12px 0}"
        ".plot img{max-width:100%;height:auto}"
        ".notes{background:#fff;border-left:3px solid #0072B2;padding:10px 14px;margin:12px 0}"
    )

    left_u = unit_notes.get("left_units") or {}
    html = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'/>",
        "<title>libDiff PPA Report</title>",
        "<style>%s</style></head><body>" % css,
        "<h1>libDiff PPA Report — Standard Cell</h1>",
        (
            "<div class='meta'><strong>Baseline (left):</strong> %s<br/>"
            "<strong>Compare (right):</strong> %s<br/>"
            "mode: %s &nbsp;|&nbsp; time_unit L/R: %s / %s &nbsp;|&nbsp; "
            "leakage_power_unit L/R: %s / %s</div>"
            % (
                _html_escape(report.get("left")),
                _html_escape(report.get("right")),
                _html_escape(report.get("mode")),
                _html_escape(left_u.get("time_unit")),
                _html_escape((unit_notes.get("right_units") or {}).get("time_unit")),
                _html_escape(left_u.get("leakage_power_unit")),
                _html_escape((unit_notes.get("right_units") or {}).get("leakage_power_unit")),
            )
        ),
        "<div class='notes'><strong>Metric notes</strong><ul>",
        "<li>%s</li>" % _html_escape(unit_notes.get("area")),
        "<li>%s</li>" % _html_escape(unit_notes.get("leakage")),
        "<li>%s</li>" % _html_escape(unit_notes.get("delay")),
        "</ul>",
    ]
    if report.get("notes"):
        html.append("<p>%s</p>" % _html_escape(report.get("notes")))
    html.append("</div>")
    html.append("<div class='cards'>")
    html.extend(cards)
    html.append("</div>")
    if plot_blocks:
        html.append("<h2>Charts</h2>")
        html.extend(plot_blocks)
    html.append("<h2>Baseline / %Δ table</h2>")
    html.extend(rows_html)
    html.append(
        "<p class='muted'>Generated by libDiff PPA (Phase A stdcell). "
        "SRAM mode is stub-only for a later phase. GPL-2.0.</p>"
    )
    html.append("</body></html>")
    text = "\n".join(html)
    if path:
        parent = os.path.dirname(os.path.abspath(path))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return text


__all__ = [
    "PPA_UNIT_NOTES",
    "compare_ppa",
    "typical_delay",
    "cell_leakage_total",
    "cell_ppa_metrics",
    "lut_mid_sample",
    "mid_index",
    "export_ppa_json",
    "export_ppa_csv",
    "export_ppa_html",
    "format_ppa_summary",
    "DEFAULT_SERIES_PATTERNS",
]
