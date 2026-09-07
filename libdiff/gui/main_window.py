"""libDiff Fluent main window (PyQt-Fluent-Widgets)."""

from __future__ import annotations

import fnmatch
import json
import os
import sys
from collections import OrderedDict
from typing import Dict, List, Optional, Sequence

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import QApplication, QFileDialog, QTableWidgetItem, QTreeWidgetItem

from qfluentwidgets import (
    FluentIcon,
    FluentWindow,
    InfoBar,
    InfoBarPosition,
    MessageBox,
    NavigationItemPosition,
    Theme,
    setTheme,
)

from libdiff.gui.pages import AboutPage, ComparePage, LibrariesPage, PPAPage, TimingQAPage
from libdiff.gui.workers import LoadLibraryWorker
from libdiff.model.library import Library, NA
from libdiff.compare.ppa import (
    compare_ppa,
    export_ppa_csv,
    export_ppa_html,
    export_ppa_json,
    format_ppa_summary,
)
from libdiff.compare.timing_qa import (
    timing_qa,
    export_timing_qa_csv,
    export_timing_qa_json,
    delta_matrices,
    run_timing_qa_batch,
    export_timing_qa_batch_csv,
    export_timing_qa_html,
)
from libdiff.compare.lut_index import (
    classify_lut,
    cross_index_delta,
    probe_points,
    resolve_indices,
    sample_lut,
    slice_curve,
)

from libdiff.series import DEFAULT_SERIES_PATTERNS, sort_cells_with_size


class MainWindow(FluentWindow):
    """Fluent shell: Libraries / Compare / Timing QA / PPA / About."""

    def __init__(self, input_files: Optional[Sequence[str]] = None):
        super().__init__()
        self.libs: Dict[str, Library] = OrderedDict()  # abs path -> Library
        self._workers: List[LoadLibraryWorker] = []
        self._active_loads = 0
        self.series_patterns = list(DEFAULT_SERIES_PATTERNS)

        self.setWindowTitle("libDiff - FIP stdcell/SRAM Liberty compare")
        self.resize(1440, 900)

        self.librariesPage = LibrariesPage(self)
        self.comparePage = ComparePage(self)
        self.timingQaPage = TimingQAPage(self)
        self.ppaPage = PPAPage(self)
        self.aboutPage = AboutPage(self)

        self.addSubInterface(self.librariesPage, FluentIcon.LIBRARY, "Libraries")
        self.addSubInterface(self.comparePage, FluentIcon.VIEW, "Compare")
        # SPEED_OFF ≈ timing; SIMILAR as fallback theme for compare-like QA
        qa_icon = getattr(FluentIcon, "SPEED_OFF", None) or getattr(
            FluentIcon, "SIMILAR", FluentIcon.SYNC
        )
        self.addSubInterface(self.timingQaPage, qa_icon, "时序QA")
        ppa_icon = getattr(FluentIcon, "SPEED_HIGH", None) or getattr(
            FluentIcon, "PIE_SINGLE", None
        ) or getattr(FluentIcon, "MARKET", FluentIcon.VIEW)
        self.addSubInterface(self.ppaPage, ppa_icon, "PPA")
        self.addSubInterface(
            self.aboutPage,
            FluentIcon.INFO,
            "About",
            position=NavigationItemPosition.BOTTOM,
        )

        self._wire()
        for f in input_files or []:
            self.load_library_async(f)

    def _wire(self):
        page = self.librariesPage
        page.load_btn.clicked.connect(lambda: self.load_library_async())
        page.open_folder_btn.clicked.connect(self.open_folder_async)
        page.compare_btn.clicked.connect(lambda: self.switchTo(self.comparePage))
        page.filter_edit.searchSignal.connect(lambda _t: self._apply_filter())
        page.filter_edit.returnPressed.connect(self._apply_filter)
        page.tree.itemChanged.connect(self._on_tree_changed)
        self.comparePage.refresh_lut_btn.clicked.connect(self._refresh_lut)
        self.comparePage.lut_probe_btn.clicked.connect(self._probe_lut)
        self.comparePage.lut_index_mode.currentIndexChanged.connect(lambda _i: self._refresh_lut())
        self.comparePage.lut_cross_mode.currentIndexChanged.connect(lambda _i: self._refresh_lut())
        self.comparePage.lut_slice.currentIndexChanged.connect(lambda _i: self._refresh_lut())
        self.comparePage.lut_i1.currentIndexChanged.connect(lambda _i: None)
        self.comparePage.lut_i2.currentIndexChanged.connect(lambda _i: None)

        tq = self.timingQaPage
        tq.run_btn.clicked.connect(self._run_timing_qa)
        tq.batch_btn.clicked.connect(self._run_timing_qa_batch)
        tq.export_csv_btn.clicked.connect(self._export_timing_qa_csv)
        tq.export_html_btn.clicked.connect(self._export_timing_qa_html)
        tq.export_json_btn.clicked.connect(self._export_timing_qa_json)
        tq.arc_table.itemSelectionChanged.connect(self._on_timing_arc_selected)
        tq.left_lib.currentTextChanged.connect(lambda _t: self._refresh_timing_qa_cells())
        tq.right_lib.currentTextChanged.connect(lambda _t: self._refresh_timing_qa_cells())
        tq.cell_filter.textChanged.connect(lambda _t: self._refresh_timing_qa_cells())
        tq.cell_filter.searchSignal.connect(lambda _t: self._refresh_timing_qa_cells())

        ppa = self.ppaPage
        ppa.run_btn.clicked.connect(self._run_ppa)
        ppa.export_html_btn.clicked.connect(self._export_ppa_html)
        ppa.export_csv_btn.clicked.connect(self._export_ppa_csv)
        ppa.export_json_btn.clicked.connect(self._export_ppa_json)
        ppa.left_lib.currentTextChanged.connect(lambda _t: None)
        ppa.right_lib.currentTextChanged.connect(lambda _t: None)

    # --- load ---

    def load_library_async(self, path: str = ""):
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "Load library file", ".", "Library Files (*.lib)"
            )
        if not path:
            return
        path = os.path.abspath(path)
        if path in self.libs:
            InfoBar.warning(
                title="Already loaded",
                content=path,
                duration=4000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        self._set_loading(True)
        worker = LoadLibraryWorker(path)
        worker.finished_ok.connect(self._on_lib_loaded)
        worker.failed.connect(self._on_lib_failed)
        self._workers.append(worker)
        worker.start()

    def open_folder_async(self, directory: str = ""):
        """Discover and async-load all *.lib files in a folder (non-recursive)."""
        if not directory:
            directory = QFileDialog.getExistingDirectory(
                self, "Open folder with Liberty libraries", "."
            )
        if not directory:
            return
        try:
            from libdiff.discover import discover_libs

            entries = discover_libs(directory, recursive=False)
        except Exception as exc:  # noqa: BLE001
            MessageBox("libDiff - folder error", str(exc), self).exec()
            return
        if not entries:
            InfoBar.warning(
                title="No .lib files",
                content=directory,
                duration=4000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        InfoBar.info(
            title="Loading folder",
            content="%d .lib file(s) from %s" % (len(entries), directory),
            duration=3500,
            position=InfoBarPosition.TOP,
            parent=self,
        )
        for entry in entries:
            self.load_library_async(entry.path)

    def _set_loading(self, active: bool):

        if active:
            self._active_loads += 1
        else:
            self._active_loads = max(0, self._active_loads - 1)
        bar = self.librariesPage.progress
        if self._active_loads > 0:
            bar.show()
            bar.start()
        else:
            bar.stop()
            bar.hide()

    def _on_lib_loaded(self, lib: Library):
        self._set_loading(False)
        self.libs[lib.key] = lib
        InfoBar.success(
            title="Library loaded",
            content="%s (%d cells)" % (lib.display_name, len(lib.cell_names())),
            duration=3500,
            position=InfoBarPosition.TOP,
            parent=self,
        )
        self._rebuild_tree()
        self._refresh_timing_qa_lib_combos()
        self._refresh_ppa_lib_combos()

    def _on_lib_failed(self, message: str):
        self._set_loading(False)
        # Critical blocking dialog for hard load failures
        MessageBox("libDiff - load error", message, self).exec()

    # --- tree / filter ---

    def _apply_filter(self):
        self._rebuild_tree()

    def _rebuild_tree(self):
        tree = self.librariesPage.tree
        tree.blockSignals(True)
        tree.clear()
        pattern = self.librariesPage.filter_edit.text().strip() or None
        for key, lib in self.libs.items():
            lib_item = QTreeWidgetItem([lib.display_name + "  [" + key + "]"])
            lib_item.setData(0, Qt.UserRole, ("lib", key))
            lib_item.setForeground(0, QBrush(QColor("#0078D4")))
            cells = lib.select_cells(pattern) if pattern else lib.cell_names()
            for cell in sort_cells_with_size(cells, self.series_patterns):
                cell_item = QTreeWidgetItem([cell])
                cell_item.setData(0, Qt.UserRole, ("cell", key, cell))
                cell_item.setCheckState(0, Qt.Unchecked)
                cell_item.setForeground(0, QBrush(QColor("#107C10")))
                lib_item.addChild(cell_item)
            tree.addTopLevelItem(lib_item)
            lib_item.setExpanded(True)
        tree.blockSignals(False)

    def _selected_cells(self):
        selected = []
        tree = self.librariesPage.tree
        root = tree.invisibleRootItem()
        for i in range(root.childCount()):
            lib_item = root.child(i)
            for j in range(lib_item.childCount()):
                cell_item = lib_item.child(j)
                if cell_item.checkState(0) == Qt.Checked:
                    role = cell_item.data(0, Qt.UserRole)
                    if role and role[0] == "cell":
                        selected.append((role[1], role[2]))  # (lib_key, cell)
        return selected

    def _on_tree_changed(self, item, column):
        if item.checkState(0) in (Qt.Checked, Qt.Unchecked):
            self._refresh_views()

    # --- compare views (preserve original business logic) ---

    def _refresh_views(self):
        selected = self._selected_cells()
        cp = self.comparePage

        # Area
        cp.area_table.setRowCount(0)
        labels, values = [], []
        for lib_key, cell in selected:
            lib = self.libs[lib_key]
            cv = lib.cell(cell)
            r = cp.area_table.rowCount()
            cp.area_table.insertRow(r)
            cp.area_table.setItem(r, 0, QTableWidgetItem(lib.display_name))
            cp.area_table.setItem(r, 1, QTableWidgetItem(cell))
            cp.area_table.setItem(r, 2, QTableWidgetItem(cv.area_display()))
            labels.append("%s/%s" % (lib.display_name, cell))
            values.append(cv.area)
        if labels:
            cp.area_plot.draw_bar(labels, values, title="Area", ylabel="area")
        else:
            cp.area_plot.draw_empty()

        # Leakage
        cp.leak_table.setRowCount(0)
        for lib_key, cell in selected:
            lib = self.libs[lib_key]
            for e in lib.cell(cell).leakage_entries():
                r = cp.leak_table.rowCount()
                cp.leak_table.insertRow(r)
                cp.leak_table.setItem(r, 0, QTableWidgetItem(lib.display_name))
                cp.leak_table.setItem(r, 1, QTableWidgetItem(cell))
                cp.leak_table.setItem(r, 2, QTableWidgetItem(str(e["when"])))
                cp.leak_table.setItem(r, 3, QTableWidgetItem(str(e["related_pg_pin"])))
                val = e["value"]
                cp.leak_table.setItem(
                    r, 4, QTableWidgetItem(NA if val is None else str(val))
                )

        # populate LUT combos from first selection
        pins = set()
        ttypes = set()
        for lib_key, cell in selected:
            for t in self.libs[lib_key].cell(cell).timing_tables():
                pins.add(t["pin"])
                ttypes.add(t["table_type"])
        cur_pin = cp.lut_pin.currentText()
        cur_tt = cp.lut_table_type.currentText()
        cp.lut_pin.blockSignals(True)
        cp.lut_table_type.blockSignals(True)
        cp.lut_pin.clear()
        cp.lut_table_type.clear()
        cp.lut_pin.addItems(sorted(pins) or [""])
        cp.lut_table_type.addItems(sorted(ttypes) or [""])
        if cur_pin in pins:
            cp.lut_pin.setCurrentText(cur_pin)
        if cur_tt in ttypes:
            cp.lut_table_type.setCurrentText(cur_tt)
        cp.lut_pin.blockSignals(False)
        cp.lut_table_type.blockSignals(False)
        self._refresh_lut()


    def _lut_selected_float(self, combo, custom_edit):
        """Prefer custom LineEdit float; else combo text."""
        txt = (custom_edit.text() or "").strip()
        if txt:
            try:
                return float(txt)
            except ValueError:
                pass
        cur = (combo.currentText() or "").strip()
        if not cur:
            return None
        try:
            return float(cur)
        except ValueError:
            return None

    def _populate_lut_index_combos(self, tables):
        cp = self.comparePage
        i1s, i2s = set(), set()
        for _lk, _cell, t in tables:
            a, b, _, _, _ = resolve_indices(self.libs.get(_lk), t)
            for x in a:
                i1s.add(float(x))
            for x in b:
                i2s.add(float(x))
        def _refill(combo, values):
            cur = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            items = ["%.6g" % v for v in sorted(values)]
            combo.addItems(items or [""])
            if cur in items:
                combo.setCurrentText(cur)
            combo.blockSignals(False)
        _refill(cp.lut_i1, i1s)
        _refill(cp.lut_i2, i2s)

    def _refresh_lut(self):
        selected = self._selected_cells()
        cp = self.comparePage
        want_pin = cp.lut_pin.currentText()
        want_tt = cp.lut_table_type.currentText()
        cp.lut_table.setRowCount(0)
        matched_tables = []
        for lib_key, cell in selected:
            for t in self.libs[lib_key].cell(cell).timing_tables():
                if want_pin and t["pin"] != want_pin:
                    continue
                if want_tt and t["table_type"] != want_tt:
                    continue
                flat = [v for row in t["values"] for v in row if v is not None]
                r = cp.lut_table.rowCount()
                cp.lut_table.insertRow(r)
                cp.lut_table.setItem(
                    r, 0, QTableWidgetItem(self.libs[lib_key].display_name)
                )
                cp.lut_table.setItem(r, 1, QTableWidgetItem(cell))
                cp.lut_table.setItem(r, 2, QTableWidgetItem(t["table_type"]))
                cp.lut_table.setItem(
                    r, 3, QTableWidgetItem(str(max(flat) if flat else NA))
                )
                matched_tables.append((lib_key, cell, t))

        self._last_lut_tables = matched_tables
        self._populate_lut_index_combos(matched_tables)

        mode_txt = cp.lut_index_mode.currentText() if hasattr(cp, "lut_index_mode") else ""
        use_cross = "Cross" in mode_txt or "physical" in mode_txt.lower()
        slice_txt = cp.lut_slice.currentText() if hasattr(cp, "lut_slice") else "Full heatmap"
        cross_mode = cp.lut_cross_mode.currentText() if hasattr(cp, "lut_cross_mode") else "left_grid"

        # Badge
        if matched_tables:
            lk, _c, t0 = matched_tables[0]
            cls = classify_lut(t0)
            i1, i2, tname, v1, v2 = resolve_indices(self.libs[lk], t0)
            cp.lut_badge.setText(
                "LUT: %s | tmpl=%s | %s / %s"
                % (cls.upper(), tname or "—", v1 or "index_1", v2 or ("index_2" if i2 else "—"))
            )
        else:
            cp.lut_badge.setText("LUT: —")

        # Primary plot: heatmap or slice curve
        if not matched_tables:
            cp.lut_plot.draw_empty()
            cp.lut_delta_plot.draw_empty("Need 2 libs/cells for Δ")
            return

        lk0, _c0, last = matched_tables[-1]
        fix_i1 = self._lut_selected_float(cp.lut_i1, cp.lut_i1_custom)
        fix_i2 = self._lut_selected_float(cp.lut_i2, cp.lut_i2_custom)

        if "curve vs load" in slice_txt:
            fixed = fix_i1 if fix_i1 is not None else (last.get("index_1") or [0])[0]
            xs, ys = slice_curve(last, axis="index_2", fixed_value=fixed, method="interp", lib=self.libs[lk0])
            series = {"LUT": ys}
            if len(matched_tables) >= 2:
                lk1, _c1, t1 = matched_tables[0]
                xs2, ys2 = slice_curve(t1, axis="index_2", fixed_value=fixed, method="interp", lib=self.libs[lk1])
                # align xs to union labels for overlay — use first xs
                series = {
                    self.libs[matched_tables[0][0]].display_name: ys2,
                    self.libs[matched_tables[-1][0]].display_name: ys,
                }
                xs = xs2 if len(xs2) >= len(xs) else xs
            cp.lut_plot.draw_delay_curves(
                xs, series, title="vs load @ i1=%s" % fixed, xlabel="index_2 (load)", ylabel=want_tt or "value"
            )
        elif "curve vs slew" in slice_txt:
            fixed = fix_i2 if fix_i2 is not None else ((last.get("index_2") or [0])[0] if last.get("index_2") else 0)
            xs, ys = slice_curve(last, axis="index_1", fixed_value=fixed, method="interp", lib=self.libs[lk0])
            series = {"LUT": ys}
            if len(matched_tables) >= 2:
                lk1, _c1, t1 = matched_tables[0]
                xs2, ys2 = slice_curve(t1, axis="index_1", fixed_value=fixed, method="interp", lib=self.libs[lk1])
                series = {
                    self.libs[matched_tables[0][0]].display_name: ys2,
                    self.libs[matched_tables[-1][0]].display_name: ys,
                }
                xs = xs2 if len(xs2) >= len(xs) else xs
            cp.lut_plot.draw_delay_curves(
                xs, series, title="vs slew @ i2=%s" % fixed, xlabel="index_1 (slew)", ylabel=want_tt or "value"
            )
        else:
            i1, i2, _, _, _ = resolve_indices(self.libs[lk0], last)
            cp.lut_plot.draw_lut_heatmap(
                last["values"],
                index_1=i1,
                index_2=i2,
                title=want_tt or "LUT",
            )

        # Delta plot when >= 2 selections
        if len(matched_tables) >= 2:
            t0 = matched_tables[0][2]
            t1 = matched_tables[1][2]
            lib0 = self.libs[matched_tables[0][0]]
            lib1 = self.libs[matched_tables[1][0]]
            if use_cross:
                dm = cross_index_delta(t0, t1, mode=cross_mode, left_lib=lib0, right_lib=lib1)
                cp.lut_delta_plot.draw_heatmap(
                    dm["abs_matrix"],
                    xlabels=dm.get("index_2") or None,
                    ylabels=dm.get("index_1") or None,
                    title="Δ cross (%s) %s − %s"
                    % (
                        cross_mode,
                        lib1.display_name,
                        lib0.display_name,
                    ),
                    cmap="RdBu_r",
                    center=0,
                )
            else:
                dm = delta_matrices(t0.get("values") or [], t1.get("values") or [])
                i1, i2, _, _, _ = resolve_indices(lib0, t0)
                cp.lut_delta_plot.draw_heatmap(
                    dm["abs_matrix"],
                    xlabels=i2 or t1.get("index_2"),
                    ylabels=i1 or t1.get("index_1"),
                    title="Δ positional (%s − %s)" % (lib1.display_name, lib0.display_name),
                    cmap="RdBu_r",
                    center=0,
                )
        else:
            cp.lut_delta_plot.draw_empty("Need 2 libs/cells for Δ")

    def _probe_lut(self):
        cp = self.comparePage
        tables = getattr(self, "_last_lut_tables", None) or []
        if not tables:
            self._refresh_lut()
            tables = getattr(self, "_last_lut_tables", None) or []
        if not tables:
            cp.lut_probe_caption.setText("Probe: no LUT selected")
            return
        x1 = self._lut_selected_float(cp.lut_i1, cp.lut_i1_custom)
        x2 = self._lut_selected_float(cp.lut_i2, cp.lut_i2_custom)
        if x1 is None:
            cp.lut_probe_caption.setText("Probe: pick index_1 (slew)")
            return
        parts = []
        left_v = right_v = None
        for idx, (lk, cell, t) in enumerate(tables[:2]):
            lib = self.libs[lk]
            i1, i2, _, _, _ = resolve_indices(lib, t)
            # 1D may not need x2
            cls = classify_lut(t)
            xx2 = x2 if cls == "2d" else x2
            val = sample_lut(t.get("values") or [], i1, i2, x1, xx2 if cls == "2d" else None)
            if cls == "2d" and x2 is None and i2:
                # default nearest first load if not specified
                val = sample_lut(t.get("values") or [], i1, i2, x1, float(i2[0]))
                xx2 = float(i2[0])
            label = lib.display_name
            parts.append("%s=%s" % (label, val))
            if idx == 0:
                left_v = val
            elif idx == 1:
                right_v = val
        delta_txt = ""
        if left_v is not None and right_v is not None:
            d = right_v - left_v
            pct = None if left_v == 0 else (d / left_v) * 100.0
            delta_txt = "  Δ=%s  %%Δ=%s" % (
                ("%.6g" % d),
                ("—" if pct is None else "%.3g%%" % pct),
            )
        elif left_v is None or (len(tables) > 1 and right_v is None):
            delta_txt = "  (out_of_range)"
        cp.lut_probe_caption.setText(
            "Probe @ (i1=%s, i2=%s): %s%s"
            % (x1, x2, " | ".join(parts), delta_txt)
        )


    # --- Timing QA ---

    def _lib_display_map(self) -> Dict[str, str]:
        """display_name -> abs key (last wins if duplicate basenames)."""
        return {lib.display_name: key for key, lib in self.libs.items()}


    def _refresh_ppa_lib_combos(self):
        ppa = self.ppaPage
        names = [lib.display_name for lib in self.libs.values()]
        for combo in (ppa.left_lib, ppa.right_lib):
            cur = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(names)
            if cur in names:
                combo.setCurrentText(cur)
            combo.blockSignals(False)
        if len(names) >= 2:
            if ppa.left_lib.currentIndex() < 0:
                ppa.left_lib.setCurrentIndex(0)
            if not ppa.right_lib.currentText() or ppa.right_lib.currentText() == ppa.left_lib.currentText():
                ppa.right_lib.setCurrentIndex(1 if ppa.left_lib.currentIndex() == 0 else 0)

    def _run_ppa(self):
        ppa = self.ppaPage
        dmap = self._lib_display_map()
        left_key = dmap.get(ppa.left_lib.currentText())
        right_key = dmap.get(ppa.right_lib.currentText())
        if not left_key or not right_key:
            InfoBar.warning(
                title="Select libraries",
                content="Load and select Baseline / Compare .lib first",
                duration=4000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        mode_txt = ppa.mode_combo.currentText() or "stdcell"
        mode = "sram" if mode_txt.startswith("sram") else "stdcell"
        pattern = (ppa.cell_filter.text() or "").strip() or None
        try:
            report = compare_ppa(
                self.libs[left_key],
                self.libs[right_key],
                cell_pattern=pattern,
                mode=mode,
                notes=(ppa.notes_edit.text() or "").strip(),
            )
        except Exception as exc:  # noqa: BLE001
            MessageBox("PPA error", str(exc), self).exec()
            return
        ppa.last_report = report
        self._fill_ppa_table(report)
        self._draw_ppa_plots(report)
        s = report.get("summary") or {}
        ppa.summary_label.setText(
            "cells=%s  Area%%=%s  Leak%%=%s  Delay%%=%s"
            % (
                s.get("n_cells_compared"),
                ("N/A" if s.get("mean_area_pct") is None else "%+.2f" % s.get("mean_area_pct")),
                ("N/A" if s.get("mean_leakage_pct") is None else "%+.2f" % s.get("mean_leakage_pct")),
                ("N/A" if s.get("mean_delay_pct") is None else "%+.2f" % s.get("mean_delay_pct")),
            )
        )
        if hasattr(ppa, "kpi_label"):
            ppa.kpi_label.setText(ppa.summary_label.text())
        InfoBar.success(
            title="PPA done",
            content=ppa.summary_label.text(),
            duration=4000,
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _fill_ppa_table(self, report: dict):
        ppa = self.ppaPage
        ppa.ppa_table.setRowCount(0)
        for name in sorted((report.get("cells") or {}).keys()):
            c = report["cells"][name]
            a, lk, d = c.get("area") or {}, c.get("leakage") or {}, c.get("delay") or {}

            def pct(v):
                return "N/A" if v is None else ("%+.3f%%" % v)

            def absv(v):
                return "N/A" if v is None else ("%.6g" % v)

            vals = [
                name,
                str(c.get("series_family") or ""),
                pct(a.get("pct")),
                pct(lk.get("pct")),
                pct(d.get("pct")),
                absv(a.get("abs")),
                absv(lk.get("abs")),
                absv(d.get("abs")),
            ]
            r = ppa.ppa_table.rowCount()
            ppa.ppa_table.insertRow(r)
            for col, v in enumerate(vals):
                ppa.ppa_table.setItem(r, col, QTableWidgetItem(v))

    def _draw_ppa_plots(self, report: dict):
        ppa = self.ppaPage
        if report.get("mode") == "sram" or (report.get("summary") or {}).get("stub"):
            ppa.area_plot.draw_empty("SRAM mode stub")
            ppa.delay_plot.draw_empty("SRAM mode stub")
            ppa.radar_plot.draw_empty("SRAM mode stub")
            return
        try:
            from libdiff.plotting.ppa_charts import (
                figure_area_series_bars,
                figure_delay_load_overlay,
                figure_ppa_radar,
            )

            fig = figure_area_series_bars(report, metric="area", fig=ppa.area_plot.figure)
            if fig is None:
                ppa.area_plot.draw_empty("No area series")
            else:
                try:
                    fig.tight_layout()
                except Exception:
                    pass
                ppa.area_plot.draw()

            fig = figure_delay_load_overlay(report, fig=ppa.delay_plot.figure)
            if fig is None:
                ppa.delay_plot.draw_empty("No delay curves")
            else:
                try:
                    fig.tight_layout()
                except Exception:
                    pass
                ppa.delay_plot.draw()

            fig = figure_ppa_radar(report, fig=ppa.radar_plot.figure)
            if fig is None:
                ppa.radar_plot.draw_empty("No radar metrics")
            else:
                try:
                    fig.tight_layout()
                except Exception:
                    pass
                ppa.radar_plot.draw()
        except Exception as exc:  # noqa: BLE001
            ppa.area_plot.draw_empty(str(exc))
            ppa.delay_plot.draw_empty()
            ppa.radar_plot.draw_empty()

    def _export_ppa_html(self):

        ppa = self.ppaPage
        if not ppa.last_report:
            InfoBar.warning(
                title="No report",
                content="Run PPA first",
                duration=3000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PPA HTML", "ppa_report.html", "HTML (*.html)"
        )
        if not path:
            return
        export_ppa_html(ppa.last_report, path=path, embed_plots=True)
        ppa.last_html_path = path
        ppa.report_path_label.setText("HTML: %s" % path)
        InfoBar.success(
            title="HTML exported",
            content=path,
            duration=3000,
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _export_ppa_csv(self):
        ppa = self.ppaPage
        if not ppa.last_report:
            InfoBar.warning(
                title="No report",
                content="Run PPA first",
                duration=3000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PPA CSV", "ppa_report.csv", "CSV (*.csv)"
        )
        if not path:
            return
        export_ppa_csv(ppa.last_report, path=path)
        InfoBar.success(
            title="CSV exported",
            content=path,
            duration=3000,
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _export_ppa_json(self):
        ppa = self.ppaPage
        if not ppa.last_report:
            InfoBar.warning(
                title="No report",
                content="Run PPA first",
                duration=3000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PPA JSON", "ppa_report.json", "JSON (*.json)"
        )
        if not path:
            return
        export_ppa_json(ppa.last_report, path=path)
        InfoBar.success(
            title="JSON exported",
            content=path,
            duration=3000,
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _refresh_timing_qa_lib_combos(self):
        tq = self.timingQaPage
        names = [lib.display_name for lib in self.libs.values()]
        for combo in (tq.left_lib, tq.right_lib):
            cur = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(names)
            if cur in names:
                combo.setCurrentText(cur)
            combo.blockSignals(False)
        if len(names) >= 2 and not tq.right_lib.currentText():
            tq.right_lib.setCurrentIndex(1)
        elif len(names) >= 2 and tq.left_lib.currentText() == tq.right_lib.currentText():
            tq.right_lib.setCurrentIndex(1 if tq.left_lib.currentIndex() == 0 else 0)
        self._refresh_timing_qa_cells()

    def _refresh_timing_qa_cells(self):
        tq = self.timingQaPage
        dmap = self._lib_display_map()
        left_key = dmap.get(tq.left_lib.currentText())
        right_key = dmap.get(tq.right_lib.currentText())
        cells = set()
        if left_key and left_key in self.libs:
            cells |= set(self.libs[left_key].cell_names())
        if right_key and right_key in self.libs:
            cells &= set(self.libs[right_key].cell_names()) if cells else set(
                self.libs[right_key].cell_names()
            )
            if left_key and left_key in self.libs:
                cells = set(self.libs[left_key].cell_names()) & set(
                    self.libs[right_key].cell_names()
                )
        filt = (tq.cell_filter.text() or "").strip()
        if filt:
            cells = {c for c in cells if fnmatch.fnmatch(c, filt)}
        ordered = sort_cells_with_size(sorted(cells), self.series_patterns)
        cur = tq.cell_combo.currentText()
        tq.cell_combo.blockSignals(True)
        tq.cell_combo.clear()
        tq.cell_combo.addItem("(all filtered)")
        tq.cell_combo.addItems(ordered)
        if cur and cur in ordered:
            tq.cell_combo.setCurrentText(cur)
        tq.cell_combo.blockSignals(False)

    def _run_timing_qa(self):
        tq = self.timingQaPage
        dmap = self._lib_display_map()
        left_key = dmap.get(tq.left_lib.currentText())
        right_key = dmap.get(tq.right_lib.currentText())
        if not left_key or not right_key:
            InfoBar.warning(
                title="Select libraries",
                content="Load and select Left / Right .lib first",
                duration=4000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        cell_combo = tq.cell_combo.currentText()
        cells = None
        pattern = (tq.cell_filter.text() or "").strip() or None
        if cell_combo and cell_combo != "(all filtered)":
            cells = [cell_combo]
            pattern = None
        tt = tq.table_type.currentText()
        table_types = None
        if tt and not tt.startswith("(all"):
            table_types = [tt]
        try:
            report = timing_qa(
                self.libs[left_key],
                self.libs[right_key],
                cells=cells,
                cell_pattern=pattern,
                table_types=table_types,
                abs_tol=float(tq.abs_tol.value()),
                rel_tol=float(tq.rel_tol.value()),
                include_matrices=True,
                index_mode="auto",
                cross_mode="left_grid",
            )
        except Exception as exc:  # noqa: BLE001
            MessageBox("Timing QA error", str(exc), self).exec()
            return

        tq.last_report = report
        self._fill_timing_qa_table(report)
        s = report.get("summary") or {}
        tq.summary_label.setText(
            "Arcs=%s  Fail=%s  Missing=%s (L=%s R=%s)"
            % (
                s.get("n_arcs_matched"),
                s.get("n_fail"),
                s.get("n_missing"),
                s.get("n_left_only"),
                s.get("n_right_only"),
            )
        )
        InfoBar.success(
            title="Timing QA 完成",
            content="matched=%s fail=%s missing=%s"
            % (s.get("n_arcs_matched"), s.get("n_fail"), s.get("n_missing")),
            duration=4000,
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _fill_timing_qa_table(self, report: dict):
        tq = self.timingQaPage
        tq.arc_table.setRowCount(0)
        rows = []
        for a in report.get("arcs") or []:
            rows.append(("arc", a))
        for a in report.get("left_only") or []:
            rows.append(("left_only", a))
        for a in report.get("right_only") or []:
            rows.append(("right_only", a))

        for kind, a in rows:
            r = tq.arc_table.rowCount()
            tq.arc_table.insertRow(r)
            if kind == "arc":
                status = str(a.get("status") or "")
                max_abs = a.get("max_abs")
                max_rel = a.get("max_rel")
                align = a.get("index_alignment")
            elif kind == "left_only":
                status = "left-only"
                max_abs = max_rel = align = ""
            else:
                status = "right-only"
                max_abs = max_rel = align = ""
            vals = [
                status,
                str(a.get("cell") or ""),
                str(a.get("pin") or ""),
                str(a.get("related_pin") or ""),
                str(a.get("table_type") or ""),
                "" if max_abs in (None, "") else ("%.6g" % max_abs),
                "" if max_rel in (None, "") else ("%.4g" % max_rel),
                str(align or ""),
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setData(Qt.UserRole, (kind, a))
                if status in ("fail", "left-only", "right-only"):
                    item.setForeground(QBrush(QColor("#C42B1C")))
                elif status == "ok":
                    item.setForeground(QBrush(QColor("#107C10")))
                tq.arc_table.setItem(r, c, item)

        if tq.arc_table.rowCount():
            tq.arc_table.selectRow(0)
            self._on_timing_arc_selected()
        else:
            tq.delta_plot.draw_empty()
            tq.curve_plot.draw_empty()
            tq.left_lut_plot.draw_empty()
            tq.right_lut_plot.draw_empty()

    def _on_timing_arc_selected(self):
        tq = self.timingQaPage
        items = tq.arc_table.selectedItems()
        if not items:
            return
        role = items[0].data(Qt.UserRole)
        if not role:
            return
        kind, a = role
        if kind != "arc":
            tq.delta_plot.draw_empty(str(kind))
            tq.curve_plot.draw_empty()
            tq.left_lut_plot.draw_empty()
            tq.right_lut_plot.draw_empty()
            return

        align = a.get("index_alignment") or "—"
        mode_used = a.get("index_mode_used") or "—"
        if hasattr(tq, "index_align_label"):
            tq.index_align_label.setText(
                "Index: %s | mode=%s | oor=%s"
                % (align, mode_used, (a.get("out_of_range") or {}).get("total", 0))
            )
        abs_m = a.get("abs_matrix") or []
        tq.delta_plot.draw_heatmap(
            abs_m,
            xlabels=a.get("grid_index_2") or a.get("index_2_left") or a.get("index_2_right"),
            ylabels=a.get("grid_index_1") or a.get("index_1_left") or a.get("index_1_right"),
            title="Δ %s %s" % (a.get("cell"), a.get("table_type")),
            cmap="RdBu_r",
            center=0,
        )
        left_v = a.get("values_left") or []
        right_v = a.get("values_right") or []
        tq.left_lut_plot.draw_lut_heatmap(
            left_v,
            index_1=a.get("index_1_left"),
            index_2=a.get("index_2_left"),
            title="Left",
        )
        tq.right_lut_plot.draw_lut_heatmap(
            right_v,
            index_1=a.get("index_1_right"),
            index_2=a.get("index_2_right"),
            title="Right",
        )
        # delay vs load at first slew index
        idx2 = a.get("index_2_left") or a.get("index_2_right") or []
        if left_v and right_v and idx2:
            series = {
                "left": left_v[0] if left_v else [],
                "right": right_v[0] if right_v else [],
            }
            # pad to len(idx2)
            for k in list(series.keys()):
                row = list(series[k])
                while len(row) < len(idx2):
                    row.append(None)
                series[k] = row[: len(idx2)]
            tq.curve_plot.draw_delay_curves(
                idx2,
                series,
                title="vs load @ index_1[0]",
                xlabel="index_2 (load)",
                ylabel=str(a.get("table_type") or "value"),
            )
        else:
            tq.curve_plot.draw_empty("No curve data")


    def _run_timing_qa_batch(self):
        """Batch Timing QA over common/filtered cells; fill table + summary."""
        tq = self.timingQaPage
        dmap = self._lib_display_map()
        left_key = dmap.get(tq.left_lib.currentText())
        right_key = dmap.get(tq.right_lib.currentText())
        if not left_key or not right_key:
            InfoBar.warning(
                title="Select libraries",
                content="Load and select Left / Right .lib first",
                duration=4000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        pattern = (tq.cell_filter.text() or "").strip() or None
        cell_combo = tq.cell_combo.currentText()
        cells = None
        if cell_combo and cell_combo != "(all filtered)":
            cells = [cell_combo]
            pattern = None
        tt = tq.table_type.currentText()
        table_types = None
        if tt and not tt.startswith("(all"):
            table_types = [tt]
        try:
            report = run_timing_qa_batch(
                self.libs[left_key],
                self.libs[right_key],
                cells=cells,
                cell_pattern=pattern,
                table_types=table_types,
                abs_tol=float(tq.abs_tol.value()),
                rel_tol=float(tq.rel_tol.value()),
                include_matrices=True,
            )
        except Exception as exc:  # noqa: BLE001
            MessageBox("Timing QA batch error", str(exc), self).exec()
            return

        tq.last_report = report
        self._fill_timing_qa_table(report)
        s = report.get("summary") or {}
        tq.summary_label.setText(
            "BATCH cells=%s arcs=%s fail=%s missing=%s"
            % (
                s.get("n_cells_compared"),
                s.get("n_arcs_matched"),
                s.get("n_fail"),
                s.get("n_missing"),
            )
        )
        InfoBar.success(
            title="Timing QA batch done",
            content="cells=%s fail=%s missing=%s"
            % (s.get("n_cells_compared"), s.get("n_fail"), s.get("n_missing")),
            duration=4500,
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _export_timing_qa_html(self):
        tq = self.timingQaPage
        if not tq.last_report:
            InfoBar.warning(
                title="No report",
                content="Run Timing QA / Batch first",
                duration=3000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Timing QA HTML", "timing_qa.html", "HTML (*.html)"
        )
        if not path:
            return
        export_timing_qa_html(tq.last_report, path=path, embed_plots=True)
        InfoBar.success(
            title="HTML exported",
            content=path,
            duration=3000,
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _export_timing_qa_csv(self):
        tq = self.timingQaPage
        if not tq.last_report:
            InfoBar.warning(
                title="No report",
                content="Run Timing QA first",
                duration=3000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Timing QA CSV", "timing_qa.csv", "CSV (*.csv)"
        )
        if not path:
            return
        report = tq.last_report
        if (report.get("summary") or {}).get("mode") == "batch" or "cells" in report:
            export_timing_qa_batch_csv(report, path=path)
        else:
            export_timing_qa_csv(report, path=path)
        InfoBar.success(
            title="CSV exported",
            content=path,
            duration=3000,
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _export_timing_qa_json(self):
        tq = self.timingQaPage
        if not tq.last_report:
            InfoBar.warning(
                title="No report",
                content="Run Timing QA first",
                duration=3000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Timing QA JSON", "timing_qa.json", "JSON (*.json)"
        )
        if not path:
            return
        export_timing_qa_json(tq.last_report, path=path)
        InfoBar.success(
            title="JSON exported",
            content=path,
            duration=3000,
            position=InfoBarPosition.TOP,
            parent=self,
        )


def run_gui(input_files: Optional[Sequence[str]] = None) -> int:
    # Theme.AUTO follows OS light/dark - polished default for EDA desktop use.
    setTheme(Theme.AUTO)
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow(input_files)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(run_gui(sys.argv[1:]))
