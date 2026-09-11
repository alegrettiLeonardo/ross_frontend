from __future__ import annotations

from math import pi

import numpy as np
from PySide6.QtCore import QSize, QTimer, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ..bearing_parity import (
    BearingAnalysisFormulation,
    BearingCoordinateConvention,
    CapabilityStatus,
    contract_for,
    require_executable_contract,
)
from ..domain import BearingGroup
from ..plotly_native_view import NativeRossFigureView
from ..ross_native_plots import NativeFigureSet, NativeRossPlotUnavailable, RossBearingNativePlotService
from ..theme import COLORS
from ..widgets import Card, configure_table, item
from .bearing_studio import BearingStudioPage as _BearingStudioPage


class BearingStudioPage(_BearingStudioPage):
    """RotorDin-style Bearing Studio backed by qualified ROSS bearing services.

    User-facing model choices follow the engineering workflow requested for ROSS
    Studio: General (Ball, Roller, Cylindrical), THD (Plain Journal, Tilting Pad,
    Thrust Pad, SFD) and AMB (visible but blocked). Direct ``BearingElement`` K/C
    remains a persistence/application class for imported models, not a calculation
    model tile.

    Output ownership is deliberately split in two:

    * K/C: available for every calculated bearing. The table is always shown; a
      curve is shown only for THD bearings and is the native ROSS ``plot()`` figure.
    * Dimensional: THD-only. Pressure, temperature, bearing geometry,
      convergence and textual summaries are delegated to the retained ROSS 2.3.0
      BearingResults object. No Studio-side pressure/temperature re-plotting occurs.
    """

    TYPE_DEFINITIONS = (
        ("ball", "Ball Bearing", "ball_bearing", "BallBearingElement", BearingGroup.GENERAL),
        ("roller", "Roller Bearing", "roller_bearing", "RollerBearingElement", BearingGroup.GENERAL),
        ("cyl", "Cylindrical", "cylindrical_bearing", "CylindricalBearing", BearingGroup.GENERAL),
        ("plain", "Plain Journal", "plain_journal", "PlainJournal", BearingGroup.THD),
        ("tilting", "Tilting Pad", "tilting_pad", "TiltingPad", BearingGroup.THD),
        ("thrust", "Thrust Pad", "thrust_pad", "ThrustPad", BearingGroup.THD),
        ("sfd", "Squeeze Film Damper", "sfd", "SqueezeFilmDamper", BearingGroup.THD),
        ("amb", "Active Magnetic Bearing", "amb", "MagneticBearingElement", BearingGroup.AMB),
    )

    THD_CLASSES = {"PlainJournal", "TiltingPad", "ThrustPad", "SqueezeFilmDamper"}
    BEPERF_FLUID_CLASSES = {"PlainJournal", "TiltingPad"}

    def __init__(self, *args, **kwargs) -> None:
        self.native_plot_service = RossBearingNativePlotService()
        self._native_element = None
        self._dimensional_outputs = NativeFigureSet("", {})
        super().__init__(*args, **kwargs)

        self._simplify_center_header()
        self._build_vertical_bearing_rail()
        self._rebuild_output_tabs()
        self._sync_target_node()
        self._sync_parity_contract()
        self._sync_output_contract()

        for button in self.type_buttons.values():
            button.clicked.connect(lambda checked=False: QTimer.singleShot(0, self._after_model_choice))
        self.bearing_selector.currentIndexChanged.connect(lambda _row: self._sync_target_node())

    # ------------------------------------------------------------------
    # Layout / navigation
    # ------------------------------------------------------------------
    def _simplify_center_header(self) -> None:
        holder = self.workspace_scroll.widget()
        layout = holder.layout() if holder is not None else None
        if layout is not None and layout.count():
            # Station/model navigation is moved to the dedicated vertical rail.
            old_navigation_card = layout.itemAt(0).widget()
            if old_navigation_card is not None:
                old_navigation_card.hide()

    def _build_vertical_bearing_rail(self) -> None:
        rail = QFrame(self)
        rail.setObjectName("bearingStudioRail")
        rail.setFixedWidth(272)
        rail.setStyleSheet(
            f"QFrame#bearingStudioRail{{background:#f7fbff;border:1px solid {COLORS.border};border-radius:6px;}}"
        )
        outer = QVBoxLayout(rail)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        title = QLabel("Bearing Studio")
        title.setObjectName("cardHeader")
        outer.addWidget(title)
        subtitle = QLabel("Station → bearing model → calculate → output → apply")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        target_title = QLabel("Apply calculated bearing at")
        target_title.setObjectName("subHeader")
        outer.addWidget(target_title)
        self.bearing_selector.setParent(rail)
        self.bearing_selector.setMinimumWidth(230)
        self.bearing_selector.setToolTip(
            "Qualified physical bearing station resolved to an exact ROSS node; nearest-node snapping is not used."
        )
        outer.addWidget(self.bearing_selector)
        self.target_node_label = QLabel()
        self.target_node_label.setObjectName("bearingTargetNode")
        self.target_node_label.setWordWrap(True)
        outer.addWidget(self.target_node_label)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        outer.addWidget(line)
        models_title = QLabel("Bearing model")
        models_title.setObjectName("subHeader")
        outer.addWidget(models_title)

        model_scroll = QScrollArea()
        model_scroll.setWidgetResizable(True)
        model_scroll.setFrameShape(QFrame.Shape.NoFrame)
        model_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        holder = QWidget()
        models = QVBoxLayout(holder)
        models.setContentsMargins(0, 0, 0, 0)
        models.setSpacing(5)
        previous_group = None
        for key, _text, _icon, _ross_class, group in self.TYPE_DEFINITIONS:
            if group != previous_group:
                group_label = QLabel(group.value)
                group_label.setObjectName("navSection")
                models.addWidget(group_label)
                previous_group = group
            button = self.type_buttons[key]
            button.setParent(holder)
            button.setMinimumHeight(42)
            button.setIconSize(QSize(28, 28))
            button.setStyleSheet("text-align:left;padding:6px 8px;")
            models.addWidget(button)
        models.addStretch(1)
        model_scroll.setWidget(holder)
        outer.addWidget(model_scroll, 1)

        # BePerf-equivalence controls remain available only where a qualified
        # PlainJournal/TiltingPad mapping can be stated explicitly.
        parity_title = QLabel("Hydrodynamic formulation")
        parity_title.setObjectName("subHeader")
        outer.addWidget(parity_title)
        self.analysis_formulation = QComboBox()
        self.analysis_formulation.setObjectName("bearingAnalysisFormulation")
        for mode in BearingAnalysisFormulation:
            self.analysis_formulation.addItem(mode.value, mode.value)
        outer.addWidget(self.analysis_formulation)
        self.coordinate_convention = QComboBox()
        self.coordinate_convention.setObjectName("bearingCoordinateConvention")
        for convention in BearingCoordinateConvention:
            self.coordinate_convention.addItem(convention.value, convention.value)
        outer.addWidget(self.coordinate_convention)
        self.parity_status = QLabel()
        self.parity_status.setObjectName("muted")
        self.parity_status.setWordWrap(True)
        outer.addWidget(self.parity_status)
        self.analysis_formulation.currentIndexChanged.connect(lambda _row: self._sync_parity_contract())
        self.coordinate_convention.currentIndexChanged.connect(lambda _row: self._sync_parity_contract())

        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        outer.addWidget(line2)
        output_title = QLabel("Output")
        output_title.setObjectName("subHeader")
        outer.addWidget(output_title)
        self.output_kc_button = QPushButton("K/C")
        self.output_kc_button.setObjectName("softButton")
        self.output_kc_button.setEnabled(False)
        self.output_kc_button.clicked.connect(lambda: self._open_output(0))
        outer.addWidget(self.output_kc_button)
        self.output_dimensional_button = QPushButton("Dimensional · THD")
        self.output_dimensional_button.setObjectName("softButton")
        self.output_dimensional_button.setEnabled(False)
        self.output_dimensional_button.clicked.connect(self._open_dimensional_output)
        outer.addWidget(self.output_dimensional_button)

        layout = self.layout()
        if layout is not None:
            layout.insertWidget(0, rail)
        self.bearing_rail = rail

    def _rebuild_output_tabs(self) -> None:
        # Keep the qualified K/C tab. Legacy Studio field tabs remain as internal
        # compatibility widgets but are removed from the visible navigation because
        # dimensional output is now rendered directly from ROSS BearingResults.
        while self.tabs.count() > 1:
            self.tabs.removeTab(1)
        self.tabs.setTabText(0, "K/C")

        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 8, 0, 0)
        root.setSpacing(8)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Solved speed"))
        self.native_frequency_selector = QComboBox()
        self.native_frequency_selector.setObjectName("bearingNativeFrequencySelector")
        self.native_frequency_selector.currentIndexChanged.connect(self._frequency_changed)
        controls.addWidget(self.native_frequency_selector)
        controls.addWidget(QLabel("ROSS dimensional plot"))
        self.native_plot_selector = QComboBox()
        self.native_plot_selector.setObjectName("bearingNativePlotSelector")
        self.native_plot_selector.currentIndexChanged.connect(self._show_selected_native_plot)
        controls.addWidget(self.native_plot_selector, 1)
        root.addLayout(controls)

        self.native_plot_view = NativeRossFigureView()
        self.native_plot_view.setMinimumHeight(430)
        self.native_plot_view.set_unavailable(
            "Calculate a THD bearing to expose native ROSS dimensional post-processing."
        )
        root.addWidget(self.native_plot_view, 1)

        text_row = QHBoxLayout()
        text_row.addWidget(QLabel("ROSS report"))
        self.native_text_selector = QComboBox()
        self.native_text_selector.currentIndexChanged.connect(self._show_selected_native_text)
        text_row.addWidget(self.native_text_selector, 1)
        root.addLayout(text_row)
        self.native_text_output = QPlainTextEdit()
        self.native_text_output.setObjectName("bearingNativeTextOutput")
        self.native_text_output.setReadOnly(True)
        self.native_text_output.setMaximumHeight(230)
        self.native_text_output.setPlaceholderText(
            "ROSS show_results(), show_coefficients_comparison(), execution time and convergence output appears here when available."
        )
        root.addWidget(self.native_text_output)

        self.dimensional_tab_index = self.tabs.addTab(page, "Dimensional · THD")
        self.tabs.setTabEnabled(self.dimensional_tab_index, False)
        if hasattr(self.tabs, "setTabVisible"):
            self.tabs.setTabVisible(self.dimensional_tab_index, False)

        self.results_button.setText("View Output")

    # ------------------------------------------------------------------
    # K/C output
    # ------------------------------------------------------------------
    def _kc_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)
        headers = [
            "RPM", "Kxx\n(N/m)", "Kxy\n(N/m)", "Kyx\n(N/m)", "Kyy\n(N/m)",
            "Cxx\n(N·s/m)", "Cxy\n(N·s/m)", "Cyx\n(N·s/m)", "Cyy\n(N·s/m)",
        ]
        table = QTableWidget(len(self.bearing.coefficients), len(headers))
        table.setHorizontalHeaderLabels(headers)
        configure_table(table, row_height=30)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, coeff in enumerate(self.bearing.coefficients):
            values = [
                f"{coeff.rpm:g}", f"{coeff.kxx:.2e}", f"{coeff.kxy:.2e}", f"{coeff.kyx:.2e}",
                f"{coeff.kyy:.2e}", f"{coeff.cxx:.2e}", f"{coeff.cxy:.2e}", f"{coeff.cyx:.2e}", f"{coeff.cyy:.2e}",
            ]
            for col, value in enumerate(values):
                table.setItem(row, col, item(value))
        self.kc_table = table
        table.resizeColumnsToContents()
        layout.addWidget(table, 3)

        chart_card = Card()
        self.chart_card = chart_card
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(10, 8, 10, 8)
        title = QLabel("K/C curves · native ROSS THD")
        title.setObjectName("subHeader")
        chart_layout.addWidget(title)
        self.kc_native_view = NativeRossFigureView()
        self.kc_native_view.set_unavailable(
            "K/C curves are shown only for calculated THD bearings. General bearings expose their calculated K/C values in the table."
        )
        chart_layout.addWidget(self.kc_native_view, 1)
        layout.addWidget(chart_card, 2)
        return page

    def set_bearing_preview(self, bearing) -> None:
        """Update K/C table without generating application-side K/C curves."""
        self.bearing = bearing
        headers = [
            "RPM", "Kxx\n(N/m)", "Kxy\n(N/m)", "Kyx\n(N/m)", "Kyy\n(N/m)",
            "Cxx\n(N·s/m)", "Cxy\n(N·s/m)", "Cyx\n(N·s/m)", "Cyy\n(N·s/m)",
        ]
        self.kc_table.clear()
        self.kc_table.setRowCount(len(bearing.coefficients))
        self.kc_table.setColumnCount(len(headers))
        self.kc_table.setHorizontalHeaderLabels(headers)
        configure_table(self.kc_table, row_height=30)
        self.kc_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, coeff in enumerate(bearing.coefficients):
            values = [
                f"{coeff.rpm:g}", f"{coeff.kxx:.2e}", f"{coeff.kxy:.2e}", f"{coeff.kyx:.2e}",
                f"{coeff.kyy:.2e}", f"{coeff.cxx:.2e}", f"{coeff.cxy:.2e}", f"{coeff.cyx:.2e}", f"{coeff.cyy:.2e}",
            ]
            for col, value in enumerate(values):
                self.kc_table.setItem(row, col, item(value))
        if bearing.coefficients and self.project.engineering is not None:
            rated = self.project.engineering.operating_cases[0].rated_speed_rpm
            self.nominal_index = min(
                range(len(bearing.coefficients)), key=lambda i: abs(bearing.coefficients[i].rpm - rated)
            )
            self.kc_table.selectRow(self.nominal_index)
        self.kc_table.resizeColumnsToContents()
        self.kc_native_view.set_unavailable(
            "K/C curves are shown only for calculated THD bearings. General bearings expose their calculated K/C values in the table."
        )
        self.set_results_available(True)

    # ------------------------------------------------------------------
    # Native ROSS THD output
    # ------------------------------------------------------------------
    def _load_thd_outputs(self, native_element) -> None:
        self._native_element = native_element
        self.native_frequency_selector.blockSignals(True)
        self.native_frequency_selector.clear()
        frequency = np.atleast_1d(getattr(native_element, "frequency", [])) if native_element is not None else np.array([])
        for index, omega in enumerate(frequency):
            rpm = float(omega) * 30.0 / pi
            self.native_frequency_selector.addItem(f"{rpm:,.1f} rpm", index)
        self.native_frequency_selector.blockSignals(False)
        if self.native_frequency_selector.count() == 0:
            self.native_frequency_selector.addItem("Solved point", 0)

        try:
            kc_figure = self.native_plot_service.kc_figure(native_element)
        except NativeRossPlotUnavailable as exc:
            self.kc_native_view.set_unavailable(str(exc))
        else:
            if kc_figure is None:
                self.kc_native_view.set_unavailable("ROSS 2.3.0 did not return a native K/C curve for this THD model.")
            else:
                self.kc_native_view.set_figure(kc_figure, tooltip="ROSS 2.3.0 native THD K/C plot")

        self._reload_dimensional_outputs(0)
        self._sync_output_contract(result_available=True)

    def _reload_dimensional_outputs(self, freq_index: int) -> None:
        if self._native_element is None:
            return
        try:
            output = self.native_plot_service.dimensional_outputs(
                self._native_element, freq_index=max(0, int(freq_index))
            )
        except NativeRossPlotUnavailable as exc:
            self._dimensional_outputs = NativeFigureSet(type(self._native_element).__name__, {})
            self.native_plot_view.set_unavailable(str(exc))
            self.native_text_output.setPlainText(str(exc))
            return

        self._dimensional_outputs = output
        self.native_plot_selector.blockSignals(True)
        self.native_plot_selector.clear()
        for name in output.figures:
            self.native_plot_selector.addItem(name)
        self.native_plot_selector.blockSignals(False)
        if self.native_plot_selector.count():
            self.native_plot_selector.setCurrentIndex(0)
            self._show_selected_native_plot(0)
        else:
            diagnostics = "\n".join(output.diagnostics)
            self.native_plot_view.set_unavailable(
                "ROSS exposes no dimensional Plotly field for this model/speed."
                + (f"\n{diagnostics}" if diagnostics else "")
            )

        self.native_text_selector.blockSignals(True)
        self.native_text_selector.clear()
        for name in output.text_outputs:
            self.native_text_selector.addItem(name)
        self.native_text_selector.blockSignals(False)
        if self.native_text_selector.count():
            self.native_text_selector.setCurrentIndex(0)
            self._show_selected_native_text(0)
        else:
            self.native_text_output.setPlainText("\n".join(output.diagnostics))

    def _frequency_changed(self, row: int) -> None:
        if row >= 0:
            self._reload_dimensional_outputs(int(self.native_frequency_selector.itemData(row) or 0))

    def _show_selected_native_plot(self, row: int) -> None:
        if row < 0:
            return
        name = self.native_plot_selector.itemText(row)
        figure = self._dimensional_outputs.figures.get(name)
        if figure is not None:
            self.native_plot_view.set_figure(figure, tooltip=f"ROSS 2.3.0 native THD output · {name}")

    def _show_selected_native_text(self, row: int) -> None:
        if row < 0:
            return
        name = self.native_text_selector.itemText(row)
        self.native_text_output.setPlainText(self._dimensional_outputs.text_outputs.get(name, ""))

    def set_thd_result(self, result) -> None:
        super().set_thd_result(result)
        self._load_thd_outputs(getattr(result, "native_element", None))

    def set_thrust_result(self, result) -> None:
        super().set_thrust_result(result)
        self.chart_card.setVisible(True)
        self._load_thd_outputs(getattr(result, "native_element", None))

    # ------------------------------------------------------------------
    # State synchronization
    # ------------------------------------------------------------------
    def _after_model_choice(self) -> None:
        self._sync_parity_contract()
        self._sync_output_contract()

    def _current_ross_class(self) -> str:
        for key, button in self.type_buttons.items():
            if button.isChecked():
                return self.type_metadata[key][1]
        return self.bearing.ross_class

    def _select_type(self, key: str, *, announce: bool = True) -> None:
        super()._select_type(key, announce=announce)
        if hasattr(self, "output_kc_button"):
            self._sync_output_contract()

    def set_results_available(self, available: bool, *, show: bool = False) -> None:
        super().set_results_available(available, show=show)
        if hasattr(self, "output_kc_button"):
            self._sync_output_contract(result_available=bool(available))

    def _sync_target_node(self) -> None:
        raw_index = self.bearing_selector.currentData()
        if raw_index is None or self.project.engineering is None:
            self.target_node_label.setText("No qualified bearing station")
            return
        try:
            station = self.workspace.station(self.project.engineering, int(raw_index))
        except Exception as exc:
            self.target_node_label.setText(f"Target unresolved: {exc}")
            return
        node = "unresolved" if station.ross_node is None else f"n{station.ross_node}"
        self.target_node_label.setText(
            f"{station.name} · x={station.position_mm:g} mm · exact ROSS node {node}"
        )

    def _selected_analysis(self) -> BearingAnalysisFormulation:
        return BearingAnalysisFormulation(str(self.analysis_formulation.currentData()))

    def _selected_coordinates(self) -> BearingCoordinateConvention:
        return BearingCoordinateConvention(str(self.coordinate_convention.currentData()))

    def _sync_parity_contract(self) -> None:
        ross_class = self._current_ross_class()
        fluid = ross_class in self.BEPERF_FLUID_CLASSES
        self.analysis_formulation.setEnabled(fluid)
        self.coordinate_convention.setEnabled(fluid)
        if not fluid:
            self.parity_status.setText(
                "BePerf dimensional/non-dimensional formulation controls apply to hydrodynamic journal models; this class uses its qualified ROSS adapter."
            )
            return
        if self.analysis_formulation.currentIndex() < 0:
            self.analysis_formulation.setCurrentText(BearingAnalysisFormulation.DIMENSIONAL_HEAT_BALANCE.value)
        if self.analysis_formulation.currentText() == BearingAnalysisFormulation.DIMENSIONAL_CONSTANT_VISCOSITY.value:
            self.analysis_formulation.blockSignals(True)
            self.analysis_formulation.setCurrentText(BearingAnalysisFormulation.DIMENSIONAL_HEAT_BALANCE.value)
            self.analysis_formulation.blockSignals(False)
        if self.coordinate_convention.currentIndex() < 0:
            self.coordinate_convention.setCurrentText(BearingCoordinateConvention.STANDARD_XY.value)

        contract = contract_for(ross_class)
        analysis = self._selected_analysis()
        coords = self._selected_coordinates()
        a = contract.analyses[analysis]
        c = contract.coordinates[coords]
        status = (
            "Executable"
            if a.status is CapabilityStatus.ROSS_NATIVE and c.status is CapabilityStatus.ROSS_NATIVE
            else "Prepared · blocked until qualified"
        )
        self.parity_status.setText(f"{status}\nAnalysis: {a.status.value}\nCoordinates: {c.status.value}")

    def _sync_output_contract(self, *, result_available: bool | None = None) -> None:
        ross_class = self._current_ross_class()
        thd = ross_class in self.THD_CLASSES
        if result_available is None:
            result_available = bool(self.results_button.isEnabled())
        self.output_kc_button.setEnabled(bool(result_available))
        self.output_dimensional_button.setEnabled(bool(result_available and thd))
        self.tabs.setTabEnabled(self.dimensional_tab_index, bool(result_available and thd))
        if hasattr(self.tabs, "setTabVisible"):
            self.tabs.setTabVisible(self.dimensional_tab_index, thd)
        if not thd and self.tabs.currentIndex() == self.dimensional_tab_index:
            self.tabs.setCurrentIndex(0)

    def _open_output(self, tab_index: int) -> None:
        if not self.results_button.isEnabled():
            return
        self.set_results_visible(True)
        self.tabs.setCurrentIndex(tab_index)

    def _open_dimensional_output(self) -> None:
        if self.output_dimensional_button.isEnabled():
            self._open_output(self.dimensional_tab_index)

    def input_values(self) -> dict:
        ross_class = self._current_ross_class()
        values = super().input_values()
        if ross_class in self.BEPERF_FLUID_CLASSES:
            analysis = self._selected_analysis()
            coordinates = self._selected_coordinates()
            require_executable_contract(ross_class, analysis, coordinates)
            values["studio_analysis_formulation"] = analysis.value
            values["studio_coordinate_convention"] = coordinates.value
        return values


__all__ = ["BearingStudioPage"]
