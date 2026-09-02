"""Unit tests for Timing QA (NLDM arc compare, monotonicity, missing arcs)."""

from __future__ import annotations

import json

import pytest

from libdiff.compare.timing_qa import (
    check_monotonicity,
    check_table_sanity,
    delta_matrices,
    export_timing_qa_csv,
    export_timing_qa_json,
    index_alignment_status,
    single_lib_timing_qa,
    timing_qa,
)
from libdiff.parser.liberty import clear_parse_cache


@pytest.fixture
def timing_left(fixtures_dir):
    return str(fixtures_dir / "timing_qa_left.lib")


@pytest.fixture
def timing_right(fixtures_dir):
    return str(fixtures_dir / "timing_qa_right.lib")


def test_delta_matrices_basic():
    left = [[0.10, 0.20], [0.15, 0.25]]
    right = [[0.12, 0.22], [0.17, None]]
    dm = delta_matrices(left, right)
    assert dm["nrows"] == 2 and dm["ncols"] == 2
    assert abs(dm["abs_matrix"][0][0] - 0.02) < 1e-12
    assert dm["abs_matrix"][1][1] is None
    assert dm["stats"]["max_abs"] is not None
    assert abs(dm["stats"]["max_abs"] - 0.02) < 1e-12
    assert dm["rel_matrix"][0][0] == pytest.approx(0.2)


def test_delta_matrices_none_padding():
    left = [[1.0]]
    right = [[1.0, 2.0], [3.0, 4.0]]
    dm = delta_matrices(left, right)
    assert dm["nrows"] == 2 and dm["ncols"] == 2
    assert dm["abs_matrix"][0][0] == 0.0
    assert dm["abs_matrix"][0][1] is None


def test_monotonicity_flags_decrease():
    values = [[0.10, 0.09], [0.15, 0.25]]
    mono = check_monotonicity(values)
    assert mono["ok"] is False
    assert mono["n_violations"] >= 1
    assert any(v["axis"] == "index_2" for v in mono["violations"])


def test_monotonicity_ok_nondecreasing():
    values = [[0.10, 0.20], [0.15, 0.25]]
    mono = check_monotonicity(values)
    assert mono["ok"] is True


def test_sanity_negative_and_empty():
    assert check_table_sanity([])["empty"] is True
    s = check_table_sanity([[-0.1, 0.2]])
    assert s["ok"] is False
    assert s["n_negative"] == 1


def test_index_alignment():
    assert index_alignment_status([0.1, 0.5], [0.01, 0.1], [0.1, 0.5], [0.01, 0.1]) == "aligned"
    assert (
        index_alignment_status([0.1, 0.5], [0.01, 0.1], [0.1, 0.6], [0.01, 0.1])
        == "index_1_mismatch"
    )


def test_timing_qa_missing_and_diff(timing_left, timing_right):
    clear_parse_cache()
    report = timing_qa(
        timing_left,
        timing_right,
        cells=["INVX1"],
        abs_tol=1e-4,
        rel_tol=0.01,
        include_matrices=True,
    )
    s = report["summary"]
    assert s["n_arcs_matched"] >= 1
    assert s["n_left_only"] >= 1
    assert s["n_right_only"] >= 1
    rises = [a for a in report["arcs"] if a["table_type"] == "cell_rise"]
    assert rises
    assert rises[0]["max_abs"] == pytest.approx(0.02)
    assert rises[0]["exceeds_tol"] is True
    assert rises[0]["abs_matrix"][0][0] == pytest.approx(0.02)


def test_timing_qa_export(timing_left, timing_right, tmp_path):
    clear_parse_cache()
    report = timing_qa(timing_left, timing_right, cell_pattern="INV*", include_matrices=False)
    jpath = tmp_path / "tq.json"
    cpath = tmp_path / "tq.csv"
    text = export_timing_qa_json(report, path=str(jpath))
    data = json.loads(text)
    assert "summary" in data and "arcs" in data
    csv_text = export_timing_qa_csv(report, path=str(cpath))
    assert "max_abs" in csv_text
    assert "left_only" in csv_text or "right_only" in csv_text
    assert jpath.exists() and cpath.exists()


def test_single_lib_monotonicity(timing_left):
    clear_parse_cache()
    qa = single_lib_timing_qa(timing_left, cells=["BUF_MONO"])
    assert qa["n_arcs"] >= 1
    assert qa["n_monotonicity_fail"] >= 1
    bad = [a for a in qa["arcs"] if a["status"] == "fail"]
    assert bad


def test_timing_qa_with_stdcell_fixtures(stdcell_base, stdcell_perturbed):
    clear_parse_cache()
    report = timing_qa(
        stdcell_base,
        stdcell_perturbed,
        cells=["INVX1"],
        abs_tol=0.01,
        rel_tol=0.05,
    )
    assert report["summary"]["n_arcs_matched"] >= 1
    assert report["summary"]["n_fail"] >= 1
