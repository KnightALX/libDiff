"""Batch Timing QA + HTML/CSV report helpers."""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Optional, Sequence, Union

from libdiff.model.library import Library, load_library
from libdiff.compare.timing_qa import timing_qa


def run_timing_qa_batch(
    left: Union[str, Library],
    right: Union[str, Library],
    cells: Optional[Sequence[str]] = None,
    cell_pattern: Optional[str] = None,
    table_types: Optional[Sequence[str]] = None,
    abs_tol: float = 1e-4,
    rel_tol: float = 0.01,
    include_matrices: bool = False,
    top_n: int = 20,
) -> Dict[str, Any]:
    """Batch Timing QA over common cells (or filter); return library-level summary.

    Runs per-cell timing_qa and aggregates arcs / fails / missing / top offenders.
    cells may be exact names; cell_pattern is fnmatch (e.g. inv*).
    If both are None, all cells present on both libraries are compared.
    """
    left_lib = left if isinstance(left, Library) else load_library(left)
    right_lib = right if isinstance(right, Library) else load_library(right)

    left_names = set(left_lib.cell_names())
    right_names = set(right_lib.cell_names())
    common = sorted(left_names & right_names)
    only_left_cells = sorted(left_names - right_names)
    only_right_cells = sorted(right_names - left_names)

    if cell_pattern:
        common = sorted(
            set(left_lib.select_cells(cell_pattern)) & set(right_lib.select_cells(cell_pattern))
        )
    if cells:
        wanted = set(cells)
        common = [c for c in common if c in wanted]

    cell_reports = []
    all_arcs = []
    all_left_only = []
    all_right_only = []
    total_fail = 0
    total_matched = 0
    total_index_mismatch = 0

    for cell in common:
        rep = timing_qa(
            left_lib,
            right_lib,
            cells=[cell],
            cell_pattern=None,
            table_types=table_types,
            abs_tol=abs_tol,
            rel_tol=rel_tol,
            include_matrices=include_matrices,
            run_single_lib_qa=False,
        )
        s = rep.get("summary") or {}
        n_fail = int(s.get("n_fail") or 0)
        n_matched = int(s.get("n_arcs_matched") or 0)
        total_fail += n_fail
        total_matched += n_matched
        total_index_mismatch += int(s.get("n_index_mismatch") or 0)
        cell_reports.append(
            {
                "cell": cell,
                "n_arcs_matched": n_matched,
                "n_fail": n_fail,
                "n_left_only": s.get("n_left_only"),
                "n_right_only": s.get("n_right_only"),
                "n_index_mismatch": s.get("n_index_mismatch"),
            }
        )
        all_arcs.extend(rep.get("arcs") or [])
        all_left_only.extend(rep.get("left_only") or [])
        all_right_only.extend(rep.get("right_only") or [])

    cell_reports_sorted = sorted(
        cell_reports,
        key=lambda r: (-int(r.get("n_fail") or 0), r.get("cell") or ""),
    )
    fails = [a for a in all_arcs if a.get("exceeds_tol")]
    fails.sort(
        key=lambda a: (
            a.get("max_abs") is None,
            -(a.get("max_abs") or 0),
            a.get("max_rel") is None,
            -(a.get("max_rel") or 0),
        )
    )

    summary = {
        "mode": "batch",
        "n_cells_compared": len(common),
        "n_cells_left_only": len(only_left_cells),
        "n_cells_right_only": len(only_right_cells),
        "n_arcs_matched": total_matched,
        "n_fail": total_fail,
        "n_left_only": len(all_left_only),
        "n_right_only": len(all_right_only),
        "n_missing": len(all_left_only) + len(all_right_only),
        "n_index_mismatch": total_index_mismatch,
        "abs_tol": abs_tol,
        "rel_tol": rel_tol,
        "top_failing_cells": cell_reports_sorted[:top_n],
        "top_failing_arcs": [
            {
                "cell": a.get("cell"),
                "pin": a.get("pin"),
                "related_pin": a.get("related_pin"),
                "table_type": a.get("table_type"),
                "max_abs": a.get("max_abs"),
                "max_rel": a.get("max_rel"),
                "status": a.get("status"),
            }
            for a in fails[:top_n]
        ],
    }

    return {
        "left": left_lib.key,
        "right": right_lib.key,
        "summary": summary,
        "cells": cell_reports_sorted,
        "arcs": all_arcs,
        "left_only": all_left_only,
        "right_only": all_right_only,
        "cells_left_only": only_left_cells,
        "cells_right_only": only_right_cells,
    }


def export_timing_qa_batch_csv(report, path=None):
    """CSV with per-cell summary rows plus flat arc detail."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "row_kind",
            "status",
            "side",
            "cell",
            "pin",
            "related_pin",
            "timing_sense",
            "timing_type",
            "when",
            "table_type",
            "max_abs",
            "max_rel",
            "mean_abs",
            "rms",
            "n_mismatch",
            "n_compared",
            "index_alignment",
            "exceeds_tol",
            "n_arcs_matched",
            "n_fail",
            "n_left_only",
            "n_right_only",
        ]
    )
    for c in report.get("cells") or []:
        writer.writerow(
            [
                "cell_summary",
                "fail" if (c.get("n_fail") or 0) else "ok",
                "both",
                c.get("cell"),
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                c.get("n_arcs_matched"),
                c.get("n_fail"),
                c.get("n_left_only"),
                c.get("n_right_only"),
            ]
        )
    for a in report.get("arcs") or []:
        writer.writerow(
            [
                "arc",
                a.get("status"),
                "both",
                a.get("cell"),
                a.get("pin"),
                a.get("related_pin"),
                a.get("timing_sense"),
                a.get("timing_type"),
                a.get("when"),
                a.get("table_type"),
                a.get("max_abs"),
                a.get("max_rel"),
                a.get("mean_abs"),
                a.get("rms"),
                a.get("n_mismatch"),
                a.get("n_compared"),
                a.get("index_alignment"),
                a.get("exceeds_tol"),
                "",
                "",
                "",
                "",
            ]
        )
    for a in report.get("left_only") or []:
        writer.writerow(
            [
                "missing",
                "missing",
                "left_only",
                a.get("cell"),
                a.get("pin"),
                a.get("related_pin"),
                a.get("timing_sense"),
                a.get("timing_type"),
                a.get("when"),
                a.get("table_type"),
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )
    for a in report.get("right_only") or []:
        writer.writerow(
            [
                "missing",
                "missing",
                "right_only",
                a.get("cell"),
                a.get("pin"),
                a.get("related_pin"),
                a.get("timing_sense"),
                a.get("timing_type"),
                a.get("when"),
                a.get("table_type"),
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )
    text = buf.getvalue()
    if path:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    return text


def _html_escape(s):
    t = "" if s is None else str(s)
    return (
        t.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _heatmap_png_base64(abs_matrix, index_1=None, index_2=None, title=""):
    if not abs_matrix:
        return None
    try:
        import numpy as np
        from matplotlib.figure import Figure
        from matplotlib import colors as mcolors
        import matplotlib as mpl
        from libdiff.gui.plots import _apply_theme, figure_to_png_base64
    except Exception:
        return None
    try:
        _apply_theme()
        rows = [[(np.nan if c is None else float(c)) for c in row] for row in abs_matrix]
        arr = np.array(rows, dtype=float)
        if arr.size == 0:
            return None
        fig = Figure(figsize=(4.2, 3.2), tight_layout=True)
        ax = fig.add_subplot(111)
        try:
            cmap = mpl.colormaps["RdBu_r"].copy()
        except Exception:
            cmap = mpl.cm.get_cmap("RdBu_r")
        try:
            cmap.set_bad(color="#D1D5DB")
        except Exception:
            pass
        z = np.ma.masked_invalid(arr)
        vmax = float(np.nanmax(np.abs(arr))) if np.isfinite(np.nanmax(np.abs(arr))) else 1.0
        if vmax == 0:
            vmax = 1.0
        norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)
        im = ax.imshow(z, aspect="auto", cmap=cmap, norm=norm, interpolation="nearest")
        ax.set_title(title or "delta", fontsize=10)
        if index_2 is not None and len(index_2) == z.shape[1] and z.shape[1] <= 16:
            ax.set_xticks(range(z.shape[1]))
            ax.set_xticklabels([str(x) for x in index_2], rotation=45, ha="right", fontsize=6)
        if index_1 is not None and len(index_1) == z.shape[0] and z.shape[0] <= 16:
            ax.set_yticks(range(z.shape[0]))
            ax.set_yticklabels([str(y) for y in index_1], fontsize=6)
        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("delta", fontsize=7)
        b64 = figure_to_png_base64(fig, dpi=100)
        try:
            import matplotlib.pyplot as plt
            plt.close(fig)
        except Exception:
            pass
        return b64
    except Exception:
        return None


def export_timing_qa_html(report, path=None, embed_plots=True, max_plots=3):
    """Self-contained HTML report (inline CSS) with summary, fail ranking, missing arcs."""
    s = report.get("summary") or {}
    is_batch = s.get("mode") == "batch" or "cells" in report
    fails = [a for a in (report.get("arcs") or []) if a.get("exceeds_tol")]
    fails.sort(key=lambda a: (a.get("max_abs") is None, -(a.get("max_abs") or 0)))

    plot_blocks = []
    if embed_plots:
        plotted = 0
        for a in fails:
            if plotted >= max_plots:
                break
            mat = a.get("abs_matrix")
            if not mat:
                continue
            title = "%s %s->%s %s" % (
                a.get("cell"),
                a.get("related_pin"),
                a.get("pin"),
                a.get("table_type"),
            )
            b64 = _heatmap_png_base64(
                mat,
                index_1=a.get("index_1_left") or a.get("index_1_right"),
                index_2=a.get("index_2_left") or a.get("index_2_right"),
                title=title,
            )
            if b64:
                plot_blocks.append(
                    '<div class="plot"><h3>%s</h3>'
                    '<img alt="heatmap" src="data:image/png;base64,%s"/></div>'
                    % (_html_escape(title), b64)
                )
                plotted += 1

    def rows_html(items, cols):
        out = ["<table><thead><tr>"]
        for c in cols:
            out.append("<th>%s</th>" % _html_escape(c))
        out.append("</tr></thead><tbody>")
        for it in items:
            out.append("<tr>")
            for c in cols:
                val = it.get(c, "")
                cls = ""
                if c == "status" and str(val) in ("fail", "missing", "left-only", "right-only"):
                    cls = ' class="bad"'
                elif c == "status" and str(val) == "ok":
                    cls = ' class="ok"'
                out.append("<td%s>%s</td>" % (cls, _html_escape(val)))
            out.append("</tr>")
        out.append("</tbody></table>")
        return "".join(out)

    top_cells = s.get("top_failing_cells") or report.get("cells") or []
    if isinstance(top_cells, list) and top_cells and "n_fail" in (top_cells[0] or {}):
        cell_table = rows_html(
            top_cells[:30],
            ["cell", "n_arcs_matched", "n_fail", "n_left_only", "n_right_only"],
        )
    else:
        cell_table = "<p class='muted'>No per-cell batch summary (single-cell run).</p>"

    fail_rows = [
        {
            "cell": a.get("cell"),
            "pin": a.get("pin"),
            "related_pin": a.get("related_pin"),
            "table_type": a.get("table_type"),
            "max_abs": a.get("max_abs"),
            "max_rel": a.get("max_rel"),
            "status": a.get("status"),
        }
        for a in fails[:40]
    ]
    fail_table = (
        rows_html(
            fail_rows,
            ["status", "cell", "pin", "related_pin", "table_type", "max_abs", "max_rel"],
        )
        if fail_rows
        else "<p class='ok'>No failing arcs.</p>"
    )

    missing = []
    for a in report.get("left_only") or []:
        missing.append(dict(a, side="left_only", status="missing"))
    for a in report.get("right_only") or []:
        missing.append(dict(a, side="right_only", status="missing"))
    miss_table = (
        rows_html(
            missing[:80],
            ["status", "side", "cell", "pin", "related_pin", "table_type", "when"],
        )
        if missing
        else "<p class='ok'>No missing arcs.</p>"
    )

    css = (
        "body{font-family:Segoe UI,Helvetica,Arial,sans-serif;margin:24px;color:#1f2937;background:#f8fafc}"
        "h1{font-size:1.4rem;margin:0 0 8px}"
        "h2{font-size:1.1rem;margin:28px 0 10px;border-bottom:1px solid #e5e7eb;padding-bottom:4px}"
        ".meta{color:#4b5563;font-size:0.9rem;margin-bottom:16px}"
        ".cards{display:flex;flex-wrap:wrap;gap:12px;margin:12px 0 20px}"
        ".card{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;min-width:120px}"
        ".card .n{font-size:1.35rem;font-weight:600}"
        ".card .l{font-size:0.75rem;color:#6b7280;text-transform:uppercase}"
        "table{border-collapse:collapse;width:100%;background:#fff;font-size:0.85rem}"
        "th,td{border:1px solid #e5e7eb;padding:6px 8px;text-align:left}"
        "th{background:#f3f4f6}"
        ".bad{color:#b91c1c;font-weight:600}"
        ".ok{color:#15803d}"
        ".muted{color:#6b7280}"
        ".plot{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:12px;margin:12px 0}"
        ".plot img{max-width:100%;height:auto}"
    )

    html = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'/>",
        "<title>libDiff Timing QA Report</title>",
        "<style>%s</style></head><body>" % css,
        "<h1>libDiff Timing QA Report</h1>",
        (
            "<div class='meta'>left: %s<br/>right: %s<br/>mode: %s &nbsp; abs_tol=%s &nbsp; rel_tol=%s</div>"
            % (
                _html_escape(report.get("left")),
                _html_escape(report.get("right")),
                _html_escape(s.get("mode") or ("batch" if is_batch else "single")),
                _html_escape(s.get("abs_tol")),
                _html_escape(s.get("rel_tol")),
            )
        ),
        "<div class='cards'>",
        "<div class='card'><div class='n'>%s</div><div class='l'>Matched arcs</div></div>"
        % _html_escape(s.get("n_arcs_matched")),
        "<div class='card'><div class='n'>%s</div><div class='l'>Fails</div></div>"
        % _html_escape(s.get("n_fail")),
        "<div class='card'><div class='n'>%s</div><div class='l'>Missing</div></div>"
        % _html_escape(s.get("n_missing")),
        "<div class='card'><div class='n'>%s</div><div class='l'>Left-only</div></div>"
        % _html_escape(s.get("n_left_only")),
        "<div class='card'><div class='n'>%s</div><div class='l'>Right-only</div></div>"
        % _html_escape(s.get("n_right_only")),
    ]
    if s.get("n_cells_compared") is not None:
        html.append(
            "<div class='card'><div class='n'>%s</div><div class='l'>Cells</div></div>"
            % _html_escape(s.get("n_cells_compared"))
        )
    html.append("</div>")
    html.append("<h2>Top failing cells</h2>")
    html.append(cell_table)
    html.append("<h2>Fail ranking (arcs)</h2>")
    html.append(fail_table)
    if plot_blocks:
        html.append("<h2>Top failing arc heatmaps</h2>")
        html.extend(plot_blocks)
    html.append("<h2>Missing arcs</h2>")
    html.append(miss_table)
    html.append("<p class='muted'>Generated by libDiff Timing QA</p>")
    html.append("</body></html>")
    text = "\n".join(html)
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return text


def format_timing_qa_batch_summary(report):
    s = report.get("summary") or {}
    lines = [
        "Timing QA batch (Liberty / NLDM)",
        "left : %s" % report.get("left"),
        "right: %s" % report.get("right"),
        "cells compared : %s" % s.get("n_cells_compared"),
        "matched arcs   : %s" % s.get("n_arcs_matched"),
        "fail (tol)     : %s  (abs_tol=%s rel_tol=%s)"
        % (s.get("n_fail"), s.get("abs_tol"), s.get("rel_tol")),
        "left-only arcs : %s" % s.get("n_left_only"),
        "right-only arcs: %s" % s.get("n_right_only"),
        "cells only-L/R : %s / %s"
        % (s.get("n_cells_left_only"), s.get("n_cells_right_only")),
    ]
    top_cells = s.get("top_failing_cells") or []
    if top_cells:
        lines.append("top failing cells:")
        for c in top_cells[:10]:
            if (c.get("n_fail") or 0) == 0:
                continue
            lines.append(
                "  %s  fail=%s matched=%s"
                % (c.get("cell"), c.get("n_fail"), c.get("n_arcs_matched"))
            )
    top_arcs = s.get("top_failing_arcs") or []
    if top_arcs:
        lines.append("top failing arcs:")
        for a in top_arcs[:10]:
            lines.append(
                "  %s %s->%s %s  max_abs=%s max_rel=%s"
                % (
                    a.get("cell"),
                    a.get("related_pin"),
                    a.get("pin"),
                    a.get("table_type"),
                    a.get("max_abs"),
                    a.get("max_rel"),
                )
            )
    return "\n".join(lines)


__all__ = [
    "run_timing_qa_batch",
    "export_timing_qa_batch_csv",
    "export_timing_qa_html",
    "format_timing_qa_batch_summary",
]
