"""High-level Liberty library analysis summaries."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Union

from libdiff.model.library import Library, load_library
from libdiff.parser.liberty import safe_float


def analyze_library(
    path: Union[str, os.PathLike],
    *,
    sample_cells: int = 8,
    library: Optional[Library] = None,
) -> Dict[str, Any]:
    """Return a summary dict for one .lib (cell counts, units, samples, coverage)."""
    lib = library or load_library(path)
    cells = lib.cell_names()
    units = lib.units()

    area_available = 0
    leakage_available = 0
    sample: List[Dict[str, Any]] = []

    # Walk parser cell groups once for coverage + samples
    parser = lib.parser
    cell_groups = []
    if "group" in parser.libDic:
        cell_groups = [g for g in parser.libDic["group"] if g.get("type") == "cell"]

    for g in cell_groups:
        name = g.get("name", "")
        has_area = "area" in g and safe_float(g.get("area")) is not None
        has_leak_attr = "cell_leakage_power" in g and safe_float(g.get("cell_leakage_power")) is not None
        has_leak_group = False
        if "group" in g:
            for sub in g["group"]:
                if sub.get("type") == "leakage_power":
                    has_leak_group = True
                    break
        if has_area:
            area_available += 1
        if has_leak_attr or has_leak_group:
            leakage_available += 1
        if len(sample) < max(0, sample_cells):
            sample.append(
                {
                    "name": name,
                    "area": safe_float(g.get("area")) if has_area else None,
                    "cell_leakage_power": safe_float(g.get("cell_leakage_power"))
                    if has_leak_attr
                    else None,
                    "has_leakage_power_group": has_leak_group,
                }
            )

    return {
        "path": lib.path,
        "display_name": lib.display_name,
        "library_name": parser.libDic.get("name"),
        "cell_count": len(cells),
        "units": units,
        "area_available": area_available,
        "leakage_available": leakage_available,
        "sample_cells": sample,
        "all_cells": cells if sample_cells < 0 else None,
    }


def format_analyze_report(summary: Dict[str, Any]) -> str:
    """Human-readable analyze summary."""
    lines = [
        "path: %s" % summary["path"],
        "library: %s" % (summary.get("library_name") or summary.get("display_name")),
        "cells: %d" % summary["cell_count"],
        "area_available: %d" % summary["area_available"],
        "leakage_available: %d" % summary["leakage_available"],
        "units:",
    ]
    for k, v in (summary.get("units") or {}).items():
        lines.append("  %s: %s" % (k, v))
    lines.append("sample_cells:")
    for c in summary.get("sample_cells") or []:
        lines.append(
            "  %s  area=%s  cell_leakage_power=%s  leakage_group=%s"
            % (
                c.get("name"),
                c.get("area"),
                c.get("cell_leakage_power"),
                c.get("has_leakage_power_group"),
            )
        )
    return "\n".join(lines)


__all__ = ["analyze_library", "format_analyze_report"]
