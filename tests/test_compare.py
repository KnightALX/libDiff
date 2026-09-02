import json

import pytest

from libdiff.compare.diff import compare_libraries, export_json, export_csv, check_units
from libdiff.errors import UnitConflictError
from libdiff.model.library import load_library
from libdiff.parser.liberty import clear_parse_cache


def test_numeric_area_leakage_timing_diff(stdcell_base, stdcell_perturbed):
    clear_parse_cache()
    report = compare_libraries(stdcell_base, stdcell_perturbed)
    assert report["summary"]["compared_cells"] >= 3
    inv = report["cells"]["INVX1"]
    assert inv["area"]["left"] == 1.0
    assert inv["area"]["right"] == 1.1
    assert abs(inv["area"]["abs"] - 0.1) < 1e-9
    assert inv["area"]["rel"] is not None
    assert inv["leakage"]
    timing_ok = [t for t in inv["timing"] if t["status"] == "ok"]
    assert timing_ok
    assert any(t.get("max_abs") not in (None, 0) for t in timing_ok)


def test_export_json_csv(stdcell_base, stdcell_perturbed, tmp_path):
    report = compare_libraries(stdcell_base, stdcell_perturbed)
    jpath = tmp_path / "out.json"
    cpath = tmp_path / "out.csv"
    text = export_json(report, path=str(jpath))
    data = json.loads(text)
    assert "cells" in data
    assert jpath.exists()
    csv_text = export_csv(report, path=str(cpath))
    assert "area" in csv_text
    assert cpath.exists()


def test_unit_conflict_blocks(fixtures_dir):
    clear_parse_cache()
    left = str(fixtures_dir / "unit_ns.lib")
    right = str(fixtures_dir / "unit_ps.lib")
    with pytest.raises(UnitConflictError):
        check_units(load_library(left), load_library(right), convert=False)
    report = compare_libraries(left, right, block_on_unit_conflict=True)
    assert report["summary"]["blocked"] is True
    assert report["unit_error"]


def test_unit_convert_allows(fixtures_dir):
    clear_parse_cache()
    left = str(fixtures_dir / "unit_ns.lib")
    right = str(fixtures_dir / "unit_ps.lib")
    info = check_units(load_library(left), load_library(right), convert=True)
    assert info["conversions"]
