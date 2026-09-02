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


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="libdiff",
        description="libDiff — Liberty (.lib) compare/analysis for FIP stdcell/SRAM teams",
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
                   help="Also run Timing QA (NLDM arc Δ / missing / thresholds)")
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
    tq.add_argument("--abs-tol", type=float, default=1e-4, help="Absolute Δ tolerance")
    tq.add_argument("--rel-tol", type=float, default=0.01, help="Relative Δ tolerance")
    tq.add_argument("--json", dest="json_out", nargs="?", const="-", default=None,
                    help="Write JSON (path or stdout)")
    tq.add_argument("--csv", dest="csv_out", default=None, help="Write CSV report to path")
    tq.add_argument("--no-matrices", action="store_true",
                    help="Omit full Δ/%% matrices from JSON (smaller)")
    tq.add_argument("--single-lib-qa", action="store_true",
                    help="Also run monotonicity/negative/empty checks per lib")
    tq.add_argument("--batch", action="store_true",
                    help="Batch Timing QA over filtered/common cells with library summary")
    tq.add_argument("--all-cells", action="store_true",
                    help="Compare all cells common to both libs (implies --batch)")
    tq.add_argument("--html", dest="html_out", default=None,
                    help="Write self-contained HTML report to path")

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
