
"""Structure-aligned Liberty compare with abs/rel deltas and unit checks."""

from __future__ import annotations

import csv
import io
import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from libdiff.errors import UnitConflictError
from libdiff.model.library import Library, load_library, NA
from libdiff.parser.liberty import safe_float

# time_unit / leakage_power_unit scale factors relative to SI base (seconds, watts)
_TIME_TO_S = {
    "1ps": 1e-12,
    "ps": 1e-12,
    "1ns": 1e-9,
    "ns": 1e-9,
    "1us": 1e-6,
    "us": 1e-6,
}
_POWER_TO_W = {
    "1pW": 1e-12,
    "pw": 1e-12,
    "1nW": 1e-9,
    "nw": 1e-9,
    "1uW": 1e-6,
    "uw": 1e-6,
    "1mW": 1e-3,
    "mw": 1e-3,
}


def _norm_unit(u: Optional[str]) -> str:
    if not u:
        return ""
    s = str(u).strip().strip('"').replace(" ", "")
    return s


def _unit_scale(unit: str, table: Dict[str, float]) -> Optional[float]:
    u = _norm_unit(unit)
    if not u:
        return None
    if u in table:
        return table[u]
    # try lowercase digit+unit
    low = u.lower()
    for k, v in table.items():
        if k.lower() == low:
            return v
    # strip leading digits for bare unit match e.g. "1ns" already covered
    m = re.match(r"^([\d.]+)([a-zA-Z]+)$", u)
    if m:
        mult = float(m.group(1))
        bare = m.group(2)
        for k, v in table.items():
            if k.lower() == bare.lower() or k.lower().endswith(bare.lower()):
                # k like "ns" or "1ns"
                base = v / (1.0 if not k[0].isdigit() else float(re.match(r"[\d.]+", k).group(0)))
                return mult * base
    return None


def check_units(left: Library, right: Library, convert: bool = False) -> Dict[str, Any]:
    """Return unit comparison info; raise UnitConflictError if conflict and not convertible."""
    lu = left.units()
    ru = right.units()
    report = {"left": lu, "right": ru, "conflicts": [], "conversions": []}
    keys = sorted(set(lu) | set(ru))
    for k in keys:
        a, b = lu.get(k), ru.get(k)
        if a is None or b is None:
            continue
        if _norm_unit(a) == _norm_unit(b):
            continue
        scale_a = scale_b = None
        if "time" in k:
            scale_a = _unit_scale(a, _TIME_TO_S)
            scale_b = _unit_scale(b, _TIME_TO_S)
        elif "power" in k or "leakage" in k:
            scale_a = _unit_scale(a, _POWER_TO_W)
            scale_b = _unit_scale(b, _POWER_TO_W)
        if convert and scale_a and scale_b:
            report["conversions"].append(
                {"unit": k, "left": a, "right": b, "left_to_si": scale_a, "right_to_si": scale_b}
            )
        else:
            report["conflicts"].append({"unit": k, "left": a, "right": b})
    if report["conflicts"]:
        c0 = report["conflicts"][0]
        raise UnitConflictError(
            "Unit conflict on %s: %s vs %s (refusing numeric compare; pass convert=True if scales known)"
            % (c0["unit"], c0["left"], c0["right"]),
            unit_name=c0["unit"],
            left=c0["left"],
            right=c0["right"],
        )
    return report


def _delta(a: Optional[float], b: Optional[float]) -> Dict[str, Any]:
    if a is None or b is None:
        return {"left": a, "right": b, "abs": None, "rel": None, "status": "missing"}
    abs_d = b - a
    rel = None if a == 0 else (abs_d / a)
    return {"left": a, "right": b, "abs": abs_d, "rel": rel, "status": "ok"}


def _timing_key(t: dict) -> tuple:
    return (
        t.get("pin"),
        t.get("related_pin"),
        t.get("related_pg_pin"),
        t.get("timing_sense"),
        t.get("timing_type"),
        t.get("when"),
        t.get("table_type"),
    )


def _flatten_lut(values: List[List[Optional[float]]]) -> List[Optional[float]]:
    flat = []
    for row in values or []:
        flat.extend(row)
    return flat


def compare_libraries(
    left: Union[str, Library],
    right: Union[str, Library],
    cells: Optional[Sequence[str]] = None,
    cell_pattern: Optional[str] = None,
    convert_units: bool = False,
    block_on_unit_conflict: bool = True,
) -> Dict[str, Any]:
    """Compare two libraries; return structured report suitable for JSON/CSV."""
    left_lib = left if isinstance(left, Library) else load_library(left)
    right_lib = right if isinstance(right, Library) else load_library(right)

    unit_info: Dict[str, Any] = {"left": left_lib.units(), "right": right_lib.units()}
    unit_error = None
    try:
        unit_info = check_units(left_lib, right_lib, convert=convert_units)
    except UnitConflictError as exc:
        unit_error = str(exc)
        if block_on_unit_conflict and not convert_units:
            return {
                "left": left_lib.key,
                "right": right_lib.key,
                "units": unit_info,
                "unit_error": unit_error,
                "cells": {},
                "summary": {"compared_cells": 0, "blocked": True},
            }

    left_cells = set(left_lib.cell_names())
    right_cells = set(right_lib.cell_names())
    if cell_pattern:
        left_cells &= set(left_lib.select_cells(cell_pattern))
        right_cells &= set(right_lib.select_cells(cell_pattern))
    if cells:
        wanted = set(cells)
        left_cells &= wanted
        right_cells &= wanted

    all_names = sorted(left_cells | right_cells)
    cell_reports = {}
    for name in all_names:
        entry: Dict[str, Any] = {"name": name, "in_left": name in left_cells, "in_right": name in right_cells}
        if name not in left_cells or name not in right_cells:
            entry["status"] = "structure_mismatch"
            cell_reports[name] = entry
            continue

        if unit_error and block_on_unit_conflict:
            entry["status"] = "unit_blocked"
            cell_reports[name] = entry
            continue

        lc = left_lib.cell(name)
        rc = right_lib.cell(name)
        entry["area"] = _delta(lc.area, rc.area)

        # leakage aligned by (when, related_pg_pin)
        l_leak = {(e["when"], e["related_pg_pin"]): e["value"] for e in lc.leakage_entries()}
        r_leak = {(e["when"], e["related_pg_pin"]): e["value"] for e in rc.leakage_entries()}
        leak_keys = sorted(set(l_leak) | set(r_leak))
        entry["leakage"] = []
        for k in leak_keys:
            entry["leakage"].append(
                {"when": k[0], "related_pg_pin": k[1], **_delta(l_leak.get(k), r_leak.get(k))}
            )

        # timing LUT sample diffs
        l_tables = {_timing_key(t): t for t in lc.timing_tables()}
        r_tables = {_timing_key(t): t for t in rc.timing_tables()}
        tkeys = sorted(set(l_tables) | set(r_tables))
        entry["timing"] = []
        for tk in tkeys:
            lt = l_tables.get(tk)
            rt = r_tables.get(tk)
            if lt is None or rt is None:
                entry["timing"].append(
                    {
                        "key": list(tk),
                        "status": "structure_mismatch",
                        "samples": [],
                    }
                )
                continue
            lf = _flatten_lut(lt["values"])
            rf = _flatten_lut(rt["values"])
            n = max(len(lf), len(rf))
            samples = []
            for i in range(n):
                a = lf[i] if i < len(lf) else None
                b = rf[i] if i < len(rf) else None
                samples.append(_delta(a, b))
            # summary stats over present samples
            abs_vals = [s["abs"] for s in samples if s["abs"] is not None]
            entry["timing"].append(
                {
                    "key": list(tk),
                    "table_type": tk[-1],
                    "status": "ok",
                    "n_samples": len(samples),
                    "max_abs": max(abs_vals) if abs_vals else None,
                    "mean_abs": (sum(abs_vals) / len(abs_vals)) if abs_vals else None,
                    "samples": samples,
                }
            )
        entry["status"] = "ok"
        cell_reports[name] = entry

    return {
        "left": left_lib.key,
        "right": right_lib.key,
        "units": unit_info,
        "unit_error": unit_error,
        "cells": cell_reports,
        "summary": {
            "compared_cells": sum(1 for c in cell_reports.values() if c.get("status") == "ok"),
            "only_left": sorted(left_cells - right_cells),
            "only_right": sorted(right_cells - left_cells),
            "blocked": bool(unit_error and block_on_unit_conflict),
        },
    }


def export_json(report: Dict[str, Any], path: Optional[str] = None, indent: int = 2) -> str:
    text = json.dumps(report, indent=indent, default=str)
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return text


def export_csv(report: Dict[str, Any], path: Optional[str] = None) -> str:
    """Flat CSV of area + leakage + timing max_abs per cell/table."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "cell",
            "kind",
            "detail",
            "left",
            "right",
            "abs_delta",
            "rel_delta",
            "status",
        ]
    )
    for name, cell in (report.get("cells") or {}).items():
        if "area" in cell:
            a = cell["area"]
            writer.writerow(
                [name, "area", "", a.get("left"), a.get("right"), a.get("abs"), a.get("rel"), a.get("status")]
            )
        for leak in cell.get("leakage") or []:
            writer.writerow(
                [
                    name,
                    "leakage",
                    "%s|%s" % (leak.get("when"), leak.get("related_pg_pin")),
                    leak.get("left"),
                    leak.get("right"),
                    leak.get("abs"),
                    leak.get("rel"),
                    leak.get("status"),
                ]
            )
        for t in cell.get("timing") or []:
            writer.writerow(
                [
                    name,
                    "timing",
                    t.get("table_type") or "/".join(str(x) for x in (t.get("key") or [])),
                    "",
                    "",
                    t.get("max_abs"),
                    "",
                    t.get("status"),
                ]
            )
    text = buf.getvalue()
    if path:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    return text


__all__ = ["compare_libraries", "export_json", "export_csv", "check_units"]
