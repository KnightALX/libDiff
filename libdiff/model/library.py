
"""Library / cell model keyed by absolute path with N/A-safe accessors."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Sequence, Union

from libdiff.errors import ParseError
from libdiff.parser.liberty import LibertyParser, safe_float, _strip_quotes, clear_parse_cache

NA = "N/A"

# Known timing LUT group types (correct OCV *constraint* spelling included).
KNOWN_TIMING_TABLES = {
    "cell_rise",
    "rise_transition",
    "cell_fall",
    "fall_transition",
    "rise_constraint",
    "fall_constraint",
    "ocv_sigma_rise_constraint",
    "ocv_sigma_fall_constraint",
    "ocv_sigma_rise_transition",
    "ocv_sigma_fall_transition",
    "ocv_sigma_cell_rise",
    "ocv_sigma_cell_fall",
    # common CCS / receiver / current tables — keep rather than drop
    "output_current_rise",
    "output_current_fall",
    "receiver_capacitance1_rise",
    "receiver_capacitance1_fall",
    "receiver_capacitance2_rise",
    "receiver_capacitance2_fall",
}

# Legacy misspellings map to corrected names when normalizing
OCV_SPELLING_FIX = {
    "ocv_sigma_rise_contraint": "ocv_sigma_rise_constraint",
    "ocv_sigma_fall_contraint": "ocv_sigma_fall_constraint",
}


def _parse_index(raw: Any) -> List[float]:
    if raw is None:
        return []
    s = str(raw)
    s = re.sub(r"[()\"]", "", s)
    s = s.replace(",", " ")
    out = []
    for tok in s.split():
        f = safe_float(tok)
        if f is not None:
            out.append(f)
    return out


def _parse_values(raw: Any) -> List[List[Optional[float]]]:
    if raw is None:
        return []
    s = str(raw)
    s = re.sub(r"[()]", "", s)
    rows = re.split(r'"\s*,', s)
    result = []
    for row in rows:
        row = row.replace('"', "")
        row = row.replace(",", " ")
        vals = []
        for tok in row.split():
            vals.append(safe_float(tok))
        if vals:
            result.append(vals)
    return result


class CellView:
    """N/A-safe view of one cell in a library."""

    def __init__(self, library: "Library", name: str):
        self.library = library
        self.name = name
        self._area_raw = None
        self._leakage = []
        self._pin_info = None
        self._loaded = False

    def _ensure(self) -> None:
        if self._loaded:
            return
        parser = self.library.parser
        areas = parser.getCellArea(cellList=[self.name])
        self._area_raw = areas.get(self.name)
        self._leakage = parser.getCellLeakagePower(cellList=[self.name]).get(self.name, [])
        self._pin_info = parser.getLibPinInfo(cellList=[self.name])
        self._loaded = True

    @property
    def area(self) -> Optional[float]:
        self._ensure()
        return safe_float(self._area_raw)

    def area_display(self) -> str:
        a = self.area
        return NA if a is None else str(a)

    def leakage_entries(self) -> List[Dict[str, Any]]:
        self._ensure()
        out = []
        for e in self._leakage or []:
            out.append(
                {
                    "value": safe_float(e.get("value")),
                    "when": _strip_quotes(e.get("when", NA)) or NA,
                    "related_pg_pin": _strip_quotes(e.get("related_pg_pin", NA)) or NA,
                }
            )
        return out

    def pin_info(self) -> dict:
        self._ensure()
        return self._pin_info or {}

    def timing_tables(self) -> List[Dict[str, Any]]:
        """Flatten timing LUTs; keep unknown tables (do not silently drop)."""
        self._ensure()
        tables = []
        cell_block = (self._pin_info or {}).get("cell", {}).get(self.name, {})
        pin_map = cell_block.get("pin", {})
        for pin_name, pin_dic in pin_map.items():
            for timing in pin_dic.get("timing", []) or []:
                related = {
                    "pin": pin_name,
                    "related_pin": _strip_quotes(timing.get("related_pin", NA)) or NA,
                    "related_pg_pin": _strip_quotes(timing.get("related_pg_pin", NA)) or NA,
                    "timing_sense": _strip_quotes(timing.get("timing_sense", NA)) or NA,
                    "timing_type": _strip_quotes(timing.get("timing_type", NA)) or NA,
                    "when": _strip_quotes(timing.get("when", NA)) or NA,
                }
                for ttype, tdata in (timing.get("table_type") or {}).items():
                    canon = OCV_SPELLING_FIX.get(ttype, ttype)
                    tables.append(
                        {
                            **related,
                            "table_type": canon,
                            "original_table_type": ttype,
                            "known": canon in KNOWN_TIMING_TABLES,
                            "index_1": _parse_index(tdata.get("index_1")),
                            "index_2": _parse_index(tdata.get("index_2")),
                            "values": _parse_values(tdata.get("values")),
                        }
                    )
        return tables


class Library:
    """Parsed Liberty library identified by absolute path."""

    def __init__(self, path: Union[str, os.PathLike], parser: Optional[LibertyParser] = None):
        self.path = os.path.abspath(os.fspath(path))
        if not os.path.exists(self.path):
            raise ParseError('library "%s": No such file' % self.path)
        self.parser = parser or LibertyParser(self.path, use_cache=True)
        self._cells: Optional[List[str]] = None
        self._units: Optional[Dict[str, str]] = None

    @property
    def key(self) -> str:
        """Stable identity key = absolute path."""
        return self.path

    @property
    def display_name(self) -> str:
        return os.path.basename(self.path)

    def cell_names(self) -> List[str]:
        if self._cells is None:
            self._cells = list(self.parser.getCellList())
        return list(self._cells)

    def select_cells(self, pattern: str) -> List[str]:
        return self.parser.select_cells(pattern)

    def units(self) -> Dict[str, str]:
        if self._units is None:
            raw = self.parser.getUnit()
            self._units = {k: str(_strip_quotes(v)) for k, v in raw.items()}
        return dict(self._units)

    def cell(self, name: str) -> CellView:
        if name not in self.cell_names():
            # still allow view; accessors return None/N/A
            pass
        return CellView(self, name)

    def get(self, attr: str, default=None):
        """Dict-like safe get for units/meta."""
        return self.units().get(attr, default)


def load_library(path: Union[str, os.PathLike]) -> Library:
    return Library(path)


__all__ = [
    "Library",
    "CellView",
    "load_library",
    "NA",
    "KNOWN_TIMING_TABLES",
    "clear_parse_cache",
    "safe_float",
]
