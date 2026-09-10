from __future__ import annotations

from PySide6.QtCore import QSize, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
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
from ..plotly_native_view import NativeRossFigureView
from ..ross_native_plots import NativeRossPlotUnavailable, RossBearingNativePlotService
from ..theme import COLORS
from .bearing_studio import BearingStudioPage as _BearingStudioPage


class BearingStudioPage(_BearingStudioPage):
    """Bearing Studio with a dedicated vertical engineering rail.

    The scientific services and transactional Calculate/Apply flow remain those of
    the qualified 0.13/0.14 implementation.  This class only reorganizes ownership
    and presentation: target station/node, bearing model and BePerf-parity analysis
    contract live in one persistent vertical rail, while engineering inputs/results
    stay in the central workspace.
    """

    BEPERF_FLUID_CLASSES = {"PlainJournal", "TiltingPad"}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.native_plot_service = RossBearingNativePlotService()
        self._native_figures: dict[str, object] = {}
        self._build_vertical_bearing_rail()
        self._build_native_plot_tab()
        self._sync_target_node()
        self._sync_parity_contract()
        for button in self.type_buttons.values():
            button.clicked.connect(lambda checked=False: QTimer.singleShot(0, self._sync_parity_contract))
        self.bearing_selector.currentIndexChanged.connect(lambda _row: self._sync_target_node())

    def _build_vertical_bearing_rail(self) -> None:
        rail = QFrame(self)
        rail.setObjectName("bearingStudioRail")
        rail.setFixedWidth(260)
        rail.setStyleSheet(
            f"QFrame#bearingStudioRail{{background:#f7fbff;border:1px solid {COLORS.border};border-radius:6px;}}"
        )
        outer = QVBoxLayout(rail)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        title = QLabel("Bearing Studio")
        title.setObjectName("cardHeader")
        outer.addWidget(title)
        subtitle = QLabel("Target → model → inputs → calculate → apply")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        target_title = QLabel("Apply calculated bearing at")
        target_title.setObjectName("subHeader")
        outer.addWidget(target_title)
        self.bearing_selector.setParent(rail)
        self.bearing_selector.setMinimumWidth(220)
        self.bearing_selector.setToolTip(
            "Qualified physical bearing station. The selected axial position is resolved to an exact ROSS node; no nearest-node snapping is used."
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
        model_scroll.setHorizontalScrollBarPolicy(model_scroll.horizontalScrollBarPolicy().ScrollBarAlwaysOff)
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

        parity_title = QLabel("BePerf analysis contract")
        parity_title.setObjectName("subHeader")
        outer.addWidget(parity_title)
        self.analysis_formulation = QComboBox()
        self.analysis_formulation.setObjectName("bearingAnalysisFormulation")
        for mode in BearingAnalysisFormulation:
            self.analysis_formulation.addItem(mode.value, mode.value)
        self.analysis_formulation.setToolTip(
            "BePerf-equivalence surface. Options without a qualified ROSS 2.3.0 mapping remain visible but fail closed on Calculate."
        )
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

        layout = self.layout()
        if layout is not None:
            layout.insertWidget(0, rail)
        self.bearing_rail = rail

    def _build_native_plot_tab(self) -> None:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 8, 0, 0)
        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("ROSS native plot"))
        self.native_plot_selector = QComboBox()
        self.native_plot_selector.setObjectName("bearingNativePlotSelector")
        self.native_plot_selector.currentIndexChanged.connect(self._show_selected_native_plot)
        selector_row.addWidget(self.native_plot_selector, 1)
        root.addLayout(selector_row)
        self.native_plot_view = NativeRossFigureView()
        self.native_plot_view.set_unavailable(
            "Calculate a qualified ROSS bearing to expose its native Plotly post-processing."
        )
        root.addWidget(self.native_plot_view, 1)
        self.native_plot_tab_index = self.tabs.addTab(page, "ROSS Native")

    def _current_ross_class(self) -> str:
        for key, button in self.type_buttons.items():
            if button.isChecked():
                return self.type_metadata[key][1]
        return self.bearing.ross_class

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
            f"{station.name}  ·  x={station.position_mm:g} mm  ·  exact ROSS node {node}"
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
                "BePerf dimensional/non-dimensional contract applies to hydrodynamic journal-bearing models; this ROSS class follows its own qualified adapter."
            )
            return

        # Preserve the qualified current physics as the default selection.
        if self.analysis_formulation.currentIndex() < 0:
            self.analysis_formulation.setCurrentText(BearingAnalysisFormulation.DIMENSIONAL_HEAT_BALANCE.value)
        if self.analysis_formulation.currentText() == BearingAnalysisFormulation.DIMENSIONAL_CONSTANT_VISCOSITY.value:
            # Do not silently change a current THD model merely because the first
            # enum item happens to be Constant Viscosity.
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
        status = "Executable" if a.status is CapabilityStatus.ROSS_NATIVE and c.status is CapabilityStatus.ROSS_NATIVE else "Prepared · blocked until qualified"
        self.parity_status.setText(f"{status}\nAnalysis: {a.status.value}\nCoordinates: {c.status.value}")

    def input_values(self) -> dict:
        ross_class = self._current_ross_class()
        values = super().input_values()
        if ross_class in self.BEPERF_FLUID_CLASSES:
            analysis = self._selected_analysis()
            coordinates = self._selected_coordinates()
            require_executable_contract(ross_class, analysis, coordinates)
            # Persist the interpretation contract next to the solver input without
            # changing the ROSS constructor arguments. Scientific services may use
            # these keys only after a dedicated adapter explicitly consumes them.
            values["studio_analysis_formulation"] = analysis.value
            values["studio_coordinate_convention"] = coordinates.value
        return values

    def _load_native_figures(self, native_element) -> None:
        self._native_figures = {}
        self.native_plot_selector.blockSignals(True)
        self.native_plot_selector.clear()
        try:
            figures = self.native_plot_service.figures(native_element, freq_index=0)
            self._native_figures = dict(figures.figures)
        except NativeRossPlotUnavailable as exc:
            self.native_plot_view.set_unavailable(str(exc))
            self.native_plot_selector.blockSignals(False)
            return
        for name in self._native_figures:
            self.native_plot_selector.addItem(name)
        self.native_plot_selector.blockSignals(False)
        if self._native_figures:
            self.native_plot_selector.setCurrentIndex(0)
            self._show_selected_native_plot(0)
        else:
            self.native_plot_view.set_unavailable(
                "No applicable native ROSS 2.3.0 figure is available for this bearing result."
            )

    def _show_selected_native_plot(self, row: int) -> None:
        if row < 0:
            return
        name = self.native_plot_selector.itemText(row)
        figure = self._native_figures.get(name)
        if figure is not None:
            self.native_plot_view.set_figure(figure, tooltip=f"ROSS 2.3.0 native bearing plot · {name}")

    def set_thd_result(self, result) -> None:
        super().set_thd_result(result)
        self._load_native_figures(getattr(result, "native_element", None))

    def set_thrust_result(self, result) -> None:
        super().set_thrust_result(result)
        self._load_native_figures(getattr(result, "native_element", None))


__all__ = ["BearingStudioPage"]
