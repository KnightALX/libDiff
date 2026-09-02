"""Fluent navigation pages for libDiff GUI."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QGridLayout,
    QSizePolicy,
    QSplitter,
    QFormLayout,
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
    TabWidget,
    TitleLabel,
    TreeWidget,
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
        root = QVBoxLayout(self)
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
        card_layout.addWidget(self.tree)

        hint = CaptionLabel("Libraries keyed by absolute path. Check cells, then open Compare.")
        card_layout.addWidget(hint)

        root.addWidget(card, 1)


class ComparePage(QWidget):
    """Area / leakage / timing LUT tables and plots for selected cells."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("comparePage")
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        root.addWidget(TitleLabel("Compare"))
        root.addWidget(
            CaptionLabel("Area · Leakage · Timing LUT - N/A-safe display for missing values")
        )

        self.tabs = TabWidget(self)

        # --- Area ---
        area_page = QWidget()
        area_layout = QVBoxLayout(area_page)
        area_layout.setContentsMargins(8, 8, 8, 8)
        area_card = SimpleCardWidget(area_page)
        area_inner = QVBoxLayout(area_card)
        self.area_table = TableWidget(area_card)
        self.area_table.setColumnCount(3)
        self.area_table.setHorizontalHeaderLabels(["Library", "Cell", "Area"])
        self.area_table.horizontalHeader().setStretchLastSection(True)
        self.area_plot = PlotCanvas(area_card)
        self.area_plot.setMinimumHeight(220)
        area_inner.addWidget(StrongBodyLabel("Area table"))
        area_inner.addWidget(self.area_table, 1)
        area_inner.addWidget(StrongBodyLabel("Area chart"))
        area_inner.addWidget(self.area_plot)
        area_layout.addWidget(area_card)
        self.tabs.addTab(area_page, "Area")

        # --- Leakage ---
        leak_page = QWidget()
        leak_layout = QVBoxLayout(leak_page)
        leak_layout.setContentsMargins(8, 8, 8, 8)
        leak_card = SimpleCardWidget(leak_page)
        leak_inner = QVBoxLayout(leak_card)
        self.leak_table = TableWidget(leak_card)
        self.leak_table.setColumnCount(5)
        self.leak_table.setHorizontalHeaderLabels(["Library", "Cell", "When", "PG", "Value"])
        self.leak_table.horizontalHeader().setStretchLastSection(True)
        leak_inner.addWidget(StrongBodyLabel("Leakage power"))
        leak_inner.addWidget(self.leak_table)
        leak_layout.addWidget(leak_card)
        self.tabs.addTab(leak_page, "Leakage")

        # --- Timing LUT ---
        lut_page = QWidget()
        lut_layout = QVBoxLayout(lut_page)
        lut_layout.setContentsMargins(8, 8, 8, 8)
        lut_card = SimpleCardWidget(lut_page)
        lut_inner = QVBoxLayout(lut_card)

        controls = QGridLayout()
        controls.addWidget(BodyLabel("Pin"), 0, 0)
        self.lut_pin = ComboBox(lut_card)
        controls.addWidget(self.lut_pin, 0, 1)
        controls.addWidget(BodyLabel("Table type"), 0, 2)
        self.lut_table_type = ComboBox(lut_card)
        controls.addWidget(self.lut_table_type, 0, 3)
        self.refresh_lut_btn = PrimaryPushButton("Refresh LUT")
        controls.addWidget(self.refresh_lut_btn, 0, 4)
        controls.setColumnStretch(1, 1)
        controls.setColumnStretch(3, 1)
        lut_inner.addLayout(controls)

        self.lut_table = TableWidget(lut_card)
        self.lut_table.setColumnCount(4)
        self.lut_table.setHorizontalHeaderLabels(["Library", "Cell", "Table", "Max sample"])
        self.lut_table.horizontalHeader().setStretchLastSection(True)
        configure_adaptive_row_height(self.lut_table, default_visible_rows=6)
        self.lut_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lut_plot = PlotCanvas(lut_card)
        self.lut_plot.setMinimumHeight(240)
        # optional Δ heatmap when two libs selected
        self.lut_delta_plot = PlotCanvas(lut_card)
        self.lut_delta_plot.setMinimumHeight(200)
        lut_inner.addWidget(self.lut_table, 1)
        lut_inner.addWidget(StrongBodyLabel("LUT surface / heatmap"))
        lut_inner.addWidget(self.lut_plot)
        lut_inner.addWidget(StrongBodyLabel("LUT Δ heatmap (when 2 libs)"))
        lut_inner.addWidget(self.lut_delta_plot)
        lut_layout.addWidget(lut_card)
        self.tabs.addTab(lut_page, "Timing LUT")

        root.addWidget(self.tabs, 1)


class TimingQAPage(QWidget):
    """时序QA / Timing QA — Qualib / Liberate-LV inspired (Liberty only)."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("timingQaPage")
        self.last_report = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
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
        btns.addWidget(self.summary_label)
        ctrl.addLayout(btns)

        root.addWidget(ctrl_card)

        # --- results splitter: table | plots ---
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)

        table_card = SimpleCardWidget()
        table_l = QVBoxLayout(table_card)
        table_l.setContentsMargins(12, 12, 12, 12)
        table_l.addWidget(StrongBodyLabel("Arcs / results"))
        self.arc_table = TableWidget(table_card)
        self.arc_table.setColumnCount(8)
        self.arc_table.setHorizontalHeaderLabels(
            ["Status", "Cell", "Pin", "Related", "Table", "max_abs", "max_rel", "Index"]
        )
        self.arc_table.horizontalHeader().setStretchLastSection(True)
        configure_adaptive_row_height(self.arc_table, default_visible_rows=6)
        self.arc_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.arc_table.setSelectionBehavior(self.arc_table.SelectRows)
        self.arc_table.setSelectionMode(self.arc_table.SingleSelection)
        table_l.addWidget(self.arc_table)
        split.addWidget(table_card)

        plots_card = SimpleCardWidget()
        plots_l = QVBoxLayout(plots_card)
        plots_l.setContentsMargins(12, 12, 12, 12)
        plots_l.addWidget(StrongBodyLabel("Δ heatmap"))
        self.delta_plot = PlotCanvas(plots_card)
        self.delta_plot.setMinimumHeight(180)
        plots_l.addWidget(self.delta_plot)
        plots_l.addWidget(StrongBodyLabel("Delay curves (left vs right)"))
        self.curve_plot = PlotCanvas(plots_card)
        self.curve_plot.setMinimumHeight(160)
        plots_l.addWidget(self.curve_plot)
        plots_l.addWidget(StrongBodyLabel("Left / Right LUT"))
        lut_row = QHBoxLayout()
        self.left_lut_plot = PlotCanvas(plots_card)
        self.right_lut_plot = PlotCanvas(plots_card)
        self.left_lut_plot.setMinimumHeight(140)
        self.right_lut_plot.setMinimumHeight(140)
        lut_row.addWidget(self.left_lut_plot)
        lut_row.addWidget(self.right_lut_plot)
        plots_l.addLayout(lut_row)
        split.addWidget(plots_card)

        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 4)
        root.addWidget(split, 1)


class AboutPage(QWidget):
    """Version and FIP purpose."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("aboutPage")
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
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
                "UI: PyQt-Fluent-Widgets · Theme: AUTO (follows system light/dark).\n"
                "Parser and compare logic are unchanged from the CLI."
            )
        )
        root.addWidget(card)
        root.addStretch(1)
