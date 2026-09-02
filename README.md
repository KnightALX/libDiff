# libDiff

Liberty (.lib) **compare / analysis / Timing QA** for chip **FIP** design teams — stdcell and SRAM libraries (NLDM and CCS-style tables).

**Version: 0.3.0**

Upstream ideas adapted from [libView](https://github.com/liyanqing1987/libView) and [libertyParser](https://github.com/liyanqing1987/libertyParser) (GPL-2.0). Reworked into an installable package with Fluent GUI, Pharosc Synopsys support, and batch Timing QA reports.

## Features

- Pure-Python Liberty parser (Windows-safe; no grep / wk / os.system)
- Library identity by **absolute path** (same basename, different folders OK)
- N/A-safe accessors for missing area / leakage / timing
- Structure-aligned numeric compare (area, leakage, LUT samples) with abs / rel deltas
- Unit conflict detection (	ime_unit, power units) — block or convert with clear errors
- CLI: python -m libdiff with JSON / CSV / HTML export
- **Timing QA** (Qualib / Liberate-LV inspired, Liberty-only)
  - Arc align, Δ / % matrices, missing arcs, monotonicity / sanity checks
  - **Batch / multi-cell** run with fail ranking
  - Self-contained **HTML** report (inline CSS + optional heatmap PNGs) and CSV
- **Fluent GUI** (PyQt-Fluent-Widgets): Libraries / Compare / Timing QA / About
- Unified **matplotlib** plot theme (bar / heatmap / delay curves; not Plotly)
- Timing LUT / arc tables default to ~**6** visible rows and grow with window height
- Discover / analyze folders (e.g. Pharosc synopsys/*.lib)

## Requirements

- Python 3.8+
- 
umpy, matplotlib, PyQt5, PyQt-Fluent-Widgets
- Dev: pytest

`at
cd /d path\to\libDiff
py -3 -m pip install -e .[dev]
`

On this machine Anaconda works well:

`at
C:\Users\USER\anaconda3\python.exe -m pip install -e .[dev]
`

## Quick start

`at
py -3 -m pytest -q
py -3 -m libdiff --help
py -3 -m libdiff discover D:\workspace\project\grok\pharosc-8.5\synopsys
py -3 -m libdiff analyze D:\workspace\project\grok\pharosc-8.5\synopsys\sxlib013.lib
py -3 -m libdiff compare tests\fixtures\stdcell_base.lib tests\fixtures\stdcell_perturbed.lib --json
py -3 -m libdiff timing-qa tests\fixtures\timing_qa_left.lib tests\fixtures\timing_qa_right.lib --batch --html qa.html --csv qa.csv
py -3 -m libdiff gui tests\fixtures\example.lib
`

Or double-click 
un_libDiff.bat / scripts\run_libDiff.bat (prefers Anaconda Python with PyQt5).

## CLI

| Command | Purpose |
|---------|---------|
| discover DIR | List *.lib under a folder |
| nalyze LIB | Cell count, units, sample cells |
| compare A B | Structure-aligned numeric compare (--json / --csv) |
| 	iming-qa A B | NLDM Timing QA (--cell, --batch, --all-cells, --html, --csv, --abs-tol, --rel-tol) |
| cells LIB | List cells |
| units LIB | Show units |
| gui [LIB ...] | Launch Fluent desktop UI |

Exit code 1 from 	iming-qa means failures beyond tolerance (expected for corner diffs).

## GUI

- **Libraries** — Load file / Open folder, fnmatch filter, async load, progress + InfoBar
- **Compare** — Area / Leakage / Timing LUT tabs, matplotlib plots
- **Timing QA** — Single or **Batch** run, arc table (~6 rows default), Δ heatmap / curves, Export CSV / HTML / JSON
- **About** — Version and scope notes
- Theme: Theme.AUTO (system light / dark)

## Timing QA scope

**Covered (Liberty / NLDM):** lib-to-lib arc compare, Δ/% heatmaps, missing arcs, thresholds, batch summary, HTML/CSV.

**Not covered (commercial Qualib / Liberate LV / PrimeLib extras):** SPICE correlation, LEF/GDS/Verilog multi-view, deep CCS waveform QA, multi-PVT dashboard ECO.

## Layout

`
libdiff/
  parser/          # Liberty parser
  model/           # Library / CellView
  compare/         # diff + timing_qa + batch/HTML
  gui/             # Fluent UI + matplotlib plots
  cli.py
tests/             # fixtures + pytest
_legacy/           # original libView / libertyParser snapshots
libertyParser_src/ # vendor reference (not imported at runtime)
`

## Tests

`at
py -3 -m pytest -q
`

Includes parser, compare, empty-cell safety, Pharosc synopsys (if path present), Timing QA, batch HTML/CSV, plot smoke tests.

## License / provenance

GPL-2.0. Substantial parser and GUI ideas from yanqing.li's libertyParser / libView. See LICENSE and IMPLEMENTATION_NOTES.md.
