# -*- coding: utf-8 -*-
"""Extra tests for quantile_index, marginals, and GUI-less lut_view_payload."""

from __future__ import annotations

import pytest

from libdiff.compare.lut_index import (
    lut_view_payload,
    marginal_delta_stats,
    quantile_index,
    resolve_indices,
)
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


def test_quantile_index_33_point():
    assert quantile_index([], 0.33) == 0.0
    assert quantile_index([0.5], 0.33) == pytest.approx(0.5)
    # two knots: 33% along → interpolate
    assert quantile_index([0.0, 1.0], 0.33) == pytest.approx(0.33)
    assert quantile_index([0.1, 0.5], 0.0) == pytest.approx(0.1)
    assert quantile_index([0.1, 0.5], 1.0) == pytest.approx(0.5)
    # clamp
    assert quantile_index([0.0, 10.0], -1.0) == pytest.approx(0.0)
    assert quantile_index([0.0, 10.0], 2.0) == pytest.approx(10.0)
    # three knots at q=0.33 → pos=0.66 between first two
    assert quantile_index([0.1, 0.5, 1.0], 0.33) == pytest.approx(0.1 * 0.34 + 0.5 * 0.66)


def test_marginal_delta_stats_basic():
    mat = [
        [0.1, -0.2, None],
        [0.3, 0.4, 0.5],
    ]
    i1 = [1.0, 2.0]
    i2 = [10.0, 20.0, 30.0]
    out = marginal_delta_stats(mat, i1, i2)
    assert out["by_i1"]["xs"] == pytest.approx([1.0, 2.0])
    # row0: mean of 0.1,-0.2 = -0.05; mean_abs=(0.1+0.2)/2=0.15; maxabs=0.2
    assert out["by_i1"]["mean"][0] == pytest.approx(-0.05)
    assert out["by_i1"]["mean_abs"][0] == pytest.approx(0.15)
    assert out["by_i1"]["maxabs"][0] == pytest.approx(0.2)
    # col0: 0.1, 0.3 → mean 0.2, maxabs 0.3
    assert out["by_i2"]["xs"] == pytest.approx([10.0, 20.0, 30.0])
    assert out["by_i2"]["mean"][0] == pytest.approx(0.2)
    assert out["by_i2"]["maxabs"][0] == pytest.approx(0.3)
    # col2: only 0.5 from row1 (None skipped)
    assert out["by_i2"]["mean"][2] == pytest.approx(0.5)


def test_lut_view_payload_point_line_surface(mismatch_left, mismatch_right):
    lt = _cell_rise(mismatch_left)
    rt = _cell_rise(mismatch_right)
    i1, i2, _, _, _ = resolve_indices(mismatch_left, lt)
    q1 = quantile_index(i1, 0.33)
    q2 = quantile_index(i2, 0.33)

    pt = lut_view_payload(
        lt, rt, view_mode="point", x1=q1, x2=q2,
        left_lib=mismatch_left, right_lib=mismatch_right,
    )
    assert pt["view_mode"] == "point"
    assert pt["point"]["left"] is not None
    assert pt["point"]["right"] is not None
    assert pt["point"]["delta"] == pytest.approx(pt["point"]["right"] - pt["point"]["left"])

    line = lut_view_payload(
        lt, rt, view_mode="line", line_fix_axis="index_1", x1=q1,
        left_lib=mismatch_left, right_lib=mismatch_right,
    )
    assert line["view_mode"] == "line"
    assert line["line"]["free_axis"] == "index_2"
    assert len(line["line"]["xs"]) >= 2
    assert "left" in line["line"]["series"]
    assert "delta" in line["line"]["series"]

    line2 = lut_view_payload(
        lt, rt, view_mode="扫线", line_fix_axis="index_2", x2=q2,
        left_lib=mismatch_left, right_lib=mismatch_right,
    )
    assert line2["line"]["free_axis"] == "index_1"

    surf = lut_view_payload(
        lt, rt, view_mode="surface", use_cross=True, cross_mode="left_grid",
        left_lib=mismatch_left, right_lib=mismatch_right,
    )
    assert surf["view_mode"] == "surface"
    assert surf["surface"]["abs_matrix"]
    assert surf["surface"]["marginals"]["by_i1"]["xs"]
    assert surf["surface"]["marginals"]["by_i2"]["maxabs"]


def test_lut_view_payload_1d_point_line(mismatch_left):
    t = _constraint(mismatch_left)
    pt = lut_view_payload(t, view_mode="point", left_lib=mismatch_left)
    assert pt["classification"] == "1d"
    assert pt["point"]["left"] is not None
    line = lut_view_payload(t, view_mode="line", left_lib=mismatch_left)
    assert line["line"]["xs"]
    assert "left" in line["line"]["series"]
