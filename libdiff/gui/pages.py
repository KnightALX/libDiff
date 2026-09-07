"""Fluent navigation pages for libDiff GUI."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    ComboBox,
    DoubleSpinBox,
    ElevatedCardWidget,
    IndeterminateProgressBar,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    SearchLineEdit,
    SimpleCardWidget,
    StrongBodyLabel,
    SubtitleLabel,
    TableWidget,
    TitleLabel,
    TreeWidget,
)

try:
    from qfluentwidgets import TabWidget
except ImportError:  # older PyQt-Fluent-Widgets (e.g. 1.5.x)
    from PyQt5.QtWidgets import QTabWidget as TabWidget

from libdiff.gui.layout_utils import (
    ChartTableSection,
    labeled_pane,
    make_h_splitter,
    make_v_splitter,
    wrap_card,
    wrap_in_scroll_area,
)
from libdiff.gui.plots import PlotCanvas
from libdiff.gui.table_utils import configure_adaptive_row_height
from libdiff import __version__


class LibrariesPage(QWidget):
    """Load libraries, filter cells, select cells for compare."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("librariesPage")
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QWidget(self)
        root = QVBoxLayout(body)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        header = TitleLabel("Libraries")
        subtitle = CaptionLabel(
            "Load Liberty (.lib) files · Open folder... · abs-path keys · fnmatch cell filter · check cells to compare"
        )
        root.addWidget(header)
        root.addWidget(subtitle)

        card = ElevatedCardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)

        toolbar = QHBoxLayout()
        self.load_btn = PrimaryPushButton("Load library...")
        self.open_folder_btn = PushButton("Open folder...")
        self.compare_btn = PushButton("Go to Compare")
        toolbar.addWidget(self.load_btn)
        toolbar.addWidget(self.open_folder_btn)
        toolbar.addWidget(self.compare_btn)
        toolbar.addStretch(1)
        card_layout.addLayout(toolbar)

        self.progress = IndeterminateProgressBar(self)
        self.progress.setFixedHeight(4)
        self.progress.hide()
        card_layout.addWidget(self.progress)

        self.filter_edit = SearchLineEdit(self)
        self.filter_edit.setPlaceholderText("fnmatch cell filter, e.g. INV*  (Enter to apply)")
        self.filter_edit.setClearButtonEnabled(True)
        card_layout.addWidget(self.filter_edit)

        self.tree = TreeWidget(self)
        self.tree.setHeaderLabels(["Library / Cell"])
        self.tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        card_layout.addWidget(self.tree, 1)

        hint = CaptionLabel("Libraries keyed by absolute path. Check cells, then open Compare.")
        card_layout.addWidget(hint)

        root.addWidget(card, 1)
        outer.addWidget(wrap_in_scroll_area(body), 1)


class ComparePage(QWidget):
    """Area / leakage / timing LUT — charts first, tables second."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("comparePage")
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QWidget(self)
        root = QVBoxLayout(body)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        root.addWidget(TitleLabel("Compare"))
        root.addWidget(
            CaptionLabel("Area · Leakage · Timing LUT — charts first, tables below · N/A-safe display")
        )

        self.tabs = TabWidget(self)

        # --- Area: chart TOP / table BOTTOM ---
        area_page = QWidget()
        area_layout = QVBoxLayout(area_page)
        area_layout.setContentsMargins(8, 8, 8, 8)
        area_layout.setSpacing(8)

        self.area_plot = PlotCanvas(area_page)
        self.area_plot.setMinimumHeight(160)
        self.area_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.area_table = TableWidget(area_page)
        self.area_table.setColumnCount(3)
        self.area_table.setHorizontalHeaderLabels(["Library", "Cell", "Area"])
        self.area_table.horizontalHeader().setStretchLastSection(True)
        self.area_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        configure_adaptive_row_height(
            self.area_table, default_visible_rows=3, enforce_minimum=False
        )

        area_section = ChartTableSection(
            self.area_plot,
            self.area_table,
            chart_title="Area chart",
            table_title="Area table",
            parent=area_page,
            top_stretch=4,
            bottom_stretch=1,
            initial_sizes=[780, 180],
            top_ratio=0.80,
        )
        area_layout.addWidget(area_section, 1)
        self.tabs.addTab(area_page, "Area")

        # --- Leakage: table-only (no plot drawn by main_window) — give stretch room ---
        leak_page = QWidget()
        leak_layout = QVBoxLayout(leak_page)
        leak_layout.setContentsMargins(8, 8, 8, 8)
        leak_layout.setSpacing(8)

        leak_card = SimpleCardWidget(leak_page)
        leak_inner = QVBoxLayout(leak_card)
        leak_inner.setContentsMargins(12, 12, 12, 12)
        leak_inner.setSpacing(8)
        leak_inner.addWidget(StrongBodyLabel("Leakage power"))
        self.leak_table = TableWidget(leak_card)
        self.leak_table.setColumnCount(5)
        self.leak_table.setHorizontalHeaderLabels(["Library", "Cell", "When", "PG", "Value"])
        self.leak_table.horizontalHeader().setStretchLastSection(True)
        self.leak_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.leak_table.setMinimumHeight(120)
        leak_inner.addWidget(self.leak_table, 1)
        leak_layout.addWidget(leak_card, 1)
        self.tabs.addTab(leak_page, "Leakage")

        # --- Timing LUT: controls → plot stack TOP / lut_table BOTTOM ---
        lut_page = QWidget()
        lut_layout = QVBoxLayout(lut_page)
        lut_layout.setContentsMargins(8, 8, 8, 8)
        lut_layout.setSpacing(8)

        ctrl_card = SimpleCardWidget(lut_page)
        ctrl_inner = QVBoxLayout(ctrl_card)
        ctrl_inner.setContentsMargins(12, 10, 12, 10)
        ctrl_inner.setSpacing(8)

        # Row1: Pin, Table type, Refresh
        row1 = QGridLayout()
        row1.setHorizontalSpacing(10)
        row1.setVerticalSpacing(6)
        row1.addWidget(BodyLabel("Pin"), 0, 0)
        self.lut_pin = ComboBox(ctrl_card)
        row1.addWidget(self.lut_pin, 0, 1)
        row1.addWidget(BodyLabel("Table type"), 0, 2)
        self.lut_table_type = ComboBox(ctrl_card)
        row1.addWidget(self.lut_table_type, 0, 3)
        self.refresh_lut_btn = PrimaryPushButton("Apply / 应用")
        row1.addWidget(self.refresh_lut_btn, 0, 4)
        row1.setColumnStretch(1, 1)
        row1.setColumnStretch(3, 1)
        ctrl_inner.addLayout(row1)

        # Row2: Badge, View mode, Cross mode
        row2 = QGridLayout()
        row2.setHorizontalSpacing(10)
        row2.setVerticalSpacing(6)
        self.lut_badge = CaptionLabel("LUT: —")
        row2.addWidget(self.lut_badge, 0, 0, 1, 2)
        row2.addWidget(BodyLabel("View / 视图"), 0, 2)
        self.lut_view_mode = ComboBox(ctrl_card)
        self.lut_view_mode.addItems(["单点 Point", "扫线 Line", "扫面 Surface"])
        row2.addWidget(self.lut_view_mode, 0, 3)
        row2.addWidget(BodyLabel("Cross / 对齐"), 0, 4)
        self.lut_index_mode = ComboBox(ctrl_card)
        self.lut_index_mode.addItems(["Cross-index (physical)", "Positional"])
        row2.addWidget(self.lut_index_mode, 0, 5)
        self.lut_cross_mode = ComboBox(ctrl_card)
        self.lut_cross_mode.addItems(["left_grid", "union", "intersection"])
        row2.addWidget(self.lut_cross_mode, 0, 6)
        row2.setColumnStretch(1, 1)
        row2.setColumnStretch(3, 1)
        ctrl_inner.addLayout(row2)

        # Row3: Index pickers + line-fix axis (enable/disable by mode)
        row3 = QGridLayout()
        row3.setHorizontalSpacing(10)
        row3.setVerticalSpacing(6)
        self.lut_i1_label = BodyLabel("Index_1 (slew)")
        row3.addWidget(self.lut_i1_label, 0, 0)
        self.lut_i1 = ComboBox(ctrl_card)
        self.lut_i1.setMinimumWidth(100)
        row3.addWidget(self.lut_i1, 0, 1)
        self.lut_i1_custom = LineEdit(ctrl_card)
        self.lut_i1_custom.setPlaceholderText("默认 33点 / custom i1")
        row3.addWidget(self.lut_i1_custom, 0, 2)

        self.lut_i2_label = BodyLabel("Index_2 (load)")
        row3.addWidget(self.lut_i2_label, 0, 3)
        self.lut_i2 = ComboBox(ctrl_card)
        self.lut_i2.setMinimumWidth(90)
        row3.addWidget(self.lut_i2, 0, 4)
        self.lut_i2_custom = LineEdit(ctrl_card)
        self.lut_i2_custom.setPlaceholderText("默认 33点 / custom i2")
        row3.addWidget(self.lut_i2_custom, 0, 5)
        row3.setColumnStretch(1, 1)
        row3.setColumnStretch(4, 1)
        ctrl_inner.addLayout(row3)

        row3b = QHBoxLayout()
        row3b.addWidget(BodyLabel("Line scan / 扫线轴"))
        self.lut_line_fix = ComboBox(ctrl_card)
        self.lut_line_fix.addItems(
            [
                "固定 Index_1 扫 Index_2",
                "固定 Index_2 扫 Index_1",
            ]
        )
        self.lut_line_fix.setMinimumWidth(220)
        row3b.addWidget(self.lut_line_fix)
        row3b.addStretch(1)
        # Keep legacy lut_slice hidden for attr compatibility (synced from view mode)
        self.lut_slice = ComboBox(ctrl_card)
        self.lut_slice.addItems(
            [
                "Full heatmap",
                "Fix index_1 → curve vs load",
                "Fix index_2 → curve vs slew",
            ]
        )
        self.lut_slice.setVisible(False)
        row3b.addWidget(self.lut_slice)
        self.lut_probe_btn = PrimaryPushButton("Probe / 探针")
        row3b.addWidget(self.lut_probe_btn)
        ctrl_inner.addLayout(row3b)

        self.lut_probe_caption = CaptionLabel(
            "Point: pick i1/i2 (default 33点) · Line: fix one axis · Surface: heatmap + marginals"
        )
        ctrl_inner.addWidget(self.lut_probe_caption)
        lut_layout.addWidget(ctrl_card)

        self.lut_plot = PlotCanvas(lut_page)
        self.lut_plot.setMinimumHeight(220)
        self.lut_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lut_delta_plot = PlotCanvas(lut_page)
        self.lut_delta_plot.setMinimumHeight(220)
        self.lut_delta_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lut_marginal_plot = PlotCanvas(lut_page)
        self.lut_marginal_plot.setMinimumHeight(180)
        self.lut_marginal_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        lut_plot_pane = labeled_pane("LUT / left · Line overlay", self.lut_plot, min_height=220)
        lut_delta_pane = labeled_pane("Δ / right heatmap", self.lut_delta_plot, min_height=220)
        plot_stack = make_h_splitter(lut_plot_pane, lut_delta_pane, left_stretch=1, right_stretch=1)
        plot_stack.setMinimumHeight(220)

        marg_pane = labeled_pane("Marginals · mean(|Δ|) / max(|Δ|)", self.lut_marginal_plot, min_height=180)
        plot_column = QWidget(lut_page)
        plot_col_l = QVBoxLayout(plot_column)
        plot_col_l.setContentsMargins(0, 0, 0, 0)
        plot_col_l.setSpacing(6)
        plot_col_l.addWidget(plot_stack, 3)
        plot_col_l.addWidget(marg_pane, 2)

        self.lut_table = TableWidget(lut_page)
        self.lut_table.setColumnCount(4)
        self.lut_table.setHorizontalHeaderLabels(["Library", "Cell", "Table", "Max sample"])
        self.lut_table.horizontalHeader().setStretchLastSection(True)
        configure_adaptive_row_height(
            self.lut_table, default_visible_rows=3, enforce_minimum=False
        )
        self.lut_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        table_pane = labeled_pane("LUT samples", self.lut_table, min_height=64)
        lut_split = make_v_splitter(
            plot_column,
            table_pane,
            top_stretch=4,
            bottom_stretch=1,
            initial_sizes=[820, 160],
            top_min=280,
            bottom_min=64,
        )
        lut_layout.addWidget(lut_split, 1)
        self.tabs.addTab(lut_page, "Timing LUT")

        root.addWidget(self.tabs, 1)
        outer.addWidget(wrap_in_scroll_area(body), 1)


class TimingQAPage(QWidget):
    """时序QA / Timing QA — chart-first vertical split (Liberty only)."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("timingQaPage")
        self.last_report = None
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QWidget(self)
        root = QVBoxLayout(body)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        root.addWidget(TitleLabel("时序QA / Timing QA"))
        root.addWidget(
            CaptionLabel(
                "NLDM arc compare · missing arcs · abs/rel thresholds · Δ heatmap · "
                "Liberty only (no SPICE) · Qualib / Liberate-LV inspired"
            )
        )

        # --- controls card ---
        ctrl_card = ElevatedCardWidget(self)
        ctrl = QVBoxLayout(ctrl_card)
        ctrl.setContentsMargins(16, 16, 16, 16)
        ctrl.setSpacing(10)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        form.addWidget(BodyLabel("Left lib"), 0, 0)
        self.left_lib = ComboBox(ctrl_card)
        form.addWidget(self.left_lib, 0, 1)

        form.addWidget(BodyLabel("Right lib"), 0, 2)
        self.right_lib = ComboBox(ctrl_card)
        form.addWidget(self.right_lib, 0, 3)

        form.addWidget(BodyLabel("Cell filter"), 1, 0)
        self.cell_filter = SearchLineEdit(ctrl_card)
        self.cell_filter.setPlaceholderText("fnmatch e.g. INV* / inv_x1")
        self.cell_filter.setClearButtonEnabled(True)
        form.addWidget(self.cell_filter, 1, 1)

        form.addWidget(BodyLabel("Cell"), 1, 2)
        self.cell_combo = ComboBox(ctrl_card)
        form.addWidget(self.cell_combo, 1, 3)

        form.addWidget(BodyLabel("Table type"), 2, 0)
        self.table_type = ComboBox(ctrl_card)
        self.table_type.addItems(
            [
                "(all NLDM)",
                "cell_rise",
                "cell_fall",
                "rise_transition",
                "fall_transition",
                "rise_constraint",
                "fall_constraint",
            ]
        )
        form.addWidget(self.table_type, 2, 1)

        form.addWidget(BodyLabel("Abs tol"), 2, 2)
        self.abs_tol = DoubleSpinBox(ctrl_card)
        self.abs_tol.setDecimals(6)
        self.abs_tol.setRange(0.0, 1e6)
        self.abs_tol.setValue(0.0001)
        self.abs_tol.setSingleStep(0.0001)
        form.addWidget(self.abs_tol, 2, 3)

        form.addWidget(BodyLabel("Rel tol"), 3, 0)
        self.rel_tol = DoubleSpinBox(ctrl_card)
        self.rel_tol.setDecimals(4)
        self.rel_tol.setRange(0.0, 10.0)
        self.rel_tol.setValue(0.01)
        self.rel_tol.setSingleStep(0.01)
        form.addWidget(self.rel_tol, 3, 1)

        form.setColumnStretch(1, 1)
        form.setColumnStretch(3, 1)
        ctrl.addLayout(form)

        btns = QHBoxLayout()
        self.run_btn = PrimaryPushButton("Run Timing QA")
        self.batch_btn = PushButton("Batch / 批跑")
        self.export_csv_btn = PushButton("Export CSV")
        self.export_html_btn = PushButton("Export HTML")
        self.export_json_btn = PushButton("Export JSON")
        btns.addWidget(self.run_btn)
        btns.addWidget(self.batch_btn)
        btns.addWidget(self.export_csv_btn)
        btns.addWidget(self.export_html_btn)
        btns.addWidget(self.export_json_btn)
        btns.addStretch(1)
        self.summary_label = CaptionLabel("Not run yet")
        self.index_align_label = CaptionLabel("Index: —")
        btns.addWidget(self.summary_label)
        btns.addWidget(self.index_align_label)
        ctrl.addLayout(btns)

        root.addWidget(ctrl_card)

        # --- charts TOP as tabs (Δ / Curves / LUTs) / arc_table BOTTOM ---
        charts_tabs = TabWidget()

        self.delta_plot = PlotCanvas()
        self.delta_plot.setMinimumHeight(160)
        self.delta_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        delta_page = QWidget()
        delta_l = QVBoxLayout(delta_page)
        delta_l.setContentsMargins(4, 4, 4, 4)
        delta_l.addWidget(self.delta_plot, 1)
        charts_tabs.addTab(delta_page, "扫面 Δ heatmap")

        self.curve_plot = PlotCanvas()
        self.curve_plot.setMinimumHeight(160)
        self.curve_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        curve_page = QWidget()
        curve_l = QVBoxLayout(curve_page)
        curve_l.setContentsMargins(4, 4, 4, 4)
        curve_l.addWidget(self.curve_plot, 1)
        charts_tabs.addTab(curve_page, "扫线 Curves")

        self.left_lut_plot = PlotCanvas()
        self.right_lut_plot = PlotCanvas()
        self.left_lut_plot.setMinimumHeight(140)
        self.right_lut_plot.setMinimumHeight(140)
        self.left_lut_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.right_lut_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left_pane = labeled_pane("Left LUT", self.left_lut_plot, min_height=140)
        right_pane = labeled_pane("Right LUT", self.right_lut_plot, min_height=140)
        lut_h = make_h_splitter(left_pane, right_pane, left_stretch=1, right_stretch=1)
        lut_page = QWidget()
        lut_l = QVBoxLayout(lut_page)
        lut_l.setContentsMargins(4, 4, 4, 4)
        lut_l.addWidget(lut_h, 1)
        charts_tabs.addTab(lut_page, "LUTs")

        charts_tabs.setMinimumHeight(160)
        charts_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        table_card = SimpleCardWidget()
        table_l = QVBoxLayout(table_card)
        table_l.setContentsMargins(12, 12, 12, 12)
        table_l.setSpacing(8)
        table_l.addWidget(StrongBodyLabel("Arcs / results"))
        self.arc_table = TableWidget(table_card)
        self.arc_table.setColumnCount(8)
        self.arc_table.setHorizontalHeaderLabels(
            ["Status", "Cell", "Pin", "Related", "Table", "max_abs", "max_rel", "Index"]
        )
        self.arc_table.horizontalHeader().setStretchLastSection(True)
        configure_adaptive_row_height(
            self.arc_table, default_visible_rows=3, enforce_minimum=False
        )
        self.arc_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.arc_table.setSelectionBehavior(self.arc_table.SelectRows)
        self.arc_table.setSelectionMode(self.arc_table.SingleSelection)
        table_l.addWidget(self.arc_table, 1)

        results_split = make_v_splitter(
            charts_tabs,
            table_card,
            top_stretch=4,
            bottom_stretch=1,
            initial_sizes=[780, 180],
            top_min=160,
            bottom_min=64,
        )
        root.addWidget(results_split, 1)
        outer.addWidget(wrap_in_scroll_area(body), 1)


class PPAPage(QWidget):
    """Stdcell PPA compare — chart-first tabs (Dashboard / Area / Timing / Data)."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("ppaPage")
        self.last_report = None
        self.last_html_path = ""
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QWidget(self)
        root = QVBoxLayout(body)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        root.addWidget(TitleLabel("PPA / 功耗面积时序"))
        root.addWidget(
            CaptionLabel(
                "Stdcell PPA vs baseline · Area / Leakage / typical delay · "
                "series-aware charts · one-page HTML · SRAM mode stub later"
            )
        )

        ctrl_card = ElevatedCardWidget(self)
        ctrl = QVBoxLayout(ctrl_card)
        ctrl.setContentsMargins(16, 16, 16, 16)
        ctrl.setSpacing(10)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        form.addWidget(BodyLabel("Baseline (left)"), 0, 0)
        self.left_lib = ComboBox(ctrl_card)
        form.addWidget(self.left_lib, 0, 1)

        form.addWidget(BodyLabel("Compare (right)"), 0, 2)
        self.right_lib = ComboBox(ctrl_card)
        form.addWidget(self.right_lib, 0, 3)

        form.addWidget(BodyLabel("Cell filter"), 1, 0)
        self.cell_filter = SearchLineEdit(ctrl_card)
        self.cell_filter.setPlaceholderText("fnmatch e.g. INV*")
        self.cell_filter.setClearButtonEnabled(True)
        form.addWidget(self.cell_filter, 1, 1)

        form.addWidget(BodyLabel("Mode"), 1, 2)
        self.mode_combo = ComboBox(ctrl_card)
        self.mode_combo.addItems(["stdcell", "sram (stub)"])
        form.addWidget(self.mode_combo, 1, 3)

        form.addWidget(BodyLabel("Notes"), 2, 0)
        self.notes_edit = LineEdit(ctrl_card)
        self.notes_edit.setPlaceholderText("Optional cover notes for HTML report")
        form.addWidget(self.notes_edit, 2, 1, 1, 3)

        form.setColumnStretch(1, 1)
        form.setColumnStretch(3, 1)
        ctrl.addLayout(form)

        btns = QHBoxLayout()
        self.run_btn = PrimaryPushButton("Run PPA")
        self.export_html_btn = PushButton("Export HTML")
        self.export_csv_btn = PushButton("Export CSV")
        self.export_json_btn = PushButton("Export JSON")
        btns.addWidget(self.run_btn)
        btns.addWidget(self.export_html_btn)
        btns.addWidget(self.export_csv_btn)
        btns.addWidget(self.export_json_btn)
        btns.addStretch(1)
        self.summary_label = CaptionLabel("Not run yet")
        btns.addWidget(self.summary_label)
        ctrl.addLayout(btns)
        self.report_path_label = CaptionLabel("")
        ctrl.addWidget(self.report_path_label)
        root.addWidget(ctrl_card)

        # Chart-first tabs: Dashboard / Area / Timing / Data
        self.tabs = TabWidget(self)

        # Dashboard — radar + KPI summary
        dash_page = QWidget()
        dash_l = QVBoxLayout(dash_page)
        dash_l.setContentsMargins(8, 8, 8, 8)
        dash_l.setSpacing(8)
        kpi_card = SimpleCardWidget(dash_page)
        kpi_inner = QVBoxLayout(kpi_card)
        kpi_inner.setContentsMargins(12, 10, 12, 10)
        kpi_inner.setSpacing(4)
        kpi_inner.addWidget(StrongBodyLabel("Summary"))
        self.kpi_label = CaptionLabel("Run PPA to populate radar and KPIs.")
        kpi_inner.addWidget(self.kpi_label)
        dash_l.addWidget(kpi_card)
        self.radar_plot = PlotCanvas(dash_page)
        self.radar_plot.setMinimumHeight(200)
        self.radar_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        dash_l.addWidget(wrap_card("PPA radar", self.radar_plot), 1)
        self.tabs.addTab(dash_page, "Dashboard")

        # Area — series bars dominate
        area_page = QWidget()
        area_l = QVBoxLayout(area_page)
        area_l.setContentsMargins(8, 8, 8, 8)
        self.area_plot = PlotCanvas(area_page)
        self.area_plot.setMinimumHeight(200)
        self.area_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        area_l.addWidget(wrap_card("Area / Leakage by drive", self.area_plot), 1)
        self.tabs.addTab(area_page, "Area")

        # Timing — delay overlay
        timing_page = QWidget()
        timing_l = QVBoxLayout(timing_page)
        timing_l.setContentsMargins(8, 8, 8, 8)
        self.delay_plot = PlotCanvas(timing_page)
        self.delay_plot.setMinimumHeight(200)
        self.delay_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        timing_l.addWidget(wrap_card("Delay vs load overlay", self.delay_plot), 1)
        self.tabs.addTab(timing_page, "Timing")

        # Data — full metrics table
        data_page = QWidget()
        data_l = QVBoxLayout(data_page)
        data_l.setContentsMargins(8, 8, 8, 8)
        data_card = SimpleCardWidget(data_page)
        data_inner = QVBoxLayout(data_card)
        data_inner.setContentsMargins(12, 12, 12, 12)
        data_inner.setSpacing(8)
        data_inner.addWidget(StrongBodyLabel("PPA table (baseline / %Δ)"))
        self.ppa_table = TableWidget(data_card)
        self.ppa_table.setColumnCount(8)
        self.ppa_table.setHorizontalHeaderLabels(
            ["Cell", "Family", "Area %", "Leak %", "Delay %", "Area abs", "Leak abs", "Delay abs"]
        )
        self.ppa_table.horizontalHeader().setStretchLastSection(True)
        configure_adaptive_row_height(
            self.ppa_table, default_visible_rows=3, enforce_minimum=False
        )
        self.ppa_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        data_inner.addWidget(self.ppa_table, 1)
        data_l.addWidget(data_card, 1)
        self.tabs.addTab(data_page, "Data")

        root.addWidget(self.tabs, 1)
        outer.addWidget(wrap_in_scroll_area(body), 1)


class AboutPage(QWidget):
    """Version and FIP purpose."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("aboutPage")
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QWidget(self)
        root = QVBoxLayout(body)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        root.addWidget(TitleLabel("About libDiff"))

        card = CardWidget(self)
        inner = QVBoxLayout(card)
        inner.setContentsMargins(20, 20, 20, 20)
        inner.setSpacing(8)
        inner.addWidget(SubtitleLabel("libDiff  v%s" % __version__))
        inner.addWidget(
            BodyLabel(
                "Liberty (.lib) compare and analysis for FIP stdcell / SRAM design teams.\n"
                "FIP 标准单元 / SRAM Liberty 对比分析工具。"
            )
        )
        inner.addWidget(
            CaptionLabel(
                "Load multiple .lib files · filter cells · compare area, leakage, and timing LUTs.\n"
                "Timing QA: NLDM Δ matrices, missing arcs, thresholds (no SPICE).\n"
                "PPA: stdcell Area/Leakage/typical-delay vs baseline (SRAM later).\n"
                "UI: PyQt-Fluent-Widgets · Theme: AUTO (follows system light/dark).\n"
                "Parser and compare logic are unchanged from the CLI."
            )
        )
        root.addWidget(card)
        root.addStretch(1)
        outer.addWidget(wrap_in_scroll_area(body), 1)
