"""Tests for physical-index LUT compare (1D/2D, probe, cross-index, templates)."""

from __future__ import annotations

import subprocess
import sys

import pytest

from libdiff.compare.lut_index import (
    classify_lut,
    cross_index_delta,
    probe_points,
    resolve_indices,
    sample_lut,
    slice_curve,
)
from libdiff.compare.timing_qa import timing_qa
from libdiff.model.library import load_library
from libdiff.parser.liberty import clear_parse_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_parse_cache()
    yield
    clear_parse_cache()


@pytest.fixture
def mismatch_left(fixtures_dir):
    return load_library(str(fixtures_dir / "lut_mismatch_left.lib"))


@pytest.fixture
def mismatch_right(fixtures_dir):
    return load_library(str(fixtures_dir / "lut_mismatch_right.lib"))


def _cell_rise(lib, cell="INVX1"):
    for t in lib.cell(cell).timing_tables():
        if t["table_type"] == "cell_rise" and t["pin"] == "Y":
            return t
    raise AssertionError("cell_rise not found")


def _constraint(lib, cell="INVX1"):
    for t in lib.cell(cell).timing_tables():
        if t["table_type"] == "rise_constraint":
            return t
    raise AssertionError("rise_constraint not found")


def test_classify_1d_2d(mismatch_left):
    assert classify_lut(_cell_rise(mismatch_left)) == "2d"
    assert classify_lut(_constraint(mismatch_left)) == "1d"
    assert classify_lut({"values": []}) == "empty"


def test_sample_bilinear_and_no_extrapolate(mismatch_left):
    t = _cell_rise(mismatch_left)
    i1, i2, _, _, _ = resolve_indices(mismatch_left, t)
    # exact corner
    assert sample_lut(t["values"], i1, i2, 0.1, 0.01) == pytest.approx(0.10)
    # mid-load at slew 0.1: load between 0.01 and 0.1 → (0.10+0.20)/2 = 0.15
    assert sample_lut(t["values"], i1, i2, 0.1, 0.055) == pytest.approx(0.15)
    # out of range
    assert sample_lut(t["values"], i1, i2, 0.0, 0.01) is None
    assert sample_lut(t["values"], i1, i2, 0.1, 1.0) is None


def test_sample_1d_constraint(mismatch_left):
    t = _constraint(mismatch_left)
    i1, i2, _, _, _ = resolve_indices(mismatch_left, t)
    assert classify_lut(t) == "1d"
    v = sample_lut(t["values"], i1, i2, 0.3, None)
    assert v == pytest.approx(0.065)  # mid between 0.05 and 0.08


def test_template_resolve_invx2(mismatch_left):
    t = _cell_rise(mismatch_left, cell="INVX2")
    # inline indices absent; filled from delay_2x2 template
    assert t.get("template_name") == "delay_2x2"
    i1, i2, tname, v1, v2 = resolve_indices(mismatch_left, t)
    assert tname == "delay_2x2"
    assert i1 == pytest.approx([0.1, 0.5])
    assert i2 == pytest.approx([0.01, 0.1])
    assert v1 == "input_net_transition"
    assert v2 == "total_output_net_capacitance"
    templates = mismatch_left.lut_templates()
    assert "delay_2x2" in templates
    assert "constraint_1x2" in templates


def test_cross_index_delta_left_grid(mismatch_left, mismatch_right):
    lt = _cell_rise(mismatch_left)
    rt = _cell_rise(mismatch_right)
    cd = cross_index_delta(lt, rt, mode="left_grid", left_lib=mismatch_left, right_lib=mismatch_right)
    assert cd["aligned"] is False
    assert cd["index_1"] == pytest.approx([0.1, 0.5])
    assert cd["index_2"] == pytest.approx([0.01, 0.1])
    assert cd["stats"]["n_compared"] == 4
    # left[0][0]=0.10, right at (0.1,0.01)=0.11 → delta 0.01
    assert cd["abs_matrix"][0][0] == pytest.approx(0.01)
    assert cd["out_of_range"]["total"] == 0


def test_cross_index_union_and_query(mismatch_left, mismatch_right):
    lt = _cell_rise(mismatch_left)
    rt = _cell_rise(mismatch_right)
    uni = cross_index_delta(lt, rt, mode="union", left_lib=mismatch_left, right_lib=mismatch_right)
    assert 0.3 in uni["index_1"]
    assert 0.05 in uni["index_2"]
    # left indices [0.1,0.5]x[0.01,0.1] cover the union via interpolation
    assert uni["stats"]["n_compared"] == len(uni["index_1"]) * len(uni["index_2"])
    # query outside left slew range → left OOR
    oor = cross_index_delta(
        lt, rt, mode="query", query_i1=[0.9], query_i2=[0.01],
        left_lib=mismatch_left, right_lib=mismatch_right,
    )
    assert oor["out_of_range"]["left"] >= 1 or oor["stats"]["n_compared"] == 0

    q = cross_index_delta(
        lt,
        rt,
        mode="query",
        query_i1=[0.1],
        query_i2=[0.01, 0.1],
        left_lib=mismatch_left,
        right_lib=mismatch_right,
    )
    assert q["nrows"] == 1 and q["ncols"] == 2
    assert q["stats"]["n_compared"] == 2


def test_slice_curve(mismatch_left):
    t = _cell_rise(mismatch_left)
    xs, ys = slice_curve(t, axis="index_2", fixed_value=0.1, method="nearest", lib=mismatch_left)
    assert xs == pytest.approx([0.01, 0.1])
    assert ys[0] == pytest.approx(0.10)
    assert ys[1] == pytest.approx(0.20)
    xs2, ys2 = slice_curve(t, axis="index_2", fixed_value=0.3, method="interp", lib=mismatch_left)
    # mid slew between 0.1 and 0.5
    assert ys2[0] == pytest.approx(0.125)


def test_probe_points(mismatch_left):
    t = _cell_rise(mismatch_left)
    rows = probe_points(t, [(0.1, 0.01), (9.0, 0.01)], lib=mismatch_left)
    assert rows[0]["value"] == pytest.approx(0.10)
    assert rows[0]["out_of_range"] is False
    assert rows[1]["value"] is None
    assert rows[1]["out_of_range"] is True


def test_timing_qa_auto_cross(mismatch_left, mismatch_right, fixtures_dir):
    report = timing_qa(
        str(fixtures_dir / "lut_mismatch_left.lib"),
        str(fixtures_dir / "lut_mismatch_right.lib"),
        cells=["INVX1"],
        table_types=["cell_rise"],
        index_mode="auto",
        include_matrices=True,
    )
    arcs = [a for a in report["arcs"] if a["table_type"] == "cell_rise"]
    assert arcs
    a = arcs[0]
    assert a["index_alignment"] != "aligned"
    assert a["index_mode_used"] == "cross"
    assert a["status"] in ("ok", "fail")  # not stuck on index_mismatch when cross used
    assert a.get("grid_index_1")


def test_cli_lut_probe_smoke(fixtures_dir):
    left = str(fixtures_dir / "lut_mismatch_left.lib")
    right = str(fixtures_dir / "lut_mismatch_right.lib")
    cmd = [
        sys.executable,
        "-m",
        "libdiff",
        "lut-probe",
        left,
        right,
        "--cell",
        "INVX1",
        "--pin",
        "Y",
        "--table",
        "cell_rise",
        "--i1",
        "0.1",
        "--i2",
        "0.01",
        "--cross-mode",
        "left_grid",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "probe left" in proc.stdout
    assert "cross-index" in proc.stdout

    cmd2 = [
        sys.executable,
        "-m",
        "libdiff",
        "lut-probe",
        left,
        "--cell",
        "INVX1",
        "--pin",
        "Y",
        "--table",
        "cell_rise",
        "--slice",
        "index_2",
        "--fix-i1",
        "0.1",
    ]
    proc2 = subprocess.run(cmd2, capture_output=True, text=True, check=False)
    assert proc2.returncode == 0, proc2.stderr + proc2.stdout
    assert "slice free=index_2" in proc2.stdout
