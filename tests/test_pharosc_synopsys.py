"""Integration tests against pharosc Synopsys Liberty libraries (skip if absent)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from libdiff.analyze import analyze_library
from libdiff.discover import discover_libs
from libdiff.parser.liberty import LibertyParser, clear_parse_cache

PHAROSC_DEFAULT = Path(r"D:\workspace\project\grok\pharosc-8.5\synopsys")
PHAROSC = Path(os.environ.get("PHAROSC", str(PHAROSC_DEFAULT)))

EXPECTED_LIBS = [
    "rgalib013.lib",
    "vgalib013.lib",
    "ssxlib013.lib",
    "sxlib013.lib",
    "vxlib013.lib",
    "vsclib013.lib",
]


def _pharosc_available() -> bool:
    return PHAROSC.is_dir() and (PHAROSC / "rgalib013.lib").is_file()


pytestmark = pytest.mark.skipif(
    not _pharosc_available(),
    reason="pharosc synopsys path missing: %s" % PHAROSC,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_parse_cache()
    yield
    clear_parse_cache()


def test_discover_six_libs():
    entries = discover_libs(PHAROSC, recursive=False)
    names = {Path(e.path).name for e in entries}
    for name in EXPECTED_LIBS:
        assert name in names
    by_name = {Path(e.path).name: e for e in entries}
    assert by_name["rgalib013.lib"].library_name == "rgalib013"
    assert by_name["rgalib013.lib"].size > 0


@pytest.mark.parametrize("lib_name", ["rgalib013.lib", "vgalib013.lib", "sxlib013.lib"])
def test_parse_core_libs(lib_name):
    path = str(PHAROSC / lib_name)
    p = LibertyParser(path, use_cache=False)
    cells = p.getCellList()
    assert len(cells) > 0
    units = p.getUnit()
    assert "time_unit" in units
    assert "ps" in str(units["time_unit"]).lower().replace(" ", "")


@pytest.mark.parametrize("lib_name", ["ssxlib013.lib", "vxlib013.lib", "vsclib013.lib"])
def test_parse_remaining_libs(lib_name):
    path = str(PHAROSC / lib_name)
    p = LibertyParser(path, use_cache=False)
    cells = p.getCellList()
    assert len(cells) > 0
    units = p.getUnit()
    assert "time_unit" in units


def test_analyze_api_smoke():
    path = str(PHAROSC / "rgalib013.lib")
    summary = analyze_library(path, sample_cells=3)
    assert summary["cell_count"] > 0
    assert "time_unit" in summary["units"]
    assert summary["area_available"] > 0
    assert len(summary["sample_cells"]) == 3


def test_trailing_comment_and_nospace_cell():
    """Parser tolerates ``cell(name) { /* ... */`` and inline area comments."""
    path = str(PHAROSC / "rgalib013.lib")
    p = LibertyParser(path, use_cache=False)
    cells = p.getCellList()
    assert "aoi21v0x1" in cells
    areas = p.getCellArea(cellList=["aoi21v0x1"])
    assert areas["aoi21v0x1"] is not None
