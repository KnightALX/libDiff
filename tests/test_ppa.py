"""PPA Phase A: metrics %Δ, series grouping, HTML smoke."""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")

from libdiff.compare.ppa import (
    compare_ppa,
    export_ppa_csv,
    export_ppa_html,
    export_ppa_json,
    format_ppa_summary,
    lut_mid_sample,
    mid_index,
    typical_delay,
)
from libdiff.model.library import load_library
from libdiff.series import group_cells_by_series, match_cell_series, sort_cells_with_size


def test_mid_index_and_lut_sample():
    assert mid_index(0) == 0
    assert mid_index(2) == 1
    assert mid_index(3) == 1
    assert lut_mid_sample([[0.10, 0.20], [0.15, 0.25]]) == 0.25
    assert lut_mid_sample([]) is None
    assert lut_mid_sample([[None, None]]) is None


def test_typical_delay_invx1(stdcell_base):
    lib = load_library(stdcell_base)
    # mid of 2x2 cell_rise -> values[1][1] = 0.25
    assert typical_delay(lib.cell("INVX1")) == 0.25


def test_ppa_pct_delta(stdcell_base, stdcell_perturbed):
    report = compare_ppa(stdcell_base, stdcell_perturbed, cells=["INVX1"])
    inv = report["cells"]["INVX1"]
    # area 1.0 -> 1.1 => +10%
    assert inv["area"]["status"] == "ok"
    assert abs(inv["area"]["abs"] - 0.1) < 1e-9
    assert abs(inv["area"]["pct"] - 10.0) < 1e-6
    # leakage sum 1.0 -> 1.1 => +10%
    assert inv["leakage"]["status"] == "ok"
    assert abs(inv["leakage"]["pct"] - 10.0) < 1e-6
    # delay 0.25 -> 0.30 => +20%
    assert inv["delay"]["status"] == "ok"
    assert abs(inv["delay"]["left"] - 0.25) < 1e-9
    assert abs(inv["delay"]["right"] - 0.30) < 1e-9
    assert abs(inv["delay"]["pct"] - 20.0) < 1e-6


def test_ppa_missing_safe(stdcell_base, stdcell_perturbed):
    # INVX2 has no leakage entries
    report = compare_ppa(stdcell_base, stdcell_perturbed, cells=["INVX2"])
    assert report["cells"]["INVX2"]["leakage"]["status"] == "missing"
    assert report["cells"]["INVX2"]["leakage"]["pct"] is None
    assert report["cells"]["INVX2"]["area"]["status"] == "ok"


def test_series_grouping_inv_family():
    names = ["INVX1", "INVX2", "NOR2X1", "OR2"]
    g = group_cells_by_series(names)
    assert "INV" in g
    drives = [d for d, _ in g["INV"]]
    assert drives == [1, 2]
    assert match_cell_series("INVX4") == ("INV", 4)
    ordered = sort_cells_with_size(["INVX2", "INVX1", "FOO"])
    assert ordered.index("INVX1") < ordered.index("INVX2")


def test_ppa_series_in_report(stdcell_base, stdcell_perturbed):
    report = compare_ppa(stdcell_base, stdcell_perturbed)
    assert "INV" in report["series"]
    members = report["series"]["INV"]["members"]
    assert [m["cell"] for m in members] == ["INVX1", "INVX2"]


def test_ppa_html_csv_smoke(stdcell_base, stdcell_perturbed, tmp_path):
    report = compare_ppa(stdcell_base, stdcell_perturbed, notes="pytest cover")
    html_path = tmp_path / "ppa.html"
    csv_path = tmp_path / "ppa.csv"
    json_path = tmp_path / "ppa.json"
    html = export_ppa_html(report, path=str(html_path), embed_plots=True)
    export_ppa_csv(report, path=str(csv_path))
    export_ppa_json(report, path=str(json_path))
    assert html_path.exists() and html_path.stat().st_size > 500
    assert "libDiff PPA Report" in html
    assert "Mean Area" in html or "Area %" in html
    assert csv_path.exists() and "INVX1" in csv_path.read_text(encoding="utf-8")
    assert "PPA compare" in format_ppa_summary(report)


def test_ppa_sram_stub(stdcell_base, stdcell_perturbed):
    report = compare_ppa(stdcell_base, stdcell_perturbed, mode="sram")
    assert report["mode"] == "sram"
    assert report["summary"].get("stub") is True
    assert report["cells"] == {}


def test_ppa_cli(stdcell_base, stdcell_perturbed, tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    html = tmp_path / "cli_ppa.html"
    csv = tmp_path / "cli_ppa.csv"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "libdiff",
            "ppa",
            stdcell_base,
            stdcell_perturbed,
            "--html",
            str(html),
            "--csv",
            str(csv),
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 0, r.stderr
    assert html.exists() and csv.exists()
    assert "PPA compare" in r.stdout
