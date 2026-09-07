"""Command-line interface for libDiff."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from libdiff import __version__
from libdiff.analyze import analyze_library, format_analyze_report
from libdiff.compare.diff import compare_libraries, export_csv, export_json
from libdiff.compare.ppa import (
    compare_ppa,
    export_ppa_csv,
    export_ppa_html,
    export_ppa_json,
    format_ppa_summary,
)
from libdiff.compare.timing_qa import (
    timing_qa,
    export_timing_qa_csv,
    export_timing_qa_json,
    format_timing_qa_summary,
    run_timing_qa_batch,
    export_timing_qa_batch_csv,
    export_timing_qa_html,
    format_timing_qa_batch_summary,
)
from libdiff.discover import discover_libs
from libdiff.errors import LibDiffError, UnitConflictError
from libdiff.model.library import load_library
from libdiff.compare.lut_index import (
    classify_lut,
    cross_index_delta,
    probe_points,
    resolve_indices,
    sample_lut,
    slice_curve,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="libdiff",
        description="libDiff - Liberty (.lib) compare/analysis for FIP stdcell/SRAM teams",
    )
    p.add_argument("--version", action="version", version="libDiff %s" % __version__)
    sub = p.add_subparsers(dest="command")

    # compare
    c = sub.add_parser("compare", help="Compare two Liberty libraries")
    c.add_argument("left", help="Baseline .lib path")
    c.add_argument("right", help="Perturbed / other .lib path")
    c.add_argument("--json", dest="json_out", nargs="?", const="-", default=None,
                   help="Write JSON report to path (or stdout if bare --json)")
    c.add_argument("--csv", dest="csv_out", default=None, help="Write CSV report to path")
    c.add_argument("--cells", nargs="*", default=None, help="Restrict to these cell names")
    c.add_argument("--pattern", default=None, help="fnmatch cell pattern")
    c.add_argument("--convert-units", action="store_true", help="Attempt unit conversion when scales known")
    c.add_argument("--allow-unit-conflict", action="store_true",
                   help="Do not block report on unit conflict (numeric deltas omitted)")
    c.add_argument("--timing-qa", action="store_true",
                   help="Also run Timing QA (NLDM arc delta / missing / thresholds)")
    c.add_argument("--abs-tol", type=float, default=1e-4, help="Timing QA absolute tolerance")
    c.add_argument("--rel-tol", type=float, default=0.01, help="Timing QA relative tolerance")

    # timing-qa
    tq = sub.add_parser(
        "timing-qa",
        help="Timing QA: NLDM arc compare (Qualib / Liberate-LV inspired, Liberty only)",
    )
    tq.add_argument("left", help="Baseline .lib path")
    tq.add_argument("right", help="Other .lib path")
    tq.add_argument("--cell", dest="cell_pattern", default=None,
                    help="fnmatch cell pattern, e.g. INV* or inv_x1")
    tq.add_argument("--cells", nargs="*", default=None, help="Exact cell name list")
    tq.add_argument("--table-type", nargs="*", default=None,
                    help="Restrict table types (cell_rise cell_fall ...)")
    tq.add_argument("--abs-tol", type=float, default=1e-4, help="Absolute delta tolerance")
    tq.add_argument("--rel-tol", type=float, default=0.01, help="Relative delta tolerance")
    tq.add_argument("--json", dest="json_out", nargs="?", const="-", default=None,
                    help="Write JSON (path or stdout)")
    tq.add_argument("--csv", dest="csv_out", default=None, help="Write CSV report to path")
    tq.add_argument("--no-matrices", action="store_true",
                    help="Omit full delta/%% matrices from JSON (smaller)")
    tq.add_argument("--single-lib-qa", action="store_true",
                    help="Also run monotonicity/negative/empty checks per lib")
    tq.add_argument("--batch", action="store_true",
                    help="Batch Timing QA over filtered/common cells with library summary")
    tq.add_argument("--all-cells", action="store_true",
                    help="Compare all cells common to both libs (implies --batch)")
    tq.add_argument("--html", dest="html_out", default=None,
                    help="Write self-contained HTML report to path")


    # ppa
    ppa = sub.add_parser(
        "ppa",
        help="Stdcell PPA compare: Area / Leakage / typical delay vs baseline",
    )
    ppa.add_argument("left", help="Baseline .lib path")
    ppa.add_argument("right", help="Compare .lib path")
    ppa.add_argument("--cell", dest="cell_pattern", default=None,
                     help="fnmatch cell pattern, e.g. INV*")
    ppa.add_argument("--cells", nargs="*", default=None, help="Exact cell name list")
    ppa.add_argument("--mode", choices=["stdcell", "sram"], default="stdcell",
                     help="Analysis mode (sram is stub-only in Phase A)")
    ppa.add_argument("--notes", default="", help="Free-text notes for HTML cover")
    ppa.add_argument("--json", dest="json_out", nargs="?", const="-", default=None,
                     help="Write JSON (path or stdout)")
    ppa.add_argument("--csv", dest="csv_out", default=None, help="Write CSV report to path")
    ppa.add_argument("--html", dest="html_out", default=None,
                     help="Write one-page PPA HTML report to path")

    # cells
    cells = sub.add_parser("cells", help="List cells in a library")
    cells.add_argument("lib", help=".lib path")
    cells.add_argument("--pattern", default=None)

    # units
    units = sub.add_parser("units", help="Show library units")
    units.add_argument("lib", help=".lib path")

    # discover
    disc = sub.add_parser("discover", help="List .lib files in a directory")
    disc.add_argument("directory", help="Directory to scan")
    disc.add_argument("--recursive", "-r", action="store_true", help="Recurse into subdirectories")
    disc.add_argument("--json", dest="json_out", action="store_true", help="Emit JSON")

    # analyze
    an = sub.add_parser("analyze", help="Summarize one Liberty library")
    an.add_argument("lib", help=".lib path")
    an.add_argument(
        "--cells",
        type=int,
        default=8,
        metavar="N",
        help="Number of sample cells to print (default 8; use 0 for none)",
    )
    an.add_argument("--json", dest="json_out", action="store_true", help="Emit JSON")

    # lut-probe
    lp = sub.add_parser(
        "lut-probe",
        help="Probe / slice / cross-index compare timing LUTs at physical index values",
    )
    lp.add_argument("left", help="Left / baseline .lib path")
    lp.add_argument("right", nargs="?", default=None, help="Optional right .lib for delta / cross")
    lp.add_argument("--cell", required=True, help="Cell name")
    lp.add_argument("--pin", required=True, help="Output pin name")
    lp.add_argument("--related", default=None, help="Related pin filter (optional)")
    lp.add_argument(
        "--table",
        default="cell_rise",
        help="Table type: cell_rise|cell_fall|rise_transition|fall_transition|...",
    )
    lp.add_argument("--i1", type=float, default=None, help="Physical index_1 (slew) probe value")
    lp.add_argument("--i2", type=float, default=None, help="Physical index_2 (load) probe value")
    lp.add_argument(
        "--slice",
        dest="slice_axis",
        choices=["index_1", "index_2"],
        default=None,
        help="Slice 2D LUT to 1D curve along free axis",
    )
    lp.add_argument("--fix-i1", type=float, default=None, help="Fixed index_1 when --slice index_2")
    lp.add_argument("--fix-i2", type=float, default=None, help="Fixed index_2 when --slice index_1")
    lp.add_argument(
        "--slice-method",
        choices=["nearest", "interp"],
        default="interp",
        help="Slice fix-axis method (default interp)",
    )
    lp.add_argument(
        "--cross-mode",
        choices=["left_grid", "union", "intersection", "query"],
        default="left_grid",
        help="Cross-index grid mode when right lib given (default left_grid)",
    )
    lp.add_argument(
        "--query-i1",
        default=None,
        help="Comma-separated query index_1 grid for --cross-mode query",
    )
    lp.add_argument(
        "--query-i2",
        default=None,
        help="Comma-separated query index_2 grid for --cross-mode query",
    )

    # gui
    gui = sub.add_parser("gui", help="Launch libDiff GUI")
    gui.add_argument("libs", nargs="*", help="Optional .lib files to preload")

    return p


def cmd_compare(args: argparse.Namespace) -> int:
    report = compare_libraries(
        args.left,
        args.right,
        cells=args.cells,
        cell_pattern=args.pattern,
        convert_units=args.convert_units,
        block_on_unit_conflict=not args.allow_unit_conflict,
    )
    if args.json_out is not None:
        text = export_json(report)
        if args.json_out == "-":
            sys.stdout.write(text)
            if not text.endswith("\n"):
                sys.stdout.write("\n")
        else:
            export_json(report, path=args.json_out)
            print("Wrote JSON:", args.json_out)
    if args.csv_out:
        export_csv(report, path=args.csv_out)
        print("Wrote CSV:", args.csv_out)
    if args.json_out is None and not args.csv_out:
        # human summary
        s = report["summary"]
        print("left :", report["left"])
        print("right:", report["right"])
        if report.get("unit_error"):
            print("UNIT:", report["unit_error"])
        print("compared_cells:", s.get("compared_cells"))
        print("only_left:", s.get("only_left"))
        print("only_right:", s.get("only_right"))
        for name, cell in report["cells"].items():
            if cell.get("status") != "ok":
                print(" ", name, cell.get("status"))
                continue
            area = cell.get("area") or {}
            print(" ", name, "area_abs=", area.get("abs"), "timing_tables=", len(cell.get("timing") or []))

    if getattr(args, "timing_qa", False):
        tq = timing_qa(
            args.left,
            args.right,
            cells=args.cells,
            cell_pattern=args.pattern,
            abs_tol=args.abs_tol,
            rel_tol=args.rel_tol,
            include_matrices=False,
        )
        print()
        print(format_timing_qa_summary(tq))

    return 1 if report.get("unit_error") and not args.allow_unit_conflict else 0


def cmd_timing_qa(args: argparse.Namespace) -> int:
    batch = bool(getattr(args, "batch", False) or getattr(args, "all_cells", False))
    want_html = getattr(args, "html_out", None)
    # HTML heatmaps need matrices; force include when writing HTML
    include_matrices = (not args.no_matrices) or bool(want_html)

    if batch:
        # --all-cells ignores cell filter unless --cell/--cells also given intentionally
        pattern = None if getattr(args, "all_cells", False) and not args.cell_pattern and not args.cells else args.cell_pattern
        report = run_timing_qa_batch(
            args.left,
            args.right,
            cells=args.cells,
            cell_pattern=pattern,
            table_types=args.table_type,
            abs_tol=args.abs_tol,
            rel_tol=args.rel_tol,
            include_matrices=include_matrices,
        )
        summary_fn = format_timing_qa_batch_summary
        csv_fn = export_timing_qa_batch_csv
    else:
        report = timing_qa(
            args.left,
            args.right,
            cells=args.cells,
            cell_pattern=args.cell_pattern,
            table_types=args.table_type,
            abs_tol=args.abs_tol,
            rel_tol=args.rel_tol,
            include_matrices=include_matrices,
            run_single_lib_qa=args.single_lib_qa,
        )
        summary_fn = format_timing_qa_summary
        csv_fn = export_timing_qa_csv

    if args.json_out is not None:
        text = export_timing_qa_json(report)
        if args.json_out == "-":
            sys.stdout.write(text)
            if not text.endswith("\n"):
                sys.stdout.write("\n")
        else:
            export_timing_qa_json(report, path=args.json_out)
            print("Wrote JSON:", args.json_out)
    if args.csv_out:
        csv_fn(report, path=args.csv_out)
        print("Wrote CSV:", args.csv_out)
    if want_html:
        export_timing_qa_html(report, path=want_html, embed_plots=True)
        print("Wrote HTML:", want_html)

    wrote_file = bool(args.csv_out or want_html or (args.json_out is not None and args.json_out != "-"))
    if args.json_out is None and not args.csv_out and not want_html:
        print(summary_fn(report))
    elif wrote_file and (args.json_out is None or args.json_out != "-"):
        print(summary_fn(report))
    return 0 if (report.get("summary") or {}).get("n_fail", 0) == 0 else 1


def cmd_cells(args: argparse.Namespace) -> int:
    lib = load_library(args.lib)
    names = lib.select_cells(args.pattern) if args.pattern else lib.cell_names()
    for n in names:
        print(n)
    return 0


def cmd_units(args: argparse.Namespace) -> int:
    lib = load_library(args.lib)
    for k, v in lib.units().items():
        print("%s: %s" % (k, v))
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    entries = discover_libs(args.directory, recursive=args.recursive)
    if args.json_out:
        print(json.dumps([e.to_dict() for e in entries], indent=2))
        return 0
    root = os.path.abspath(args.directory)
    if not entries:
        print("No .lib files found in", root)
        return 0
    print("%d .lib file(s):" % len(entries))
    for e in entries:
        name = e.library_name or "?"
        print("  %s  (%d bytes, library=%s)" % (e.path, e.size, name))
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    summary = analyze_library(args.lib, sample_cells=args.cells)
    if args.json_out:
        payload = {k: v for k, v in summary.items() if v is not None}
        print(json.dumps(payload, indent=2))
        return 0
    print(format_analyze_report(summary))
    return 0



def cmd_ppa(args: argparse.Namespace) -> int:
    report = compare_ppa(
        args.left,
        args.right,
        cells=args.cells,
        cell_pattern=args.cell_pattern,
        mode=args.mode,
        notes=args.notes or "",
    )
    if args.json_out is not None:
        text = export_ppa_json(report)
        if args.json_out == "-":
            sys.stdout.write(text)
            if not text.endswith("\n"):
                sys.stdout.write("\n")
        else:
            export_ppa_json(report, path=args.json_out)
            print("Wrote JSON:", args.json_out)
    if args.csv_out:
        export_ppa_csv(report, path=args.csv_out)
        print("Wrote CSV:", args.csv_out)
    if args.html_out:
        export_ppa_html(report, path=args.html_out, embed_plots=True)
        print("Wrote HTML:", args.html_out)

    wrote_file = bool(
        args.csv_out or args.html_out or (args.json_out is not None and args.json_out != "-")
    )
    if args.json_out is None and not args.csv_out and not args.html_out:
        print(format_ppa_summary(report))
    elif wrote_file and (args.json_out is None or args.json_out != "-"):
        print(format_ppa_summary(report))
    # non-zero only for sram stub when explicitly requested? keep 0 for ok compare
    return 0



def _find_table(lib, cell: str, pin: str, table: str, related=None):
    tables = lib.cell(cell).timing_tables()
    matches = []
    for t in tables:
        if t.get("pin") != pin:
            continue
        if t.get("table_type") != table:
            continue
        if related is not None and str(t.get("related_pin")) != str(related):
            continue
        matches.append(t)
    return matches


def _parse_float_list(s):
    if not s:
        return None
    out = []
    for tok in str(s).replace(";", ",").split(","):
        tok = tok.strip()
        if not tok:
            continue
        out.append(float(tok))
    return out


def cmd_lut_probe(args: argparse.Namespace) -> int:
    """Probe / slice / cross-index compare LUTs at physical indices."""
    left = load_library(args.left)
    right = load_library(args.right) if args.right else None
    lt_list = _find_table(left, args.cell, args.pin, args.table, related=args.related)
    if not lt_list:
        print(
            "No left table for cell=%s pin=%s table=%s related=%s"
            % (args.cell, args.pin, args.table, args.related),
            file=sys.stderr,
        )
        return 2
    lt = lt_list[0]
    li1, li2, tname, v1, v2 = resolve_indices(left, lt)
    cls = classify_lut(lt)
    print("left :", left.key)
    print("cell=%s pin=%s table=%s" % (args.cell, args.pin, args.table))
    print("class=%s template=%s  var1=%s var2=%s" % (cls, tname, v1, v2))
    print("index_1:", li1)
    print("index_2:", li2)

    if args.i1 is not None:
        val = sample_lut(lt.get("values") or [], li1, li2, args.i1, args.i2)
        print("probe left @ (i1=%s, i2=%s) = %s" % (args.i1, args.i2, val))
        if right is not None:
            rt_list = _find_table(right, args.cell, args.pin, args.table, related=args.related)
            if not rt_list:
                print("No matching right table", file=sys.stderr)
                return 2
            rt = rt_list[0]
            ri1, ri2, _, _, _ = resolve_indices(right, rt)
            rval = sample_lut(rt.get("values") or [], ri1, ri2, args.i1, args.i2)
            print("probe right@ (i1=%s, i2=%s) = %s" % (args.i1, args.i2, rval))
            if val is not None and rval is not None:
                d = rval - val
                pct = None if val == 0 else d / val
                print("delta abs=%s  rel=%s" % (d, pct))
            else:
                print("delta: out_of_range (left=%s right=%s)" % (val, rval))

    if args.slice_axis:
        fixed = args.fix_i1 if args.slice_axis == "index_2" else args.fix_i2
        if fixed is None:
            # default fix to first of the other axis
            fixed = (li1[0] if li1 else 0.0) if args.slice_axis == "index_2" else (li2[0] if li2 else 0.0)
        xs, ys = slice_curve(lt, axis=args.slice_axis, fixed_value=fixed, method=args.slice_method, lib=left)
        print("slice free=%s fixed=%s method=%s" % (args.slice_axis, fixed, args.slice_method))
        for x, y in zip(xs, ys):
            print("  %s -> %s" % (x, y))

    if right is not None and (args.i1 is None or args.cross_mode):
        # Always print cross-index summary when right present
        rt_list = _find_table(right, args.cell, args.pin, args.table, related=args.related)
        if rt_list:
            rt = rt_list[0]
            qi1 = _parse_float_list(args.query_i1)
            qi2 = _parse_float_list(args.query_i2)
            cd = cross_index_delta(
                lt,
                rt,
                mode=args.cross_mode,
                query_i1=qi1,
                query_i2=qi2,
                left_lib=left,
                right_lib=right,
            )
            st = cd["stats"]
            print("cross-index mode=%s aligned=%s" % (cd["mode"], cd["aligned"]))
            print(
                "grid i1=%s i2=%s  max_abs=%s max_rel=%s n_compared=%s oor=%s"
                % (
                    cd["index_1"],
                    cd["index_2"],
                    st.get("max_abs"),
                    st.get("max_rel"),
                    st.get("n_compared"),
                    cd.get("out_of_range"),
                )
            )
            # print delta matrix compactly
            print("abs_matrix:")
            for row in cd["abs_matrix"]:
                print(" ", row)
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    from libdiff.gui.main_window import run_gui
    return run_gui(args.libs or [])


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    try:
        if args.command == "compare":
            return cmd_compare(args)
        if args.command == "timing-qa":
            return cmd_timing_qa(args)
        if args.command == "cells":
            return cmd_cells(args)
        if args.command == "units":
            return cmd_units(args)
        if args.command == "discover":
            return cmd_discover(args)
        if args.command == "analyze":
            return cmd_analyze(args)
        if args.command == "ppa":
            return cmd_ppa(args)
        if args.command == "lut-probe":
            return cmd_lut_probe(args)
        if args.command == "gui":
            return cmd_gui(args)
        parser.print_help()
        return 0
    except LibDiffError as exc:
        print("Error:", exc, file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print("Error:", exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
