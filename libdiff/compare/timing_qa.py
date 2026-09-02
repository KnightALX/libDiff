"""Timing QA: lib-to-lib NLDM arc compare + single-lib checks (Liberty only, no SPICE).

Inspired by Empyrean Qualib / Cadence Liberate LV / Synopsys PrimeLib library-compare
capabilities that can be done from Liberty alone.
"""

from __future__ import annotations

import csv
import io
import json
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from libdiff.model.library import Library, load_library, NA, KNOWN_TIMING_TABLES

# NLDM / constraint table types we fully matrix-diff
NLDM_TABLE_TYPES = frozenset(
    {
        "cell_rise",
        "cell_fall",
        "rise_transition",
        "fall_transition",
        "rise_constraint",
        "fall_constraint",
    }
)

ArcKey = Tuple[str, str, str, str, str, str, str]  # cell,pin,related,sense,type,when,table


def _arc_key_from_table(cell: str, t: dict) -> ArcKey:
    return (
        cell,
        str(t.get("pin") or NA),
        str(t.get("related_pin") or NA),
        str(t.get("timing_sense") or NA),
        str(t.get("timing_type") or NA),
        str(t.get("when") or NA),
        str(t.get("table_type") or NA),
    )


def arc_key_to_dict(key: ArcKey) -> Dict[str, str]:
    return {
        "cell": key[0],
        "pin": key[1],
        "related_pin": key[2],
        "timing_sense": key[3],
        "timing_type": key[4],
        "when": key[5],
        "table_type": key[6],
    }


def _collect_arcs(
    lib: Library,
    cells: Optional[Sequence[str]] = None,
    cell_pattern: Optional[str] = None,
    table_types: Optional[Sequence[str]] = None,
) -> Dict[ArcKey, dict]:
    names = set(lib.cell_names())
    if cell_pattern:
        names &= set(lib.select_cells(cell_pattern))
    if cells:
        names &= set(cells)
    tt_filter = set(table_types) if table_types else None
    out: Dict[ArcKey, dict] = {}
    for name in sorted(names):
        for t in lib.cell(name).timing_tables():
            if tt_filter and t.get("table_type") not in tt_filter:
                continue
            key = _arc_key_from_table(name, t)
            out[key] = t
    return out


def _pad_matrix(
    values: List[List[Optional[float]]], nrows: int, ncols: int
) -> List[List[Optional[float]]]:
    rows: List[List[Optional[float]]] = []
    for i in range(nrows):
        src = values[i] if i < len(values) else []
        row = [(src[j] if j < len(src) else None) for j in range(ncols)]
        rows.append(row)
    return rows


def _matrix_shape(values: List[List[Optional[float]]]) -> Tuple[int, int]:
    if not values:
        return 0, 0
    ncols = max((len(r) for r in values), default=0)
    return len(values), ncols


def delta_matrices(
    left: List[List[Optional[float]]],
    right: List[List[Optional[float]]],
) -> Dict[str, Any]:
    """Compute full Δ and % matrices (right - left). None cells stay None."""
    nr = max(_matrix_shape(left)[0], _matrix_shape(right)[0])
    nc = max(_matrix_shape(left)[1], _matrix_shape(right)[1])
    L = _pad_matrix(left or [], nr, nc)
    R = _pad_matrix(right or [], nr, nc)
    abs_m: List[List[Optional[float]]] = []
    rel_m: List[List[Optional[float]]] = []
    abs_vals: List[float] = []
    rel_vals: List[float] = []
    n_mismatch = 0
    n_compared = 0
    for i in range(nr):
        arow: List[Optional[float]] = []
        rrow: List[Optional[float]] = []
        for j in range(nc):
            a, b = L[i][j], R[i][j]
            if a is None or b is None:
                arow.append(None)
                rrow.append(None)
                if a is None and b is None:
                    pass
                else:
                    n_mismatch += 1
                continue
            n_compared += 1
            d = b - a
            arow.append(d)
            abs_vals.append(abs(d))
            if a == 0:
                pct = None if b == 0 else (float("inf") if b != 0 else 0.0)
                # treat exact both-zero as 0 rel
                if b == 0:
                    pct = 0.0
                else:
                    pct = None  # undefined relative
                rrow.append(pct)
                if pct is not None and math.isfinite(pct):
                    rel_vals.append(abs(pct))
            else:
                pct = d / a
                rrow.append(pct)
                rel_vals.append(abs(pct))
            if d != 0:
                n_mismatch += 1  # count any numeric difference as mismatch cell
        abs_m.append(arow)
        rel_m.append(rrow)

    def _rms(xs: List[float]) -> Optional[float]:
        if not xs:
            return None
        return math.sqrt(sum(x * x for x in xs) / len(xs))

    return {
        "abs_matrix": abs_m,
        "rel_matrix": rel_m,
        "nrows": nr,
        "ncols": nc,
        "stats": {
            "max_abs": max(abs_vals) if abs_vals else None,
            "max_rel": max(rel_vals) if rel_vals else None,
            "mean_abs": (sum(abs_vals) / len(abs_vals)) if abs_vals else None,
            "rms": _rms(abs_vals),
            "n_compared": n_compared,
            "n_mismatch": n_mismatch,
            "n_none": nr * nc - n_compared,
        },
    }


def index_alignment_status(
    left_i1: Sequence[float],
    left_i2: Sequence[float],
    right_i1: Sequence[float],
    right_i2: Sequence[float],
    tol: float = 1e-12,
) -> str:
    """Return 'aligned' | 'index_1_mismatch' | 'index_2_mismatch' | 'both_mismatch' | 'empty'.

    Both sides missing inline indices (common when Liberty only stores indices on
    lu_table_template) counts as aligned — value-matrix shape is compared separately.
    """
    l1, l2 = list(left_i1 or []), list(left_i2 or [])
    r1, r2 = list(right_i1 or []), list(right_i2 or [])
    if not l1 and not r1 and not l2 and not r2:
        return "aligned"  # template-only / no inline indices on either side

    def _eq(a: Sequence[float], b: Sequence[float]) -> bool:
        if len(a) != len(b):
            return False
        for x, y in zip(a, b):
            if abs(float(x) - float(y)) > tol:
                return False
        return True

    i1_ok = _eq(l1, r1)
    i2_ok = _eq(l2, r2)
    if i1_ok and i2_ok:
        return "aligned"
    if not i1_ok and not i2_ok:
        return "both_mismatch"
    if not i1_ok:
        return "index_1_mismatch"
    return "index_2_mismatch"


def check_monotonicity(
    values: List[List[Optional[float]]],
    *,
    along_rows: bool = True,
    along_cols: bool = True,
    allow_equal: bool = True,
) -> Dict[str, Any]:
    """Flag non-increasing steps (delay vs load / slew typically non-decreasing).

    along_cols: check each row left→right (index_2 / load axis)
    along_rows: check each column top→bottom (index_1 / slew axis)
    """
    violations: List[Dict[str, Any]] = []
    nr, nc = _matrix_shape(values)
    if along_cols:
        for i in range(nr):
            row = values[i] if i < len(values) else []
            prev = None
            for j, v in enumerate(row):
                if v is None:
                    prev = None
                    continue
                if prev is not None:
                    if allow_equal:
                        bad = v < prev
                    else:
                        bad = v <= prev
                    if bad:
                        violations.append(
                            {
                                "axis": "index_2",
                                "row": i,
                                "col": j,
                                "prev": prev,
                                "value": v,
                            }
                        )
                prev = v
    if along_rows:
        for j in range(nc):
            prev = None
            for i in range(nr):
                row = values[i] if i < len(values) else []
                v = row[j] if j < len(row) else None
                if v is None:
                    prev = None
                    continue
                if prev is not None:
                    if allow_equal:
                        bad = v < prev
                    else:
                        bad = v <= prev
                    if bad:
                        violations.append(
                            {
                                "axis": "index_1",
                                "row": i,
                                "col": j,
                                "prev": prev,
                                "value": v,
                            }
                        )
                prev = v
    return {
        "ok": len(violations) == 0,
        "n_violations": len(violations),
        "violations": violations[:50],  # cap for report size
    }


def check_table_sanity(values: List[List[Optional[float]]]) -> Dict[str, Any]:
    """Negative values, NaN, empty table flags."""
    if not values:
        return {"ok": False, "empty": True, "n_negative": 0, "n_nan": 0, "issues": ["empty"]}
    n_neg = 0
    n_nan = 0
    n_vals = 0
    for row in values:
        for v in row:
            if v is None:
                continue
            n_vals += 1
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                n_nan += 1
            elif v < 0:
                n_neg += 1
    issues = []
    if n_vals == 0:
        issues.append("empty")
    if n_neg:
        issues.append("negative")
    if n_nan:
        issues.append("nan_or_inf")
    return {
        "ok": not issues,
        "empty": n_vals == 0,
        "n_negative": n_neg,
        "n_nan": n_nan,
        "n_values": n_vals,
        "issues": issues,
    }


def single_lib_timing_qa(
    lib: Union[str, Library],
    cells: Optional[Sequence[str]] = None,
    cell_pattern: Optional[str] = None,
    table_types: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Optional single-library QA: monotonicity, negatives, empty/NaN tables."""
    library = lib if isinstance(lib, Library) else load_library(lib)
    arcs = _collect_arcs(library, cells=cells, cell_pattern=cell_pattern, table_types=table_types)
    results = []
    n_mono_fail = 0
    n_sanity_fail = 0
    for key, t in arcs.items():
        mono = check_monotonicity(t.get("values") or [])
        sanity = check_table_sanity(t.get("values") or [])
        if not mono["ok"]:
            n_mono_fail += 1
        if not sanity["ok"]:
            n_sanity_fail += 1
        results.append(
            {
                **arc_key_to_dict(key),
                "monotonicity": mono,
                "sanity": sanity,
                "status": "ok" if mono["ok"] and sanity["ok"] else "fail",
            }
        )
    return {
        "library": library.key,
        "n_arcs": len(results),
        "n_monotonicity_fail": n_mono_fail,
        "n_sanity_fail": n_sanity_fail,
        "arcs": results,
    }


def _exceeds_threshold(
    max_abs: Optional[float],
    max_rel: Optional[float],
    abs_tol: Optional[float],
    rel_tol: Optional[float],
) -> bool:
    if abs_tol is not None and max_abs is not None and max_abs > abs_tol:
        return True
    if rel_tol is not None and max_rel is not None and max_rel > rel_tol:
        return True
    return False


def timing_qa(
    left: Union[str, Library],
    right: Union[str, Library],
    cells: Optional[Sequence[str]] = None,
    cell_pattern: Optional[str] = None,
    table_types: Optional[Sequence[str]] = None,
    abs_tol: float = 1e-4,
    rel_tol: float = 0.01,
    include_matrices: bool = True,
    run_single_lib_qa: bool = False,
) -> Dict[str, Any]:
    """Compare timing arcs between two libraries; return structured QA report."""
    left_lib = left if isinstance(left, Library) else load_library(left)
    right_lib = right if isinstance(right, Library) else load_library(right)

    # Default to NLDM + constraint tables for matrix compare; still track others as missing/matched
    tt = list(table_types) if table_types else None

    left_arcs = _collect_arcs(left_lib, cells=cells, cell_pattern=cell_pattern, table_types=tt)
    right_arcs = _collect_arcs(right_lib, cells=cells, cell_pattern=cell_pattern, table_types=tt)

    all_keys = sorted(set(left_arcs) | set(right_arcs))
    matched: List[Dict[str, Any]] = []
    left_only: List[Dict[str, str]] = []
    right_only: List[Dict[str, str]] = []
    n_fail = 0
    n_index_mismatch = 0

    for key in all_keys:
        meta = arc_key_to_dict(key)
        lt = left_arcs.get(key)
        rt = right_arcs.get(key)
        if lt is None:
            right_only.append(meta)
            continue
        if rt is None:
            left_only.append(meta)
            continue

        align = index_alignment_status(
            lt.get("index_1") or [],
            lt.get("index_2") or [],
            rt.get("index_1") or [],
            rt.get("index_2") or [],
        )
        if align != "aligned":
            n_index_mismatch += 1

        dm = delta_matrices(lt.get("values") or [], rt.get("values") or [])
        stats = dm["stats"]
        fail = _exceeds_threshold(stats["max_abs"], stats["max_rel"], abs_tol, rel_tol)
        if fail:
            n_fail += 1
        status = "fail" if fail else "ok"
        if align != "aligned":
            status = "index_mismatch" if status == "ok" else status

        entry: Dict[str, Any] = {
            **meta,
            "status": status,
            "index_alignment": align,
            "max_abs": stats["max_abs"],
            "max_rel": stats["max_rel"],
            "mean_abs": stats["mean_abs"],
            "rms": stats["rms"],
            "n_mismatch": stats["n_mismatch"],
            "n_compared": stats["n_compared"],
            "exceeds_tol": fail,
            "index_1_left": list(lt.get("index_1") or []),
            "index_2_left": list(lt.get("index_2") or []),
            "index_1_right": list(rt.get("index_1") or []),
            "index_2_right": list(rt.get("index_2") or []),
        }
        if include_matrices:
            entry["abs_matrix"] = dm["abs_matrix"]
            entry["rel_matrix"] = dm["rel_matrix"]
            entry["values_left"] = lt.get("values") or []
            entry["values_right"] = rt.get("values") or []
        matched.append(entry)

    summary = {
        "n_arcs_matched": len(matched),
        "n_left_only": len(left_only),
        "n_right_only": len(right_only),
        "n_fail": n_fail,
        "n_index_mismatch": n_index_mismatch,
        "n_missing": len(left_only) + len(right_only),
        "abs_tol": abs_tol,
        "rel_tol": rel_tol,
    }

    report: Dict[str, Any] = {
        "left": left_lib.key,
        "right": right_lib.key,
        "summary": summary,
        "arcs": matched,
        "left_only": left_only,
        "right_only": right_only,
    }

    if run_single_lib_qa:
        report["left_qa"] = single_lib_timing_qa(
            left_lib, cells=cells, cell_pattern=cell_pattern, table_types=tt
        )
        report["right_qa"] = single_lib_timing_qa(
            right_lib, cells=cells, cell_pattern=cell_pattern, table_types=tt
        )

    return report


def export_timing_qa_json(report: Dict[str, Any], path: Optional[str] = None, indent: int = 2) -> str:
    text = json.dumps(report, indent=indent, default=str)
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return text


def export_timing_qa_csv(report: Dict[str, Any], path: Optional[str] = None) -> str:
    """Flat CSV of matched arcs + missing arc rows."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
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
        ]
    )
    for a in report.get("arcs") or []:
        writer.writerow(
            [
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
            ]
        )
    for a in report.get("left_only") or []:
        writer.writerow(
            [
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
            ]
        )
    for a in report.get("right_only") or []:
        writer.writerow(
            [
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
            ]
        )
    text = buf.getvalue()
    if path:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    return text


def format_timing_qa_summary(report: Dict[str, Any]) -> str:
    s = report.get("summary") or {}
    lines = [
        "Timing QA (Liberty / NLDM)",
        "left : %s" % report.get("left"),
        "right: %s" % report.get("right"),
        "matched arcs : %s" % s.get("n_arcs_matched"),
        "fail (tol)   : %s  (abs_tol=%s rel_tol=%s)"
        % (s.get("n_fail"), s.get("abs_tol"), s.get("rel_tol")),
        "left-only    : %s" % s.get("n_left_only"),
        "right-only   : %s" % s.get("n_right_only"),
        "index mismatch: %s" % s.get("n_index_mismatch"),
    ]
    # top offenders
    fails = [a for a in (report.get("arcs") or []) if a.get("exceeds_tol")]
    fails.sort(key=lambda a: (a.get("max_abs") is None, -(a.get("max_abs") or 0)))
    if fails:
        lines.append("top fails:")
        for a in fails[:10]:
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



# Re-export batch / HTML helpers (kept in timing_qa_batch to keep this module focused)
from libdiff.compare.timing_qa_batch import (  # noqa: E402
    run_timing_qa_batch,
    export_timing_qa_batch_csv,
    export_timing_qa_html,
    format_timing_qa_batch_summary,
)

__all__ = [
    "NLDM_TABLE_TYPES",
    "KNOWN_TIMING_TABLES",
    "delta_matrices",
    "index_alignment_status",
    "check_monotonicity",
    "check_table_sanity",
    "single_lib_timing_qa",
    "timing_qa",
    "export_timing_qa_json",
    "export_timing_qa_csv",
    "format_timing_qa_summary",
    "run_timing_qa_batch",
    "export_timing_qa_batch_csv",
    "export_timing_qa_html",
    "format_timing_qa_batch_summary",
    "arc_key_to_dict",
]
