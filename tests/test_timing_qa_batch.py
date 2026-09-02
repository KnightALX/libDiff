"""Extra Timing QA batch + HTML export tests."""

from __future__ import annotations

import json
from pathlib import Path

from libdiff.compare.timing_qa import (
    export_timing_qa_html,
    export_timing_qa_batch_csv,
    run_timing_qa_batch,
)
from libdiff.parser.liberty import clear_parse_cache


def test_run_timing_qa_batch(fixtures_dir):
    clear_parse_cache()
    left = str(fixtures_dir / "timing_qa_left.lib")
    right = str(fixtures_dir / "timing_qa_right.lib")
    report = run_timing_qa_batch(
        left,
        right,
        cell_pattern="INV*",
        abs_tol=1e-4,
        rel_tol=0.01,
        include_matrices=True,
    )
    s = report["summary"]
    assert s["mode"] == "batch"
    assert s["n_cells_compared"] >= 1
    assert s["n_arcs_matched"] >= 1
    assert s["n_fail"] >= 1
    assert report["cells"]
    assert s["top_failing_arcs"]


def test_batch_exports_html_csv(fixtures_dir, tmp_path):
    clear_parse_cache()
    left = str(fixtures_dir / "timing_qa_left.lib")
    right = str(fixtures_dir / "timing_qa_right.lib")
    report = run_timing_qa_batch(
        left, right, cells=["INVX1"], include_matrices=True
    )
    html_path = tmp_path / "qa.html"
    csv_path = tmp_path / "qa.csv"
    html = export_timing_qa_html(report, path=str(html_path), embed_plots=True)
    csv_text = export_timing_qa_batch_csv(report, path=str(csv_path))
    assert html_path.exists()
    assert "libDiff Timing QA Report" in html
    assert "Matched arcs" in html
    assert "cell_summary" in csv_text or "arc" in csv_text
    assert csv_path.exists()
