from __future__ import annotations

from math import pi

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ..analysis_charts import RealCampbellChart
from ..analysis_pipeline import AnalysisPipelineResult
from ..icons import engineering_icon
from ..models import ProjectModel
from ..widgets import Card, ProjectInfoCard, SectionCard, configure_table, item


class KpiCard(Card):
    def __init__(self, title: str, value: str, unit: str, icon_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent, object_name="kpiCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 14, 10)
        layout.setSpacing(12)
        icon = QLabel()
        icon.setPixmap(engineering_icon(icon_name, 42, "#0f4f89").pixmap(42, 42))
        layout.addWidget(icon)
        text = QVBoxLayout()
        text.setSpacing(0)
        title_label = QLabel(title)
        title_label.setObjectName("kpiTitle")
        text.addWidget(title_label)
        row = QHBoxLayout()
        self.value_label = QLabel(value)
        self.value_label.setObjectName("kpiValue")
        row.addWidget(self.value_label)
        self.unit_label = QLabel(unit)
        self.unit_label.setObjectName("muted")
        row.addWidget(self.unit_label, 0, Qt.AlignmentFlag.AlignBottom)
        row.addStretch(1)
        text.addLayout(row)
        layout.addLayout(text, 1)

    def set_value(self, value: str, unit: str | None = None) -> None:
        self.value_label.setText(value)
        if unit is not None:
            self.unit_label.setText(unit)


class AnalysisResultsPage(QWidget):
    """Results workspace populated only by the latest real ROSS pipeline result."""

    def __init__(self, project: ProjectModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.result: AnalysisPipelineResult | None = None
        self._selected_analysis = "campbell"

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)
        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(10)
        root.addLayout(center, 1)

        head = Card()
        hl = QVBoxLayout(head)
        hl.setContentsMargins(14, 10, 14, 10)
        hl.setSpacing(8)
        title_row = QHBoxLayout()
        title = QLabel("Analysis Results")
        title.setObjectName("cardHeader")
        title_row.addWidget(title)
        title_row.addWidget(QLabel(project.name))
        title_row.addStretch(1)
        self.result_state = QLabel("No real analysis executed")
        self.result_state.setObjectName("muted")
        title_row.addWidget(self.result_state)
        hl.addLayout(title_row)

        tabs = QHBoxLayout()
        self.analysis_buttons: dict[str, QPushButton] = {}
        for key, text in [
            ("static", "Static"),
            ("modal", "Modal"),
            ("critical", "Critical Speed"),
            ("campbell", "Campbell"),
            ("ump", "UMP"),
            ("unbalance", "Unbalance / Probes"),
        ]:
            button = QPushButton(text)
            button.setCheckable(True)
            button.setObjectName("primaryButton" if key == "campbell" else "outlineButton")
            button.setMinimumHeight(36)
            button.clicked.connect(lambda checked=False, k=key: self._select_analysis(k))
            tabs.addWidget(button)
            self.analysis_buttons[key] = button
        self.analysis_buttons["campbell"].setChecked(True)
        tabs.addStretch(1)
        hl.addLayout(tabs)
        center.addWidget(head)

        kpis = QHBoxLayout()
        kpis.setSpacing(10)
        self.kpi_first = KpiCard("First Critical Speed", "—", "rpm", "speed")
        self.kpi_second = KpiCard("Second Critical Speed", "—", "rpm", "speed")
        self.kpi_response = KpiCard("Max Probe Amplitude", "—", "µm", "amplification")
        self.kpi_damping = KpiCard("Min Rated Damping", "—", "%", "shield")
        for card in (self.kpi_first, self.kpi_second, self.kpi_response, self.kpi_damping):
            kpis.addWidget(card, 1)
        center.addLayout(kpis)

        main = QHBoxLayout()
        main.setSpacing(10)
        chart_card = Card()
        cl = QVBoxLayout(chart_card)
        cl.setContentsMargins(12, 10, 12, 10)
        self.chart_header = QLabel("Campbell Diagram — real ROSS result")
        self.chart_header.setObjectName("cardHeader")
        cl.addWidget(self.chart_header)
        self.campbell_chart = RealCampbellChart()
        cl.addWidget(self.campbell_chart, 1)
        main.addWidget(chart_card, 3)

        table_card = Card()
        tl = QVBoxLayout(table_card)
        tl.setContentsMargins(8, 10, 8, 8)
        self.table_header = QLabel("Result Table")
        self.table_header.setObjectName("cardHeader")
        tl.addWidget(self.table_header)
        self.table = QTableWidget(0, 1)
        configure_table(self.table, row_height=30)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tl.addWidget(self.table, 1)
        main.addWidget(table_card, 2)
        center.addLayout(main, 1)

        footer = Card()
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(10, 5, 10, 5)
        self.audit_summary = QLabel("Run Analysis to populate numerical results and engineering audit gates.")
        self.audit_summary.setWordWrap(True)
        self.audit_summary.setObjectName("muted")
        fl.addWidget(self.audit_summary, 1)
        center.addWidget(footer)

        right_l = QVBoxLayout()
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(10)
        right = QWidget()
        right.setFixedWidth(326)
        right.setLayout(right_l)
        root.addWidget(right)
        right_l.addWidget(ProjectInfoCard(project))
        right_l.addWidget(self._settings_card(), 1)
        right_l.addWidget(self._export_card())

        self._populate_empty()

    def set_results(self, result: AnalysisPipelineResult) -> None:
        self.result = result
        ump_state = " · UMP active" if result.ump_assembly is not None and result.ump_assembly.active else ""
        self.result_state.setText(f"ROSS pipeline PASS · {result.total_elapsed_s:.2f} s{ump_state}")
        self.kpi_first.set_value(f"{result.first_critical_rpm:,.0f}" if result.first_critical_rpm is not None else "None")
        self.kpi_second.set_value(f"{result.second_critical_rpm:,.0f}" if result.second_critical_rpm is not None else "None")
        self.kpi_response.set_value(f"{result.max_probe_amplitude_um:.4g}" if result.max_probe_amplitude_um is not None else "—")
        self.kpi_damping.set_value(f"{100.0 * result.min_modal_damping_ratio:.3f}" if result.min_modal_damping_ratio is not None else "—")

        self.campbell_chart.set_result(result)
        warnings = [audit for audit in result.audits if audit.severity == "warning"]
        ump_records = [audit for audit in result.audits if audit.code.startswith("UMP_")]
        self.audit_summary.setText(
            f"{len(result.audits)} audit record(s), {len(warnings)} warning(s), {len(ump_records)} UMP audit record(s). "
            + (warnings[0].message if warnings else "All active numerical gates passed.")
        )
        self._select_analysis("campbell")

    def _set_table(self, title: str, headers: list[str], rows: list[list[object]]) -> None:
        self.table_header.setText(title)
        self.table.clear()
        self.table.setRowCount(len(rows))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                self.table.setItem(r, c, item(value))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _populate_empty(self) -> None:
        self._set_table("Result Table", ["Status"], [["Run the real ROSS pipeline to populate results"]])

    def _select_analysis(self, key: str) -> None:
        self._selected_analysis = key
        for name, button in self.analysis_buttons.items():
            active = name == key
            button.setChecked(active)
            button.setObjectName("primaryButton" if active else "outlineButton")
            button.style().unpolish(button)
            button.style().polish(button)
        if self.result is None:
            self._populate_empty()
            return

        result = self.result
        if key == "modal":
            rows = [
                [m.mode, f"{m.wn_hz:.3f}", f"{m.wd_hz:.3f}", f"{100*m.damping_ratio:.4f}", f"{m.log_dec:.5f}", m.whirl]
                for m in result.modal_modes
            ]
            self._set_table("Modal @ rated speed", ["Mode", "Wn (Hz)", "Wd (Hz)", "Damping (%)", "Log Dec", "Whirl"], rows)
            self.chart_header.setText("Campbell context — rated modal modes highlighted by the table")
        elif key == "critical":
            rows = [
                [c.mode, f"{c.speed_rpm:.2f}", f"{c.frequency_hz:.3f}", f"{100*c.damping_ratio:.4f}", c.whirl, c.method]
                for c in result.critical_speeds
            ]
            if not rows:
                rows = [["—", "No 1X crossing inside qualified K/C envelope", "—", "—", "—", "—"]]
            self._set_table("Critical Speeds", ["Mode", "Speed (rpm)", "Freq (Hz)", "Damping (%)", "Whirl", "Method"], rows)
            self.chart_header.setText("Campbell Diagram — 1X critical crossings")
        elif key == "campbell":
            speed = np.asarray(result.campbell.speed_range, dtype=float) * 60.0 / (2.0 * pi)
            wd = np.asarray(result.campbell.wd, dtype=float) / (2.0 * pi)
            rated = self.project.speed_rpm
            idx = int(np.argmin(np.abs(speed - rated)))
            rows = [[mode + 1, f"{speed[idx]:.1f}", f"{wd[idx, mode]:.3f}"] for mode in range(wd.shape[1])]
            self._set_table("Campbell branches near rated speed", ["Branch", "Speed (rpm)", "Wd (Hz)"], rows)
            self.chart_header.setText("Campbell Diagram — real ROSS result")
        elif key == "ump":
            assembly = result.ump_assembly
            if assembly is None or not assembly.active:
                rows = [["—", "No active UMP", "—", "—", "—", "—"]]
            else:
                rows = [
                    [
                        span.name,
                        f"{span.start_mm:g}",
                        f"{span.end_mm:g}",
                        f"{span.stiffness_per_length_n_m2:.9g}",
                        f"{span.integrated_stiffness_n_m:.9g}",
                        ", ".join(str(index) for index in span.shaft_element_indices),
                    ]
                    for span in assembly.spans
                ]
            self._set_table(
                "UMP — electromagnetic negative stiffness",
                ["Span", "Start (mm)", "End (mm)", "k' (N/m²)", "Integrated k (N/m)", "Shaft elements"],
                rows,
            )
            self.chart_header.setText("UMP active in Modal / Campbell / Harmonic Response: K_eff = K - K_UMP")
        elif key == "unbalance":
            rows = [
                [
                    p.name,
                    p.node,
                    f"{p.position_mm:g}",
                    p.coordinate,
                    f"{p.orientation_deg:g}",
                    f"{p.peak_amplitude_um:.6g}",
                    f"{p.peak_speed_rpm:.1f}",
                    f"{p.rated_amplitude_um:.6g}",
                    f"{p.rated_phase_deg:.2f}",
                ]
                for p in result.probe_responses
            ]
            self._set_table(
                "Unbalance Response / Probes",
                ["Probe", "Node", "x (mm)", "Coord", "Angle", "Peak (µm)", "Peak rpm", "Rated (µm)", "Rated phase"],
                rows,
            )
            self.chart_header.setText("Harmonic response uses the same qualified K/C envelope and active UMP stiffness")
        elif key == "static":
            deformation = np.asarray(result.static.deformation, dtype=float)
            bearing_forces = getattr(result.static, "bearing_forces", {})
            rows = [["Max |deflection|", f"{np.max(np.abs(deformation))*1e6:.6g}", "µm"]]
            for name, force in bearing_forces.items():
                rows.append([f"Bearing reaction · {name}", f"{float(force):.6g}", "N"])
            if result.ump_assembly is not None and result.ump_assembly.active:
                rows.append(["UMP in gravity static", "Excluded by energized-dynamic policy", "—"])
            self._set_table("Static / gravity", ["Quantity", "Value", "Unit"], rows)
            self.chart_header.setText("Campbell context — static results are listed in the table")

    def _settings_card(self) -> QWidget:
        card = SectionCard("Analysis Settings")
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(10)
        grid.addWidget(QLabel("Requested Speed Range"), 0, 0, 1, 3)
        start = QSpinBox()
        start.setRange(0, 200000)
        start.setValue(self.project.speed_min_rpm)
        start.setReadOnly(True)
        end = QSpinBox()
        end.setRange(0, 200000)
        end.setValue(self.project.speed_max_rpm)
        end.setReadOnly(True)
        grid.addWidget(start, 1, 0)
        grid.addWidget(QLabel("–"), 1, 1, Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(end, 1, 2)
        grid.addWidget(QLabel("Result Units"), 2, 0)
        units = QComboBox()
        units.addItems(["Hz / rpm / µm", "SI base"])
        grid.addWidget(units, 2, 1, 1, 2)
        grid.addWidget(QLabel("Mode Display"), 3, 0)
        modes = QComboBox()
        modes.addItems(["All Modes", "Forward Whirl", "Backward Whirl"])
        grid.addWidget(modes, 3, 1, 1, 2)
        checks = [("Show Synchronous Line (1X)", True), ("Show Critical Speeds", True), ("Show Grid", True)]
        for r, (text, checked) in enumerate(checks, 4):
            check = QCheckBox(text)
            check.setChecked(checked)
            check.setEnabled(False)
            grid.addWidget(check, r, 0, 1, 3)
        card.root.addLayout(grid)
        return card

    def _export_card(self) -> QWidget:
        card = SectionCard("Export & Report")
        for text, icon in [("Export PNG", "image"), ("Export CSV", "table"), ("Generate Report", "report")]:
            button = QPushButton(text)
            button.setObjectName("softButton")
            button.setIcon(engineering_icon(icon, 20))
            card.root.addWidget(button)
        return card
