import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run_mod(*args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [PY, "-m", "libdiff", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
    )


def test_help():
    r = run_mod("--help")
    assert r.returncode == 0
    assert "compare" in r.stdout
    assert "timing-qa" in r.stdout


def test_compare_json(stdcell_base, stdcell_perturbed):
    r = run_mod("compare", stdcell_base, stdcell_perturbed, "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert "INVX1" in data["cells"]
    assert data["cells"]["INVX1"]["area"]["abs"] is not None


def test_cells_cmd(stdcell_base):
    r = run_mod("cells", stdcell_base, "--pattern", "INV*")
    assert r.returncode == 0
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    assert lines == ["INVX1", "INVX2"]


def test_timing_qa_cli(stdcell_base, stdcell_perturbed):
    r = run_mod(
        "timing-qa",
        stdcell_base,
        stdcell_perturbed,
        "--cell",
        "INVX1",
        "--json",
        "--no-matrices",
    )
    assert r.returncode in (0, 1), r.stderr
    data = json.loads(r.stdout)
    assert "summary" in data
    assert data["summary"]["n_arcs_matched"] >= 1


def test_timing_qa_batch_cli(fixtures_dir, tmp_path):
    left = str(fixtures_dir / "timing_qa_left.lib")
    right = str(fixtures_dir / "timing_qa_right.lib")
    html = tmp_path / "qa.html"
    csv = tmp_path / "qa.csv"
    r = run_mod(
        "timing-qa",
        left,
        right,
        "--cell",
        "INV*",
        "--batch",
        "--html",
        str(html),
        "--csv",
        str(csv),
    )
    assert r.returncode in (0, 1), r.stderr
    assert html.exists() and html.stat().st_size > 0
    assert csv.exists() and csv.stat().st_size > 0
    assert "Timing QA batch" in r.stdout or "cells compared" in r.stdout
