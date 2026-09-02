# libDiff

Liberty (`.lib`) **compare / analysis / Timing QA** for chip **FIP** design teams -
stdcell and SRAM libraries (NLDM and CCS-style tables).

**Version: 0.3.0**

Built for FIP library bring-up and corner QA. Parser and GUI ideas draw from
[libView](https://github.com/liyanqing1987/libView) and
[libertyParser](https://github.com/liyanqing1987/libertyParser) (GPL-2.0),
reworked into an installable package with Fluent UI, Pharosc Synopsys support,
and batch Timing QA reports.

## Features

- Pure-Python Liberty parser (Windows-safe; no external `grep` / `awk` / `os.system`)
- Library identity by **absolute path** (same basename in different folders is OK)
- N/A-safe accessors when area / leakage / timing are missing
- Structure-aligned numeric compare (area, leakage, LUT samples) with abs / rel deltas
- Unit conflict detection for time and power units (block or convert with clear errors)
- CLI (`python -m libdiff`) with JSON / CSV / HTML export
- **Timing QA** (Qualib / Liberate-LV inspired, Liberty-only)
  - Arc alignment, delta / percent matrices, missing arcs, basic monotonicity checks
  - **Batch / multi-cell** runs with fail ranking
  - Self-contained **HTML** report (inline CSS; optional heatmap PNGs) and CSV
- **Fluent GUI** (PyQt-Fluent-Widgets): Libraries / Compare / Timing QA / About
- Unified **matplotlib** plot theme (bar / heatmap / delay curves)
- Timing LUT and arc tables default to about **6** visible rows and grow with window height
- Folder discover / analyze (for example Pharosc `synopsys/*.lib`)

## Requirements

- Python 3.8+
- Runtime: `numpy`, `matplotlib`, `PyQt5`, `PyQt-Fluent-Widgets`
- Dev: `pytest`

```bat
cd /d path\to\libDiff
py -3 -m pip install -e ".[dev]"
```

Anaconda works well on Windows:

```bat
C:\Users\USER\anaconda3\python.exe -m pip install -e ".[dev]"
```

## Quick start

```bat
py -3 -m pytest -q
py -3 -m libdiff --help
py -3 -m libdiff discover D:\workspace\project\grok\pharosc-8.5\synopsys
py -3 -m libdiff analyze D:\workspace\project\grok\pharosc-8.5\synopsys\sxlib013.lib
py -3 -m libdiff compare tests\fixtures\stdcell_base.lib tests\fixtures\stdcell_perturbed.lib --json
py -3 -m libdiff timing-qa tests\fixtures\timing_qa_left.lib tests\fixtures\timing_qa_right.lib --batch --html qa_report.html --csv qa_report.csv
py -3 -m libdiff gui tests\fixtures\example.lib
```

Or double-click `run_libDiff.bat` / `scripts\run_libDiff.bat`
(prefers Anaconda Python when PyQt5 is available there).

## CLI

| Command | Purpose |
|---------|---------|
| `discover DIR` | List `*.lib` files under a directory |
| `analyze LIB` | Cell count, units, sample cells |
| `compare A B` | Structure-aligned numeric compare (`--json` / `--csv`) |
| `timing-qa A B` | NLDM Timing QA (`--cell`, `--batch`, `--all-cells`, `--html`, `--csv`, `--abs-tol`, `--rel-tol`) |
| `cells LIB` | List cells |
| `units LIB` | Show units |
| `gui [LIB ...]` | Launch Fluent desktop UI |

`timing-qa` exits with code `1` when arcs exceed tolerance (useful in CI for corner diffs).

## GUI

- **Libraries** - load file or open folder, fnmatch filter, async load, progress + InfoBar
- **Compare** - Area / Leakage / Timing LUT tabs with matplotlib plots
- **Timing QA** - single or batch run, arc table, delta heatmap / curves, export CSV / HTML / JSON
- **About** - version and scope notes
- Theme follows system light / dark (`Theme.AUTO`)

### Plots and tables

- Soft background, readable fonts, colorblind-friendly series colors
- Heatmaps: centered diverging map for signed deltas, gray for missing, labeled colorbars
- Bars: missing values shown as N/A (not forced to zero)
- LUT / Timing QA tables start at about six visible rows and expand when the window grows

## Timing QA scope

**Covered (Liberty / NLDM):** library-to-library arc compare, delta / percent views, missing arcs, thresholds, batch summary, HTML / CSV export.

**Not covered yet:** SPICE correlation, LEF / GDS / Verilog multi-view, deep CCS waveform QA, multi-PVT dashboard / ECO suggestions.

## Layout

```text
libdiff/
  parser/     # Liberty parser
  model/      # Library / CellView
  compare/    # numeric diff + Timing QA + batch HTML/CSV
  gui/        # Fluent UI + matplotlib plots
  cli.py
tests/        # fixtures + pytest
_legacy/      # original libView / libertyParser snapshots
libertyParser_src/  # vendor reference (not imported at runtime)
```

## Tests

```bat
py -3 -m pytest -q
```

Coverage includes parser, compare, empty-cell safety, Pharosc synopsys (when that path exists), Timing QA, batch HTML/CSV, and plot smoke tests.

## License

GPL-2.0. See `LICENSE` and `IMPLEMENTATION_NOTES.md` for provenance.

<!-- docs refresh: 2026-09-02 -->
