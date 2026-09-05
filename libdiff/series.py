"""Cell drive-strength / series grouping helpers (stdcell naming).

Shared by GUI sort and PPA series-aware charts. Patterns cover common foundry /
open-source styles: INVX1, inv_x2, iv1v0x4, *D8BWP*, etc.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# (compiled_regex, size_group_index) — group 1 is family prefix, size_gi is drive
DEFAULT_SERIES_PATTERNS: List[Tuple[re.Pattern, int]] = [
    (re.compile(r"^(.+?)D(\d+)(BWP.*)$"), 2),
    # pharosc-style: inv_x1, a2_x4
    (re.compile(r"^(.+?)_x(\d+)$", re.IGNORECASE), 2),
    # pharosc-style: iv1v0x2, nd2v0x4, aoi21v0x1
    (re.compile(r"^(.+?)v\d+x(\d+)$", re.IGNORECASE), 2),
    # INVX1 / NOR2X4
    (re.compile(r"^(.+?)X(\d+)$", re.IGNORECASE), 2),
    (re.compile(r"^(.+?)_(\d+)$"), 2),
]


def match_cell_series(
    cell_name: str,
    patterns: Optional[Sequence[Tuple[re.Pattern, int]]] = None,
) -> Optional[Tuple[str, int]]:
    """Return (family_key, drive_size) if cell matches a series pattern, else None."""
    patterns = patterns or DEFAULT_SERIES_PATTERNS
    for cre, size_gi in patterns:
        m = cre.match(cell_name)
        if m:
            parts = list(m.groups())
            size_idx = size_gi - 1
            key_parts = parts[:size_idx] + parts[size_idx + 1 :]
            key = "".join(key_parts)
            return key, int(m.group(size_gi))
    return None


def group_cells_by_series(
    cell_names: Iterable[str],
    patterns: Optional[Sequence[Tuple[re.Pattern, int]]] = None,
    *,
    min_family_size: int = 2,
) -> OrderedDict:
    """Group cells into drive families.

    Returns OrderedDict: family_key -> list of (drive_size, cell_name) sorted by size.
    Orphans (no match or singleton families when min_family_size>1) land under
    key ``_other`` as a flat list of cell names (no size tuples).
    """
    patterns = patterns or DEFAULT_SERIES_PATTERNS
    series: OrderedDict = OrderedDict()
    other: List[str] = []
    for cell_name in cell_names:
        hit = match_cell_series(cell_name, patterns)
        if hit is None:
            other.append(cell_name)
            continue
        key, size = hit
        series.setdefault(key, []).append((size, cell_name))

    out: OrderedDict = OrderedDict()
    for key in sorted(series.keys()):
        items = sorted(series[key], key=lambda t: t[0])
        if len(items) < min_family_size:
            other.extend([c for _, c in items])
        else:
            out[key] = items
    out["_other"] = sorted(other)
    return out


def sort_cells_with_size(orig_cell_list, patterns=None):
    """Stable series-aware sort used by the Fluent GUI tree / combos."""
    patterns = patterns or DEFAULT_SERIES_PATTERNS
    series = OrderedDict()
    series["zzz"] = []
    for cell_name in orig_cell_list:
        matched = False
        for cre, size_gi in patterns:
            m = cre.match(cell_name)
            if m:
                parts = list(m.groups())
                size_idx = size_gi - 1
                key_parts = parts[:size_idx] + parts[size_idx + 1 :]
                key = "".join(key_parts)
                series.setdefault(key, []).append((int(m.group(size_gi)), cell_name))
                matched = True
                break
        if not matched:
            series["zzz"].append(cell_name)
    for key in list(series.keys()):
        if key == "zzz":
            continue
        if len(series[key]) == 1:
            series["zzz"].append(series[key][0][1])
            series.pop(key)
    out = []
    for key in sorted(series.keys()):
        items = series[key]
        if key == "zzz":
            items = sorted(items)
            out.extend(items)
        else:
            items = sorted(items, key=lambda t: t[0])
            out.extend([c for _, c in items])
    return out


__all__ = [
    "DEFAULT_SERIES_PATTERNS",
    "match_cell_series",
    "group_cells_by_series",
    "sort_cells_with_size",
]
