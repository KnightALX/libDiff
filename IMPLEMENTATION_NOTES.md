# IMPLEMENTATION_NOTES

Date: 2026-09-02 (Asia/Shanghai)

## What was done

Rewrote the flat `libView.py` + `libertyParser.py` tree into an installable `libdiff` package with CLI, GUI, and pytest fixtures aimed at FIP stdcell/SRAM Liberty/CCS compare.

## Review fixes mapped

1. Library raises `ParseError` / `LibDiffError` / `UnitConflictError` — no `sys.exit` in library modules (CLI/GUI may exit after catching).
2. Missing area/leakage/timing use `.get` / `None` / `"N/A"` via `CellView`.
3. `safe_float()` returns `None` for missing/invalid (never coerced to 0 for diffs).
4. Parser is pure Python on Windows; `genCellLibFile` rewritten without grep/awk.
5. Bus filter uses `busName` (fixed NameError from `bundleName`).
6. `Library.key` / GUI dict keys are absolute paths.
7. OCV tables use correct `ocv_sigma_*_constraint` spelling; unknown/legacy tables kept.
8. Cell select via `fnmatch.fnmatchcase`.
9. Unit conflicts raise / block numeric compare; `--convert-units` records conversion scales.
10. `getLibPinInfo(cellList=selected)`; module parse cache by abs path.
11. GUI: `LoadLibraryWorker(QThread)`, `QMessageBox`, window title `libDiff`.
12. Real numeric abs/rel deltas for area/leakage/LUT samples; CLI `--json`.
13. Configurable `DEFAULT_SERIES_PATTERNS` in `gui/main_window.py`.
14. pytest suite under `tests/`.
15. Runtime does not import `libertyParser_src/`; originals moved to `_legacy/`.

## How to verify

```bat
cd D:\workspace\project\grok\libDiff
C:\Users\USER\anaconda3\python.exe -m pytest -q
C:\Users\USER\anaconda3\python.exe -m libdiff --help
C:\Users\USER\anaconda3\python.exe -m libdiff compare tests\fixtures\stdcell_base.lib tests\fixtures\stdcell_perturbed.lib --json
```

## Remaining gaps / follow-ups

- GUI is a thinner LUT browser than legacy libView (shared timing LUT tab; not every legacy combo path ported 1:1).
- Unit conversion adjusts report metadata; LUT values are not auto-rescaled in the JSON payload yet (conflict still blocks by default).
- CCS waveform tables are parsed/retained but not specialized beyond generic LUT flatten.
- Optional: delete top-level `libertyParser.py` / `libView.py` after team confirms `_legacy/` + package path.
- `libertyParser_src/` kept as vendor reference only.

## Pharosc Synopsys support (2026-09)

Parser now flattens inline { / } (string-aware), strips trailing /* */ and // comments, allows cell(name) without space, and raises ParseError with line numbers instead of IndexError when no group is open. Added libdiff/discover.py, libdiff/analyze.py, CLI discover/nalyze, GUI **Open folder...**, and pharosc series sort patterns.

## 0.3.0 changes (2026-09-02)

- Unified matplotlib plot theme (libdiff/gui/plots.py): soft bg, colorblind palette, grid/spine cleanup; fixed UTF-8 corruption; prefer 2D heatmap over 3D.
- Timing QA **batch** API (
un_timing_qa_batch) + self-contained **HTML** report (inline CSS, optional base64 heatmaps) and batch CSV.
- CLI: 	iming-qa --batch / --all-cells / --html / --csv.
- GUI Timing QA: Batch / Export HTML buttons + summary label.
- Version aligned to **0.3.0** in libdiff/__init__.py and pyproject.toml.
- Still matplotlib-only (no Plotly / PyQtWebEngine).
