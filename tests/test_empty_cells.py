import os

from libdiff.model.library import load_library, NA
from libdiff.parser.liberty import clear_parse_cache


def test_empty_attrs_na_safe(fixtures_dir):
    clear_parse_cache()
    lib = load_library(str(fixtures_dir / "empty_attrs.lib"))
    assert os.path.isabs(lib.key)
    assert lib.key.endswith("empty_attrs.lib")
    empty = lib.cell("EMPTY1")
    assert empty.area is None
    assert empty.area_display() == NA
    assert empty.leakage_entries() == []
    assert empty.timing_tables() == []
    partial = lib.cell("PARTIAL1")
    assert partial.area == 3.0


def test_library_abs_path_key(stdcell_base):
    lib = load_library(stdcell_base)
    assert os.path.isabs(lib.key)
    assert lib.key == lib.path
