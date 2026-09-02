import pytest

from libdiff.errors import ParseError
from libdiff.parser.liberty import LibertyParser, clear_parse_cache, safe_float


def test_parse_example_cells(example_lib):
    clear_parse_cache()
    p = LibertyParser(example_lib)
    cells = p.getCellList()
    assert "INVX1" in cells
    assert "NOR2X1" in cells
    assert "DFFX1" in cells
    assert len(cells) == 3


def test_parse_units(example_lib):
    p = LibertyParser(example_lib)
    units = p.getUnit()
    assert "time_unit" in units
    assert "ns" in units["time_unit"].replace(" ", "").lower()


def test_get_cell_area_and_leakage(stdcell_base):
    clear_parse_cache()
    p = LibertyParser(stdcell_base)
    areas = p.getCellArea(cellList=["INVX1", "MISSING"])
    assert safe_float(areas["INVX1"]) == 1.0
    assert areas["MISSING"] is None
    leak = p.getCellLeakagePower(cellList=["INVX1"])
    assert "INVX1" in leak
    assert len(leak["INVX1"]) == 2


def test_get_lib_pin_info_selected(stdcell_base):
    p = LibertyParser(stdcell_base)
    info = p.getLibPinInfo(cellList=["INVX1"])
    assert "cell" in info
    assert "INVX1" in info["cell"]
    assert "Y" in info["cell"]["INVX1"]["pin"]
    assert "timing" in info["cell"]["INVX1"]["pin"]["Y"]


def test_missing_file_raises():
    clear_parse_cache()
    with pytest.raises(ParseError):
        LibertyParser("Z:/no/such/file.lib")


def test_safe_float_none_not_zero():
    assert safe_float(None) is None
    assert safe_float("") is None
    assert safe_float("N/A") is None
    assert safe_float("1.5") == 1.5


def test_fnmatch_select(stdcell_base):
    p = LibertyParser(stdcell_base)
    assert p.select_cells("INV*") == ["INVX1", "INVX2"]
    assert p.select_cells("NOR2X1") == ["NOR2X1"]


def test_bus_filter_no_nameerror(fixtures_dir):
    path = fixtures_dir / "_bus_tmp.lib"
    path.write_text(
        "library (buslib) {\n"
        "  cell (B1) {\n"
        "    bus (DATA) {\n"
        "      bus_type : bus4;\n"
        "      pin (DATA[0]) {\n"
        "        direction : input;\n"
        "        timing () { related_pin : \"CK\"; cell_rise (t) { values (\"0.1\"); } }\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    clear_parse_cache()
    p = LibertyParser(str(path))
    info = p.getLibPinInfo(cellList=["B1"], busList=["DATA"])
    assert "bus" in info["cell"]["B1"]
    info2 = p.getLibPinInfo(cellList=["B1"], busList=["OTHER"])
    assert "bus" not in info2.get("cell", {}).get("B1", {})


def test_parse_cache(stdcell_base):
    clear_parse_cache()
    a = LibertyParser(stdcell_base, use_cache=True)
    b = LibertyParser(stdcell_base, use_cache=True)
    assert a.libDic is b.libDic


def test_ocv_constraint_names(fixtures_dir):
    clear_parse_cache()
    p = LibertyParser(str(fixtures_dir / "ocv_constraint.lib"))
    info = p.getLibPinInfo(cellList=["DFFX1"])
    timing = info["cell"]["DFFX1"]["pin"]["D"]["timing"][0]
    tables = set(timing["table_type"].keys())
    assert "ocv_sigma_rise_constraint" in tables
    assert "ocv_sigma_fall_constraint" in tables
    assert "ocv_sigma_rise_contraint" in tables


def test_ccs_mini(fixtures_dir):
    clear_parse_cache()
    p = LibertyParser(str(fixtures_dir / "ccs_mini.lib"))
    assert p.getCellList() == ["INVX1"]
    info = p.getLibPinInfo(cellList=["INVX1"])
    tables = info["cell"]["INVX1"]["pin"]["Y"]["timing"][0]["table_type"]
    assert "output_current_rise" in tables
