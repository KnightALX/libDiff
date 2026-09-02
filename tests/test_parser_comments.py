"""Synthetic tests for trailing comments and same-line closing braces."""

from pathlib import Path

import pytest

from libdiff.errors import ParseError
from libdiff.parser.liberty import LibertyParser, clear_parse_cache


def test_trailing_comment_on_group_and_attr(fixtures_dir, tmp_path):
    clear_parse_cache()
    path = tmp_path / "trail_comment.lib"
    path.write_text(
        "library (trail) { /* hdr */\n"
        '  time_unit : "1ps" ; /* u */\n'
        "  capacitive_load_unit (1.00,ff) ;\n"
        '  leakage_power_unit : "1pW" ;\n'
        "  library_features (report_delay_calculation) ;\n"
        '  wire_load ("1K") {\n'
        "    fanout_length (  1,  2.86 ) ;\n"
        "  }\n"
        "  cell(inv_x1) { /* cell */\n"
        "    area : 8 ; /* tracks */\n"
        "    pin(a) {\n"
        "      direction : input ;\n"
        "    }\n"
        "  }\n"
        "} /* end */\n",
        encoding="utf-8",
    )
    p = LibertyParser(str(path), use_cache=False)
    assert p.getCellList() == ["inv_x1"]
    units = p.getUnit()
    assert "time_unit" in units
    assert "capacitive_load_unit" in units
    assert "leakage_power_unit" in units
    assert "library_features" in p.libDic
    areas = p.getCellArea(cellList=["inv_x1"])
    assert areas["inv_x1"].strip() == "8"


def test_same_line_closing_brace(tmp_path):
    clear_parse_cache()
    path = tmp_path / "same_close.lib"
    # `"); }}` closes cell_rise + timing; then pin, cell, library
    path.write_text(
        "library (sameclose) {\n"
        '  time_unit : "1ns";\n'
        "  lu_table_template (t1) {\n"
        '    index_1 ("0.1, 0.2") ; }\n'
        "  cell (C1) {\n"
        "    area : 1.0;\n"
        "    pin (Y) {\n"
        "      timing () {\n"
        "        cell_rise (t1) {\n"
        '          values ("0.1, 0.2"); }}\n'
        "    }\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    p = LibertyParser(str(path), use_cache=False)
    assert p.getCellList() == ["C1"]
    info = p.getLibPinInfo(cellList=["C1"])
    assert "cell_rise" in info["cell"]["C1"]["pin"]["Y"]["timing"][0]["table_type"]


def test_attr_outside_group_raises_parse_error(tmp_path):
    clear_parse_cache()
    path = tmp_path / "bad.lib"
    # No library group — technology looks like complex attr with no open group
    path.write_text("technology (cmos) ;\n", encoding="utf-8")
    with pytest.raises(ParseError, match="Line 1"):
        LibertyParser(str(path), use_cache=False)


def test_multiline_values_with_trailing_closes(tmp_path):
    clear_parse_cache()
    path = tmp_path / "ml_close.lib"
    path.write_text(
        "library (ml) {\n"
        '  time_unit : "1ns";\n'
        "  cell (C1) {\n"
        "    pin (Y) {\n"
        "      timing () {\n"
        "        cell_rise (t1) {\n"
        '          values ( "0.1, 0.2", \\\n'
        '                   "0.3, 0.4" ); }}\n'
        "    }\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    p = LibertyParser(str(path), use_cache=False)
    info = p.getLibPinInfo(cellList=["C1"])
    vals = info["cell"]["C1"]["pin"]["Y"]["timing"][0]["table_type"]["cell_rise"]["values"]
    assert "0.1" in str(vals)


def test_inline_nested_groups(tmp_path):
    clear_parse_cache()
    path = tmp_path / "inline.lib"
    path.write_text(
        "library (buslib) {\n"
        "  cell (B1) {\n"
        "    bus (DATA) {\n"
        "      bus_type : bus4;\n"
        "      pin (DATA[0]) {\n"
        "        direction : input;\n"
        '        timing () { related_pin : "CK"; cell_rise (t) { values ("0.1"); } }\n'
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    p = LibertyParser(str(path), use_cache=False)
    info = p.getLibPinInfo(cellList=["B1"], busList=["DATA"])
    assert "bus" in info["cell"]["B1"]
