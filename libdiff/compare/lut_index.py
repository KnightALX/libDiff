"""Physical-index LUT sampling, cross-index resampling, and 1D/2D helpers.

Grounded in Liberty practice: index_1 = input_net_transition (slew),
index_2 = total_output_net_capacitance (load) for timing templates such as
tmg_ntin_oload_*; constraint templates use constrained/related pin transitions.
1D tables have only index_1. Never compare only by matrix cell [i][j] when
physical indices differ — align on coordinates via linear/bilinear resample.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

TableLike = Dict[str, Any]
IndexVec = List[float]
Matrix = List[List[Optional[float]]]


def classify_lut(table: Optional[TableLike]) -> str:
    """Classify a timing/power LUT as '1d', '2d', or 'empty'."""
    if not table:
        return "empty"
    values = table.get("values") or []
    if not values:
        return "empty"
    i2 = table.get("index_2") or []
    nrows = len(values)
    ncols = max((len(r) for r in values), default=0)
    # Explicit index_2 with width>1 ⇒ 2D. Lone index_1 (constraint) ⇒ 1D even if
    # values are stored as a single multi-column row.
    if i2 and ncols > 1 and nrows >= 1:
        return "2d"
    if ncols <= 1:
        return "1d" if nrows else "empty"
    if nrows == 1:
        return "1d"
    if nrows > 1 and ncols > 1:
        # 2D values without inline index_2 (template-only) still count as 2D
        return "2d"
    return "1d"


def _as_float_list(raw: Any) -> IndexVec:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        out: IndexVec = []
        for x in raw:
            try:
                out.append(float(x))
            except (TypeError, ValueError):
                continue
        return out
    return []


def resolve_indices(
    lib: Any,
    table: TableLike,
) -> Tuple[IndexVec, IndexVec, Optional[str], Optional[str], Optional[str]]:
    """Resolve physical index vectors for a table.

    Uses inline index_1/index_2 when present; otherwise falls back to the
    library ``lu_table_template`` / ``power_lut_template`` named by the table
    group (``template_name``).

    Returns (index_1, index_2, template_name, variable_1, variable_2).
    """
    i1 = _as_float_list(table.get("index_1"))
    i2 = _as_float_list(table.get("index_2"))
    tname = table.get("template_name") or table.get("template") or None
    if isinstance(tname, str):
        tname = tname.strip() or None
    else:
        tname = None
    v1 = table.get("variable_1")
    v2 = table.get("variable_2")

    need_template = (not i1) or (classify_lut(table) == "2d" and not i2 and (table.get("values") or [[]]) and max(len(r) for r in (table.get("values") or [[]])) > 1)
    if lib is not None and tname and (need_template or v1 is None):
        templates = {}
        if hasattr(lib, "lut_templates"):
            templates = lib.lut_templates() or {}
        elif isinstance(lib, dict):
            templates = lib
        tmpl = templates.get(tname) or {}
        if not i1:
            i1 = _as_float_list(tmpl.get("index_1"))
        if not i2:
            i2 = _as_float_list(tmpl.get("index_2"))
        if v1 is None:
            v1 = tmpl.get("variable_1")
        if v2 is None:
            v2 = tmpl.get("variable_2")

    # If still missing indices, synthesize positional grid from values shape.
    # Do NOT invent index_2 for single-row (1D constraint) tables.
    values = table.get("values") or []
    nrows = len(values)
    ncols = max((len(r) for r in values), default=0) if values else 0
    looks_1d = (not i2) and (ncols <= 1 or nrows <= 1)
    if not i1:
        if looks_1d and nrows == 1 and ncols > 1:
            i1 = [float(j) for j in range(ncols)]
        elif nrows:
            i1 = [float(i) for i in range(nrows)]
    if not i2 and ncols > 1 and nrows > 1:
        i2 = [float(j) for j in range(ncols)]

    return i1, i2, tname, (str(v1) if v1 is not None else None), (str(v2) if v2 is not None else None)


def _find_bracket(xs: Sequence[float], x: float) -> Optional[Tuple[int, int, float]]:
    """Return (i0, i1, t) for linear interpolation, or None if out of range.

    Exact hits return (i, i, 0.0). No extrapolation.
    """
    if not xs:
        return None
    n = len(xs)
    # allow tiny tolerance at endpoints
    lo, hi = float(xs[0]), float(xs[-1])
    if x < lo - 1e-15 or x > hi + 1e-15:
        return None
    if n == 1:
        if abs(x - xs[0]) <= 1e-12:
            return 0, 0, 0.0
        return None
    # assume monotonic increasing (Liberty convention)
    ascending = xs[-1] >= xs[0]
    if ascending:
        if x <= xs[0]:
            return 0, 0, 0.0
        if x >= xs[-1]:
            return n - 1, n - 1, 0.0
        for i in range(n - 1):
            a, b = float(xs[i]), float(xs[i + 1])
            if a <= x <= b or b <= x <= a:
                if abs(b - a) < 1e-30:
                    return i, i, 0.0
                t = (x - a) / (b - a)
                return i, i + 1, t
    else:
        # descending
        if x >= xs[0]:
            return 0, 0, 0.0
        if x <= xs[-1]:
            return n - 1, n - 1, 0.0
        for i in range(n - 1):
            a, b = float(xs[i]), float(xs[i + 1])
            if (a >= x >= b) or (b >= x >= a):
                if abs(b - a) < 1e-30:
                    return i, i, 0.0
                t = (x - a) / (b - a)
                return i, i + 1, t
    return None


def _cell(values: Matrix, i: int, j: int) -> Optional[float]:
    if i < 0 or i >= len(values):
        return None
    row = values[i]
    if j < 0 or j >= len(row):
        return None
    v = row[j]
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if isinstance(f, float) and (math.isnan(f) or math.isinf(f)):
        return None
    return f


def sample_lut(
    values: Matrix,
    index_1: Sequence[float],
    index_2: Optional[Sequence[float]],
    x1: float,
    x2: Optional[float] = None,
) -> Optional[float]:
    """Sample LUT at physical (x1, x2) via linear (1D) / bilinear (2D).

    No extrapolation: returns None when the query is outside index bounds
    or any required corner value is missing.
    """
    if not values:
        return None
    i1 = list(index_1 or [])
    i2 = list(index_2 or []) if index_2 is not None else []

    # Detect 1D: no index_2 or single-column values
    ncols = max((len(r) for r in values), default=0)
    is_1d = (not i2) or ncols <= 1

    if is_1d:
        # values may be Nx1 or 1xN
        if ncols <= 1:
            # column vector along index_1
            br = _find_bracket(i1, float(x1))
            if br is None:
                return None
            r0, r1, t = br
            v0 = _cell(values, r0, 0)
            if r0 == r1:
                return v0
            v1 = _cell(values, r1, 0)
            if v0 is None or v1 is None:
                return None
            return v0 * (1.0 - t) + v1 * t
        else:
            # single row along index_1 (or use index_2 if provided as free axis)
            axis = i1 if len(i1) == ncols else (i2 if len(i2) == ncols else i1)
            br = _find_bracket(axis, float(x1 if x2 is None else (x2 if len(i1) != ncols else x1)))
            # Prefer x1 against the axis we have
            query = float(x1)
            if len(i1) != ncols and i2 and len(i2) == ncols and x2 is not None:
                query = float(x2)
                axis = i2
            br = _find_bracket(axis, query)
            if br is None:
                return None
            c0, c1, t = br
            v0 = _cell(values, 0, c0)
            if c0 == c1:
                return v0
            v1 = _cell(values, 0, c1)
            if v0 is None or v1 is None:
                return None
            return v0 * (1.0 - t) + v1 * t

    # 2D bilinear
    if x2 is None:
        return None
    if not i1 or not i2:
        return None
    br1 = _find_bracket(i1, float(x1))
    br2 = _find_bracket(i2, float(x2))
    if br1 is None or br2 is None:
        return None
    r0, r1, t1 = br1
    c0, c1, t2 = br2
    v00 = _cell(values, r0, c0)
    if r0 == r1 and c0 == c1:
        return v00
    v01 = _cell(values, r0, c1)
    v10 = _cell(values, r1, c0)
    v11 = _cell(values, r1, c1)
    corners = [v00, v01, v10, v11]
    if any(v is None for v in corners):
        return None
    # bilinear
    return (
        v00 * (1.0 - t1) * (1.0 - t2)
        + v01 * (1.0 - t1) * t2
        + v10 * t1 * (1.0 - t2)
        + v11 * t1 * t2
    )


def resample_to_grid(
    src_i1: Sequence[float],
    src_i2: Optional[Sequence[float]],
    src_values: Matrix,
    dst_i1: Sequence[float],
    dst_i2: Optional[Sequence[float]],
) -> Matrix:
    """Resample source LUT onto destination physical grid (no extrapolate → None)."""
    d1 = list(dst_i1 or [])
    d2 = list(dst_i2 or []) if dst_i2 is not None else []
    s1 = list(src_i1 or [])
    s2 = list(src_i2 or []) if src_i2 is not None else []
    if not d1:
        return []
    if d2:
        out: Matrix = []
        for x1 in d1:
            row: List[Optional[float]] = []
            for x2 in d2:
                row.append(sample_lut(src_values, s1, s2, float(x1), float(x2)))
            out.append(row)
        return out
    # 1D destination
    out = []
    for x1 in d1:
        v = sample_lut(src_values, s1, s2, float(x1), None)
        out.append([v])
    return out


def _union_sorted(a: Sequence[float], b: Sequence[float], tol: float = 1e-12) -> IndexVec:
    merged = sorted(float(x) for x in list(a or []) + list(b or []))
    out: IndexVec = []
    for x in merged:
        if not out or abs(out[-1] - x) > tol:
            out.append(x)
    return out


def _intersect_sorted(a: Sequence[float], b: Sequence[float], tol: float = 1e-9) -> IndexVec:
    aa = sorted(float(x) for x in (a or []))
    bb = sorted(float(x) for x in (b or []))
    out: IndexVec = []
    j = 0
    for x in aa:
        while j < len(bb) and bb[j] < x - tol:
            j += 1
        if j < len(bb) and abs(bb[j] - x) <= tol:
            if not out or abs(out[-1] - x) > tol:
                out.append(x)
            j += 1
    return out


def cross_index_delta(
    left_table: TableLike,
    right_table: TableLike,
    mode: str = "left_grid",
    query_i1: Optional[Sequence[float]] = None,
    query_i2: Optional[Sequence[float]] = None,
    left_lib: Any = None,
    right_lib: Any = None,
) -> Dict[str, Any]:
    """Compare two LUTs on a shared physical grid via resampling.

    mode:
      - left_grid: use left indices as reference
      - union: union of index values
      - intersection: intersection of index values
      - query: use query_i1 / query_i2

    Returns abs/rel matrices, alignment meta, out_of_range counts.
    """
    li1, li2, ltname, lv1, lv2 = resolve_indices(left_lib, left_table)
    ri1, ri2, rtname, rv1, rv2 = resolve_indices(right_lib, right_table)
    left_cls = classify_lut(left_table)
    right_cls = classify_lut(right_table)

    # Decide dimensionality of compare grid
    left_2d = left_cls == "2d" and bool(li2)
    right_2d = right_cls == "2d" and bool(ri2)
    want_2d = left_2d or right_2d

    mode_l = (mode or "left_grid").lower()
    if mode_l == "query":
        dst_i1 = list(query_i1 or li1)
        dst_i2 = list(query_i2 or li2) if want_2d else []
    elif mode_l == "union":
        dst_i1 = _union_sorted(li1, ri1)
        dst_i2 = _union_sorted(li2, ri2) if want_2d else []
    elif mode_l == "intersection":
        dst_i1 = _intersect_sorted(li1, ri1)
        dst_i2 = _intersect_sorted(li2, ri2) if want_2d else []
    else:  # left_grid
        dst_i1 = list(li1)
        dst_i2 = list(li2) if want_2d else []

    lvals = left_table.get("values") or []
    rvals = right_table.get("values") or []
    left_r = resample_to_grid(li1, li2, lvals, dst_i1, dst_i2 if want_2d else None)
    right_r = resample_to_grid(ri1, ri2, rvals, dst_i1, dst_i2 if want_2d else None)

    nr = len(dst_i1)
    nc = len(dst_i2) if want_2d and dst_i2 else 1
    abs_m: Matrix = []
    rel_m: Matrix = []
    abs_vals: List[float] = []
    rel_vals: List[float] = []
    n_compared = 0
    n_oor_left = 0
    n_oor_right = 0
    n_oor_both = 0

    for i in range(nr):
        arow: List[Optional[float]] = []
        rrow: List[Optional[float]] = []
        for j in range(nc):
            lv = left_r[i][j] if i < len(left_r) and j < len(left_r[i]) else None
            rv = right_r[i][j] if i < len(right_r) and j < len(right_r[i]) else None
            if lv is None and rv is None:
                n_oor_both += 1
                arow.append(None)
                rrow.append(None)
                continue
            if lv is None:
                n_oor_left += 1
                arow.append(None)
                rrow.append(None)
                continue
            if rv is None:
                n_oor_right += 1
                arow.append(None)
                rrow.append(None)
                continue
            n_compared += 1
            d = rv - lv
            arow.append(d)
            abs_vals.append(abs(d))
            if lv == 0:
                pct = 0.0 if rv == 0 else None
            else:
                pct = d / lv
            rrow.append(pct)
            if pct is not None and math.isfinite(pct):
                rel_vals.append(abs(pct))
        abs_m.append(arow)
        rel_m.append(rrow)

    def _rms(xs: List[float]) -> Optional[float]:
        if not xs:
            return None
        return math.sqrt(sum(x * x for x in xs) / len(xs))

    aligned = (
        len(li1) == len(ri1)
        and all(abs(a - b) <= 1e-12 for a, b in zip(li1, ri1))
        and len(li2) == len(ri2)
        and all(abs(a - b) <= 1e-12 for a, b in zip(li2, ri2))
    )

    return {
        "mode": mode_l,
        "classification": {"left": left_cls, "right": right_cls},
        "index_1": dst_i1,
        "index_2": dst_i2,
        "values_left": left_r,
        "values_right": right_r,
        "abs_matrix": abs_m,
        "rel_matrix": rel_m,
        "nrows": nr,
        "ncols": nc,
        "aligned": aligned,
        "templates": {"left": ltname, "right": rtname},
        "variables": {
            "left": {"variable_1": lv1, "variable_2": lv2},
            "right": {"variable_1": rv1, "variable_2": rv2},
        },
        "out_of_range": {
            "left": n_oor_left,
            "right": n_oor_right,
            "both": n_oor_both,
            "total": n_oor_left + n_oor_right + n_oor_both,
        },
        "stats": {
            "max_abs": max(abs_vals) if abs_vals else None,
            "max_rel": max(rel_vals) if rel_vals else None,
            "mean_abs": (sum(abs_vals) / len(abs_vals)) if abs_vals else None,
            "rms": _rms(abs_vals),
            "n_compared": n_compared,
            "n_none": nr * nc - n_compared,
        },
        "source_indices": {
            "left_index_1": li1,
            "left_index_2": li2,
            "right_index_1": ri1,
            "right_index_2": ri2,
        },
    }


def _nearest_index(xs: Sequence[float], x: float) -> int:
    best_i = 0
    best_d = float("inf")
    for i, v in enumerate(xs):
        d = abs(float(v) - float(x))
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def slice_curve(
    table: TableLike,
    axis: str = "index_1",
    fixed_value: Optional[float] = None,
    method: str = "nearest",
    lib: Any = None,
) -> Tuple[List[float], List[Optional[float]]]:
    """Slice a 2D LUT to a 1D curve by fixing one axis at a physical value.

    axis: free axis ('index_1' or 'index_2').
    Returns (xs, ys) along the free axis.
    """
    i1, i2, _, _, _ = resolve_indices(lib, table)
    values = table.get("values") or []
    cls = classify_lut(table)
    if cls == "empty":
        return [], []
    if cls == "1d":
        # already 1D — ignore fixed_value
        if i2 and not i1:
            xs = list(i2)
            ys = [(_cell(values, 0, j) if values else None) for j in range(len(xs))]
            return xs, ys
        xs = list(i1)
        if values and max(len(r) for r in values) > 1 and len(values) == 1:
            ys = [_cell(values, 0, j) for j in range(len(xs))]
        else:
            ys = [_cell(values, i, 0) for i in range(len(xs))]
        return xs, ys

    if fixed_value is None:
        fixed_value = float(i1[0]) if axis == "index_2" and i1 else (float(i2[0]) if i2 else 0.0)

    method_l = (method or "nearest").lower()
    if axis == "index_2":
        # free axis = index_2 (load); fix index_1 (slew)
        xs = list(i2)
        ys: List[Optional[float]] = []
        if method_l == "interp":
            for x2 in xs:
                ys.append(sample_lut(values, i1, i2, float(fixed_value), float(x2)))
        else:
            ri = _nearest_index(i1, float(fixed_value))
            for j in range(len(xs)):
                ys.append(_cell(values, ri, j))
        return xs, ys
    else:
        # free axis = index_1 (slew); fix index_2 (load)
        xs = list(i1)
        ys = []
        if method_l == "interp":
            for x1 in xs:
                ys.append(sample_lut(values, i1, i2, float(x1), float(fixed_value)))
        else:
            ci = _nearest_index(i2, float(fixed_value)) if i2 else 0
            for i in range(len(xs)):
                ys.append(_cell(values, i, ci))
        return xs, ys


def probe_points(
    table: TableLike,
    points: List[Tuple[float, Optional[float]]],
    lib: Any = None,
) -> List[Dict[str, Any]]:
    """Probe LUT at a list of physical (x1, x2) points."""
    i1, i2, tname, v1, v2 = resolve_indices(lib, table)
    values = table.get("values") or []
    cls = classify_lut(table)
    out: List[Dict[str, Any]] = []
    for pt in points:
        x1 = float(pt[0])
        x2 = float(pt[1]) if pt[1] is not None else None
        val = sample_lut(values, i1, i2, x1, x2)
        out.append(
            {
                "x1": x1,
                "x2": x2,
                "value": val,
                "out_of_range": val is None,
                "classification": cls,
                "template_name": tname,
                "variable_1": v1,
                "variable_2": v2,
            }
        )
    return out




def quantile_index(index_vals: Sequence[float], q: float = 0.33) -> float:
    """Physical value at fraction ``q`` along an ordered index vector.

    Interpolates linearly between surrounding knots. ``q=0.33`` is the
    GUI default 「33点」. Empty vector returns 0.0; single knot returns that knot.
    ``q`` is clamped to [0, 1].
    """
    xs = [float(x) for x in (index_vals or [])]
    if not xs:
        return 0.0
    if len(xs) == 1:
        return xs[0]
    qq = max(0.0, min(1.0, float(q)))
    pos = qq * (len(xs) - 1)
    i0 = int(math.floor(pos))
    i1 = min(i0 + 1, len(xs) - 1)
    t = pos - i0
    return xs[i0] * (1.0 - t) + xs[i1] * t


def marginal_delta_stats(
    abs_or_signed_matrix: Matrix,
    index_1: Sequence[float],
    index_2: Sequence[float],
) -> Dict[str, Any]:
    """Collapse a Δ matrix to marginal mean / max(|·|) curves.

    Returns::
        {
          "by_i1": {"xs": [...], "mean": [...], "maxabs": [...], "mean_abs": [...]},
          "by_i2": {"xs": [...], "mean": [...], "maxabs": [...], "mean_abs": [...]},
        }

    ``mean`` is mean of signed values (None cells skipped).
    ``mean_abs`` is mean(|Δ|); ``maxabs`` is max(|Δ|).
    """
    i1 = [float(x) for x in (index_1 or [])]
    i2 = [float(x) for x in (index_2 or [])]
    mat = abs_or_signed_matrix or []

    def _row_stats(row: Sequence[Optional[float]]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        vals = []
        for v in row:
            if v is None:
                continue
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if math.isnan(f) or math.isinf(f):
                continue
            vals.append(f)
        if not vals:
            return None, None, None
        mean_s = sum(vals) / len(vals)
        abs_vals = [abs(v) for v in vals]
        return mean_s, sum(abs_vals) / len(abs_vals), max(abs_vals)

    by_i1_mean: List[Optional[float]] = []
    by_i1_mean_abs: List[Optional[float]] = []
    by_i1_max: List[Optional[float]] = []
    xs_i1: List[float] = []
    for i, x in enumerate(i1):
        row = mat[i] if i < len(mat) else []
        # If 1-col matrix without index_2, still collapse that single col
        if not i2 and row and not isinstance(row, (list, tuple)):
            row = [row]
        m, ma, mx = _row_stats(list(row) if row is not None else [])
        xs_i1.append(float(x))
        by_i1_mean.append(m)
        by_i1_mean_abs.append(ma)
        by_i1_max.append(mx)

    by_i2_mean: List[Optional[float]] = []
    by_i2_mean_abs: List[Optional[float]] = []
    by_i2_max: List[Optional[float]] = []
    xs_i2: List[float] = []
    ncols = len(i2) if i2 else (max((len(r) for r in mat), default=0) if mat else 0)
    for j in range(ncols):
        col: List[Optional[float]] = []
        for i in range(len(mat)):
            row = mat[i]
            if j < len(row):
                col.append(row[j])
            else:
                col.append(None)
        m, ma, mx = _row_stats(col)
        xs_i2.append(float(i2[j]) if j < len(i2) else float(j))
        by_i2_mean.append(m)
        by_i2_mean_abs.append(ma)
        by_i2_max.append(mx)

    return {
        "by_i1": {
            "xs": xs_i1,
            "mean": by_i1_mean,
            "mean_abs": by_i1_mean_abs,
            "maxabs": by_i1_max,
        },
        "by_i2": {
            "xs": xs_i2,
            "mean": by_i2_mean,
            "mean_abs": by_i2_mean_abs,
            "maxabs": by_i2_max,
        },
    }


def lut_view_payload(
    left_table: TableLike,
    right_table: Optional[TableLike] = None,
    *,
    view_mode: str = "point",
    line_fix_axis: str = "index_1",
    x1: Optional[float] = None,
    x2: Optional[float] = None,
    cross_mode: str = "left_grid",
    use_cross: bool = True,
    left_lib: Any = None,
    right_lib: Any = None,
    denser: int = 0,
) -> Dict[str, Any]:
    """GUI-less payload for Point / Line / Surface Timing-LUT views.

    view_mode: 'point' | 'line' | 'surface'
    line_fix_axis: which axis is fixed when view_mode=='line' ('index_1' or 'index_2').
    denser: if >0 on Line, resample free axis to that many points (inclusive endpoints).
    """
    mode = (view_mode or "point").lower()
    if mode in ("单点", "point", "probe"):
        mode = "point"
    elif mode in ("扫线", "line", "slice"):
        mode = "line"
    elif mode in ("扫面", "surface", "heatmap", "full"):
        mode = "surface"
    else:
        mode = "point"

    li1, li2, ltname, lv1, lv2 = resolve_indices(left_lib, left_table)
    cls = classify_lut(left_table)
    if x1 is None:
        x1 = quantile_index(li1, 0.33) if li1 else 0.0
    if x2 is None and li2:
        x2 = quantile_index(li2, 0.33)

    out: Dict[str, Any] = {
        "view_mode": mode,
        "classification": cls,
        "template": ltname,
        "variables": {"variable_1": lv1, "variable_2": lv2},
        "x1": x1,
        "x2": x2,
        "index_1": list(li1),
        "index_2": list(li2),
    }

    if mode == "point":
        lv = sample_lut(left_table.get("values") or [], li1, li2, float(x1), float(x2) if cls == "2d" and x2 is not None else None)
        rv = None
        if right_table is not None:
            ri1, ri2, _, _, _ = resolve_indices(right_lib, right_table)
            rcls = classify_lut(right_table)
            rv = sample_lut(
                right_table.get("values") or [],
                ri1,
                ri2,
                float(x1),
                float(x2) if rcls == "2d" and x2 is not None else None,
            )
        delta = None if lv is None or rv is None else (rv - lv)
        pct = None
        if delta is not None and lv not in (None, 0):
            pct = delta / lv
        out["point"] = {"left": lv, "right": rv, "delta": delta, "pct": pct}
        return out

    if mode == "line":
        fix_axis = (line_fix_axis or "index_1").lower()
        if "index_2" in fix_axis or fix_axis.endswith("2"):
            free_axis = "index_1"
            fixed_value = float(x2) if x2 is not None else quantile_index(li2, 0.33)
            fixed_axis = "index_2"
        else:
            free_axis = "index_2" if cls == "2d" and li2 else "index_1"
            fixed_value = float(x1) if x1 is not None else quantile_index(li1, 0.33)
            fixed_axis = "index_1"
            if cls == "1d":
                free_axis = "index_1"
                fixed_axis = "none"
                fixed_value = None

        xs_l, ys_l = slice_curve(
            left_table,
            axis=free_axis if cls == "2d" else "index_1",
            fixed_value=fixed_value,
            method="interp",
            lib=left_lib,
        )
        if denser and denser > 1 and len(xs_l) >= 2:
            lo, hi = float(xs_l[0]), float(xs_l[-1])
            xs_dense = [lo + (hi - lo) * k / (denser - 1) for k in range(denser)]
            vals = left_table.get("values") or []
            ys_dense: List[Optional[float]] = []
            for xv in xs_dense:
                if free_axis == "index_2":
                    ys_dense.append(sample_lut(vals, li1, li2, float(fixed_value), float(xv)))
                else:
                    ys_dense.append(sample_lut(vals, li1, li2, float(xv), float(fixed_value) if fixed_value is not None else None))
            xs_l, ys_l = xs_dense, ys_dense

        series: Dict[str, List[Optional[float]]] = {"left": ys_l}
        ys_r: Optional[List[Optional[float]]] = None
        if right_table is not None:
            xs_r, ys_r = slice_curve(
                right_table,
                axis=free_axis if classify_lut(right_table) == "2d" else "index_1",
                fixed_value=fixed_value,
                method="interp",
                lib=right_lib,
            )
            # resample right onto left xs when lengths differ
            if denser and denser > 1:
                ri1, ri2, _, _, _ = resolve_indices(right_lib, right_table)
                rvals = right_table.get("values") or []
                ys_r = []
                for xv in xs_l:
                    if free_axis == "index_2":
                        ys_r.append(sample_lut(rvals, ri1, ri2, float(fixed_value), float(xv)))
                    else:
                        ys_r.append(sample_lut(rvals, ri1, ri2, float(xv), float(fixed_value) if fixed_value is not None else None))
            series["right"] = ys_r
            delta_y: List[Optional[float]] = []
            for a, b in zip(ys_l, ys_r or []):
                if a is None or b is None:
                    delta_y.append(None)
                else:
                    delta_y.append(b - a)
            series["delta"] = delta_y
        out["line"] = {
            "xs": xs_l,
            "series": series,
            "free_axis": free_axis,
            "fixed_axis": fixed_axis,
            "fixed_value": fixed_value,
        }
        return out

    # surface
    if right_table is not None and use_cross:
        dm = cross_index_delta(
            left_table, right_table, mode=cross_mode, left_lib=left_lib, right_lib=right_lib
        )
        marg = marginal_delta_stats(dm["abs_matrix"], dm["index_1"], dm["index_2"])
        out["surface"] = {
            "values_left": dm["values_left"],
            "values_right": dm["values_right"],
            "abs_matrix": dm["abs_matrix"],
            "index_1": dm["index_1"],
            "index_2": dm["index_2"],
            "marginals": marg,
            "stats": dm.get("stats"),
            "cross_mode": cross_mode,
        }
    else:
        marg = None
        abs_m = None
        if right_table is not None:
            lv = left_table.get("values") or []
            rv = right_table.get("values") or []
            abs_m = []
            for i, row in enumerate(lv):
                arow: List[Optional[float]] = []
                rrow = rv[i] if i < len(rv) else []
                for j, a in enumerate(row):
                    b = rrow[j] if j < len(rrow) else None
                    if a is None or b is None:
                        arow.append(None)
                    else:
                        try:
                            arow.append(float(b) - float(a))
                        except (TypeError, ValueError):
                            arow.append(None)
                abs_m.append(arow)
            marg = marginal_delta_stats(abs_m, li1, li2)
        out["surface"] = {
            "values_left": left_table.get("values") or [],
            "values_right": (right_table.get("values") if right_table else None),
            "abs_matrix": abs_m,
            "index_1": list(li1),
            "index_2": list(li2),
            "marginals": marg,
            "stats": None,
            "cross_mode": "positional" if not use_cross else cross_mode,
        }
    return out


__all__ = [
    "classify_lut",
    "resolve_indices",
    "sample_lut",
    "resample_to_grid",
    "cross_index_delta",
    "slice_curve",
    "probe_points",
    "quantile_index",
    "marginal_delta_stats",
    "lut_view_payload",
]
