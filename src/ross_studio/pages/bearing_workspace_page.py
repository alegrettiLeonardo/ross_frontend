from __future__ import annotations

from math import pi
from typing import Any

import numpy as np
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..bearing_assets import bearing_icon
from ..bearing_input_workspace import BearingInputWorkspace
from ..bearing_parity import (
    BearingAnalysisFormulation,
    BearingCoordinateConvention,
    CapabilityStatus,
    contract_for,
    require_executable_contract,
)
from ..bearing_schema import (
    MODEL_BY_CLASS,
    MODEL_BY_KEY,
    MODEL_SPECS,
    BearingModelSpec,
    BearingUiState,
)
from ..bearing_workspace import BearingStation, BearingStationInventory, BearingWorkspaceService
from ..domain import AdapterStatus, BearingGroup
from ..icons import engineering_icon
from ..models import BearingModel, ProjectModel
from ..plotly_native_view import NativeRossFigureView
from ..ross_native_plots import NativeFigureSet, NativeRossPlotUnavailable, RossBearingNativePlotService
from ..rotor_selection import RotorEntityRef, WORKSPACE_SELECTION
from ..services import BearingCatalogService
from ..widgets import BearingCoefficientChart, Card


class CoefficientTableModel(QAbstractTableModel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.headers: list[str] = []
        self.rows: list[list[Any]] = []
        self.nominal_row = -1

    def set_data(self, headers: list[str], rows: list[list[Any]], nominal_row: int = -1) -> None:
        self.beginResetModel()
        self.headers = list(headers)
        self.rows = list(rows)
        self.nominal_row = int(nominal_row)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.rows):
            return None
        value = self.rows[index.row()][index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            if isinstance(value, float):
                if index.column() == 0:
                    return f"{value:,.0f}"
                return f"{value:.3e}"
            return str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter)
        if role == Qt.ItemDataRole.BackgroundRole and index.row() == self.nominal_row:
            return QBrush(QColor("#e8f4ff"))
        if role == Qt.ItemDataRole.FontRole and index.row() == self.nominal_row:
            font = super().data(index, role)
            return font
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and section < len(self.headers):
            return self.headers[section]
        return str(section + 1)


class BearingModelCard(QPushButton):
    def __init__(self, spec: BearingModelSpec, parent=None) -> None:
        label = spec.public_name + (f"\n{spec.subtitle}" if spec.subtitle else "")
        super().__init__(label, parent)
        self.spec = spec
        self.setObjectName("bearingModelCard")
        self.setCheckable(True)
        self.setIcon(bearing_icon(spec.icon_asset, 62))
        self.setIconSize(self.icon().actualSize(self.sizeHint()).boundedTo(self.sizeHint()))
        self.setMinimumHeight(98)
        self.setMinimumWidth(116)
        self.setToolTip(f"{spec.family.value} · ROSS {spec.ross_class}")
        if not spec.executable:
            self.setProperty("blocked", True)


class BearingFamilyPanel(QFrame):
    def __init__(self, title: str, specs: list[BearingModelSpec], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("bearingFamilyPanel")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 7, 8, 8)
        root.setSpacing(6)
        label = QLabel(title)
        label.setObjectName("bearingFamilyTitle")
        root.addWidget(label)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(7)
        self.cards: list[BearingModelCard] = []
        for spec in specs:
            card = BearingModelCard(spec)
            self.cards.append(card)
            row.addWidget(card, 1)
        root.addLayout(row)


class MetricPanel(QFrame):
    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("bearingMetricPanel")
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 7, 10, 8)
        root.setSpacing(3)
        header = QLabel(title)
        header.setObjectName("bearingInputSectionTitle")
        root.addWidget(header)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(3)
        root.addLayout(self.grid)
        self.value_labels: dict[str, QLabel] = {}

    def set_metrics(self, rows: list[tuple[str, str]]) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.value_labels.clear()
        for i, (name, value) in enumerate(rows):
            key = QLabel(name)
            key.setObjectName("muted")
            val = QLabel(value)
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.grid.addWidget(key, i, 0)
            self.grid.addWidget(val, i, 1)
            self.value_labels[name] = val
        self.grid.setColumnStretch(0, 1)


class AdditionalResultsPanel(QFrame):
    result_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("additionalResultsPanel")
        self.setMinimumWidth(220)
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(6)
        title = QLabel("Additional THD Results")
        title.setObjectName("bearingInputSectionTitle")
        root.addWidget(title)
        self.grid = QGridLayout()
        self.grid.setSpacing(7)
        root.addLayout(self.grid)
        root.addStretch(1)
        self.tiles: dict[str, QPushButton] = {}

    def set_results(self, names: tuple[str, ...], available: set[str]) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.tiles.clear()
        for i, name in enumerate(names):
            button = QPushButton(name)
            button.setObjectName("bearingResultTile")
            button.setMinimumHeight(72)
            button.setEnabled(name in available)
            button.setToolTip("Open native ROSS result" if button.isEnabled() else "Not returned by the current ROSS result")
            button.clicked.connect(lambda checked=False, n=name: self.result_requested.emit(n))
            self.tiles[name] = button
            self.grid.addWidget(button, i // 2, i % 2)


class BearingStudioPage(QWidget):
    """ROSS Studio 0.16 Bearing Studio golden-layout workspace.

    The page owns presentation and transaction state only. Bearing physics remains in
    the dispatcher/services and in ROSS itself. Calculate creates a preview/cache;
    Apply is the only operation that can mutate the rotor model.
    """

    status_message = Signal(str)
    bearing_selected = Signal(int)

    TYPE_DEFINITIONS = tuple(
        (spec.key, spec.public_name, spec.icon_asset, spec.ross_class, spec.family)
        for spec in MODEL_SPECS
    )
    THD_CLASSES = {"PlainJournal", "TiltingPad", "ThrustPad", "SqueezeFilmDamper"}
    BEPERF_FLUID_CLASSES = {"PlainJournal", "TiltingPad"}

    def __init__(
        self,
        project: ProjectModel,
        bearing: BearingModel,
        parent: QWidget | None = None,
        catalog: BearingCatalogService | None = None,
        bearing_index: int = 0,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.bearing = bearing
        self.catalog = catalog or BearingCatalogService()
        self.bearing_index = int(bearing_index)
        self.workspace = BearingWorkspaceService()
        self.selection = WORKSPACE_SELECTION
        self.native_plot_service = RossBearingNativePlotService()
        self._native_element = None
        self._dimensional_outputs = NativeFigureSet("", {})
        self._result_object = None
        self._result_available = False
        self._input_dirty = False
        self.ui_state = BearingUiState.NO_STATION
        self.nominal_index = -1

        engineering = self.project.engineering
        if engineering is None:
            raise RuntimeError("Bearing Studio requires a loaded engineering domain.")
        self.stations: tuple[BearingStation, ...] = self.workspace.stations(engineering)
        self.station = next((row for row in self.stations if row.index == self.bearing_index), None)
        self.inventory: BearingStationInventory | None = (
            self.workspace.inventory(engineering, self.bearing_index) if self.station is not None else None
        )

        try:
            self.current_group = BearingGroup(bearing.group)
        except ValueError:
            self.current_group = BearingGroup.GENERAL

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.workspace_scroll = QScrollArea()
        self.workspace_scroll.setObjectName("bearingWorkspaceScroll")
        self.workspace_scroll.setWidgetResizable(True)
        self.workspace_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.workspace_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self.workspace_scroll, 1)

        content = QWidget()
        content.setObjectName("bearingWorkspaceContent")
        root = QVBoxLayout(content)
        root.setContentsMargins(12, 8, 12, 10)
        root.setSpacing(8)
        self.workspace_scroll.setWidget(content)

        self._build_header(root)
        self._build_model_selector(root)
        self._build_input_and_operating_area(root)
        self._build_action_bar(root)
        self._build_results(root)
        root.addStretch(1)

        # Compatibility-only controls used by existing qualification APIs. They are
        # intentionally hidden because the golden visual has no secondary rail.
        self.group_selector = QComboBox(self)
        for group in (BearingGroup.GENERAL, BearingGroup.THD, BearingGroup.AMB):
            self.group_selector.addItem(group.value, group.value)
        self.group_selector.hide()
        self.group_selector.currentTextChanged.connect(self.set_group)
        self.group_badge = QLabel(self); self.group_badge.hide()
        self.bearing_rail = self.model_selector_container

        self.analysis_formulation = QComboBox(self)
        for mode in BearingAnalysisFormulation:
            self.analysis_formulation.addItem(mode.value, mode.value)
        self.analysis_formulation.setCurrentText(BearingAnalysisFormulation.DIMENSIONAL_HEAT_BALANCE.value)
        self.analysis_formulation.hide()
        self.coordinate_convention = QComboBox(self)
        for convention in BearingCoordinateConvention:
            self.coordinate_convention.addItem(convention.value, convention.value)
        self.coordinate_convention.setCurrentText(BearingCoordinateConvention.STANDARD_XY.value)
        self.coordinate_convention.hide()
        self.parity_status = QLabel(self); self.parity_status.hide()

        self.output_kc_button = QPushButton(self); self.output_kc_button.hide()
        self.output_dimensional_button = QPushButton(self); self.output_dimensional_button.hide()
        self.output_kc_button.clicked.connect(lambda: self._open_output(0))
        self.output_dimensional_button.clicked.connect(self._open_dimensional_output)

        self.selection.selection_changed.connect(self._workspace_selection_changed)
        self.bearing_selector.currentIndexChanged.connect(self._bearing_combo_changed)
        self.input_panel.changed.connect(self._mark_stale)
        self.additional_results.result_requested.connect(self._open_additional_result)

        key = next((spec.key for spec in MODEL_SPECS if spec.ross_class == bearing.ross_class), None)
        if key is None or key == "amb":
            key = next(spec.key for spec in MODEL_SPECS if spec.family == self.current_group)
        self._select_type(key, announce=False)
        self._sync_target_node()
        self._set_ui_state(BearingUiState.INPUT_READY if self.station is not None else BearingUiState.NO_STATION)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build_header(self, root: QVBoxLayout) -> None:
        row = QHBoxLayout()
        title = QLabel("Bearing Studio")
        title.setObjectName("bearingStudioTitle")
        row.addWidget(title)
        self.crumb = QLabel("Model  /  Bearings")
        self.crumb.setObjectName("muted")
        row.addWidget(self.crumb)
        row.addStretch(1)
        root.addLayout(row)

    def _build_model_selector(self, root: QVBoxLayout) -> None:
        holder = QWidget()
        holder.setObjectName("bearingModelSelector")
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        groups = (
            ("General Bearing Models (Rolling Element)", BearingGroup.GENERAL, 3),
            ("Fluid-Film Bearing Models (THD / Advanced)", BearingGroup.THD, 4),
            ("Active Magnetic Bearings", BearingGroup.AMB, 1),
        )
        self.type_buttons: dict[str, BearingModelCard] = {}
        self.type_metadata: dict[str, tuple[str, str, BearingGroup]] = {}
        self.family_panels: dict[BearingGroup, BearingFamilyPanel] = {}
        for title, group, stretch in groups:
            specs = [spec for spec in MODEL_SPECS if spec.family == group]
            panel = BearingFamilyPanel(title, specs)
            self.family_panels[group] = panel
            row.addWidget(panel, stretch)
            for card, spec in zip(panel.cards, specs):
                self.type_buttons[spec.key] = card
                self.type_metadata[spec.key] = (spec.public_name, spec.ross_class, spec.family)
                card.clicked.connect(lambda checked=False, key=spec.key: self._select_type(key))
        root.addWidget(holder)
        self.model_selector_container = holder

    def _build_input_and_operating_area(self, root: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)
        self.input_card = QFrame()
        self.input_card.setObjectName("bearingInputArea")
        input_layout = QVBoxLayout(self.input_card)
        input_layout.setContentsMargins(0, 0, 0, 0)
        self.input_panel = BearingInputWorkspace(
            self.project.engineering,
            self.bearing_index,
            self.bearing.ross_class if self.bearing.ross_class in MODEL_BY_CLASS else "BallBearingElement",
        )
        input_layout.addWidget(self.input_panel)
        row.addWidget(self.input_card, 4)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(7)
        self.operating_panel = MetricPanel("Operating Point")
        self.operating_panel.set_metrics([("Status", "Not calculated")])
        right_layout.addWidget(self.operating_panel, 1)

        apply = QFrame()
        apply.setObjectName("bearingMetricPanel")
        apply_layout = QVBoxLayout(apply)
        apply_layout.setContentsMargins(10, 7, 10, 8)
        apply_layout.setSpacing(5)
        title = QLabel("Apply Calculated Bearing at")
        title.setObjectName("bearingInputSectionTitle")
        apply_layout.addWidget(title)
        self.bearing_selector = QComboBox()
        self.bearing_selector.setObjectName("bearingStationSelector")
        for station in self.stations:
            self.bearing_selector.addItem(station.display_label, station.index)
        selected = self.bearing_selector.findData(self.bearing_index)
        if selected >= 0:
            self.bearing_selector.setCurrentIndex(selected)
        apply_layout.addWidget(self.bearing_selector)
        self.target_node_label = QLabel()
        self.target_node_label.setObjectName("muted")
        self.target_node_label.setWordWrap(True)
        apply_layout.addWidget(self.target_node_label)
        self.apply_button = QPushButton("Apply to Rotor")
        self.apply_button.setObjectName("successButton")
        self.apply_button.setIcon(engineering_icon("check", 18))
        self.apply_button.setEnabled(False)
        apply_layout.addWidget(self.apply_button)
        right_layout.addWidget(apply)
        row.addWidget(right, 1)
        root.addLayout(row)

    def _build_action_bar(self, root: QVBoxLayout) -> None:
        bar = QFrame()
        bar.setObjectName("bearingActionBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 5, 8, 5)
        layout.setSpacing(8)
        self.info_icon = QLabel()
        self.info_icon.setPixmap(engineering_icon("info", 18).pixmap(18, 18))
        layout.addWidget(self.info_icon)
        self.info_label = QLabel("Select a bearing model and review its engineering inputs.")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label, 1)
        self.state_label = QLabel()
        self.state_label.setObjectName("bearingStateLabel")
        layout.addWidget(self.state_label)
        self.calculate_button = QPushButton("Calculate Bearing")
        self.calculate_button.setObjectName("primaryButton")
        self.calculate_button.setIcon(engineering_icon("gear", 18, "#ffffff"))
        layout.addWidget(self.calculate_button)
        root.addWidget(bar)

    def _build_results(self, root: QVBoxLayout) -> None:
        card = QFrame()
        card.setObjectName("bearingResultsArea")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        card_layout.addWidget(self.tabs)

        kc_page = QWidget()
        kc_layout = QHBoxLayout(kc_page)
        kc_layout.setContentsMargins(8, 8, 8, 8)
        kc_layout.setSpacing(8)
        self.coefficient_model = CoefficientTableModel(self)
        self.kc_table = QTableView()
        self.kc_table.setObjectName("bearingCoefficientTable")
        self.kc_table.setModel(self.coefficient_model)
        self.kc_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.kc_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.kc_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.kc_table.verticalHeader().setVisible(False)
        self.kc_table.horizontalHeader().setStretchLastSection(True)
        self.kc_table.setMinimumWidth(500)
        self.kc_table.selectionModel().currentRowChanged.connect(self._coefficient_row_changed)
        kc_layout.addWidget(self.kc_table, 5)

        plot_card = Card()
        plot_layout = QVBoxLayout(plot_card)
        plot_layout.setContentsMargins(9, 7, 9, 9)
        top = QHBoxLayout()
        plot_title = QLabel("Stiffness and Damping Coefficients")
        plot_title.setObjectName("bearingInputSectionTitle")
        top.addWidget(plot_title)
        top.addStretch(1)
        self.plot_kind = QComboBox()
        self.plot_kind.addItems(["Stiffness (K)", "Damping (C)"])
        top.addWidget(self.plot_kind)
        plot_layout.addLayout(top)
        self.plot_stack = QStackedWidget()
        self.coefficient_chart = BearingCoefficientChart(self.bearing)
        self.plot_kind.currentIndexChanged.connect(self.coefficient_chart.set_coefficient_kind)
        self.plot_stack.addWidget(self.coefficient_chart)
        self.kc_native_view = NativeRossFigureView()
        self.plot_stack.addWidget(self.kc_native_view)
        plot_layout.addWidget(self.plot_stack, 1)
        kc_layout.addWidget(plot_card, 3)

        self.additional_results = AdditionalResultsPanel()
        kc_layout.addWidget(self.additional_results, 2)
        self.kc_tab_index = self.tabs.addTab(kc_page, "K & C Coefficients")

        self.result_views: dict[str, NativeRossFigureView] = {}
        for name in ("Pressure", "Temperature", "Film Thickness", "Journal Position", "Convergence", "Dimensional"):
            page = QWidget()
            lay = QVBoxLayout(page)
            lay.setContentsMargins(8, 8, 8, 8)
            view = NativeRossFigureView()
            view.set_unavailable(f"{name} is not available for the selected bearing result.")
            lay.addWidget(view, 1)
            self.result_views[name] = view
            self.tabs.addTab(page, name)
        self.dimensional_tab_index = self._tab_index("Dimensional")
        self.tabs.currentChanged.connect(self._tab_changed)

        self.native_frequency_selector = QComboBox(self); self.native_frequency_selector.hide()
        self.native_plot_selector = QComboBox(self); self.native_plot_selector.hide()
        self.native_text_selector = QComboBox(self); self.native_text_selector.hide()
        self.native_plot_view = self.result_views["Dimensional"]
        self.native_text_output = QLabel(self); self.native_text_output.hide()
        self.native_frequency_selector.currentIndexChanged.connect(self._frequency_changed)

        self.result_card = card
        self.result_card.setMinimumHeight(330)
        self.result_card.hide()
        root.addWidget(card, 1)

        self.results_button = QPushButton(self)
        self.results_button.hide()
        self.results_button.clicked.connect(lambda: self.set_results_visible(True))

    # ------------------------------------------------------------------
    # Selection / state
    # ------------------------------------------------------------------
    def _current_spec(self) -> BearingModelSpec:
        for key, button in self.type_buttons.items():
            if button.isChecked():
                return MODEL_BY_KEY[key]
        return MODEL_BY_CLASS.get(self.bearing.ross_class, MODEL_SPECS[0])

    def _current_ross_class(self) -> str:
        return self._current_spec().ross_class

    def _select_type(self, key: str, *, announce: bool = True) -> None:
        spec = MODEL_BY_KEY[key]
        for name, button in self.type_buttons.items():
            button.setChecked(name == key)
        self.current_group = spec.family
        self.group_badge.setText(spec.family.value) if hasattr(self, "group_badge") else None
        if hasattr(self, "group_selector"):
            idx = self.group_selector.findData(spec.family.value)
            if idx >= 0 and idx != self.group_selector.currentIndex():
                self.group_selector.blockSignals(True); self.group_selector.setCurrentIndex(idx); self.group_selector.blockSignals(False)
        self.crumb.setText(f"Model  /  Bearings  /  {self.bearing.name}  /  {spec.public_name}")
        self.input_panel.set_model(self.project.engineering, self.bearing_index, spec.ross_class)
        self.input_panel.changed.connect(self._mark_stale)
        if spec.ross_class == "TiltingPad" and "pad_data" in self.input_panel.fields:
            self.input_panel.fields.setdefault("pivot_angles_deg", self.input_panel.fields["pad_data"])

        status, reason = self.catalog.registry.effective_status(spec.ross_class)
        executable = spec.executable and status == AdapterStatus.VALIDATED
        self.calculate_button.setEnabled(executable)
        self.apply_button.setEnabled(False)
        self._result_available = False
        self.result_card.hide()
        self.results_button.setEnabled(False)
        self.output_kc_button.setEnabled(False) if hasattr(self, "output_kc_button") else None
        self.output_dimensional_button.setEnabled(False) if hasattr(self, "output_dimensional_button") else None
        self._configure_tabs(spec)
        self.additional_results.set_results(spec.additional_results, set())
        self._sync_parity_contract()
        self._set_ui_state(BearingUiState.INPUT_READY if executable else BearingUiState.MODEL_SELECTED)
        if spec.ross_class == "MagneticBearingElement":
            self.info_label.setText("Magnetic Bearing (AMB) is present by design but remains blocked until the feedback/Newmark rotor workflow is scientifically qualified.")
        elif spec.axial:
            self.info_label.setText("Thrust Pad is axial. Calculate returns native ROSS Kzz/Czz and THD fields; Apply never maps Kzz/Czz into lateral K/C.")
        elif spec.family == BearingGroup.THD:
            self.info_label.setText(f"{spec.public_name} uses native ROSS fluid-film results. Calculate creates a cached preview; tab navigation never re-solves the bearing.")
        else:
            self.info_label.setText(f"{spec.public_name} calculates ROSS K/C coefficients. Calculate is preview-only; Apply commits explicitly to the selected exact ROSS node.")
        if announce:
            detail = "" if executable else (f" {reason}" if reason else " Model remains blocked.")
            self.status_message.emit(f"{spec.public_name}: {'ready' if executable else 'blocked'}.{detail}")

    def set_group(self, group: str, *, announce: bool = True) -> None:
        selected = BearingGroup(group)
        self.current_group = selected
        candidates = [spec for spec in MODEL_SPECS if spec.family == selected]
        preferred = next((spec for spec in candidates if spec.ross_class == self.bearing.ross_class), candidates[0])
        self._select_type(preferred.key, announce=announce)

    def _bearing_combo_changed(self, row: int) -> None:
        index = self.bearing_selector.itemData(row)
        if index is None:
            return
        index = int(index)
        station = next((candidate for candidate in self.stations if candidate.index == index), None)
        if station is not None:
            self.selection.select(RotorEntityRef("bearings", index, station.name, station.position_mm))
        self._sync_target_node()
        if index != self.bearing_index:
            self.bearing_selected.emit(index)

    def _workspace_selection_changed(self, ref: RotorEntityRef | None) -> None:
        if ref is None or ref.kind != "bearings" or self.project.engineering is None:
            return
        try:
            anchor = self.workspace.anchor_index(self.project.engineering, ref.index)
            station = self.workspace.station(self.project.engineering, anchor)
        except Exception:
            return
        row = self.bearing_selector.findData(anchor)
        if row >= 0 and row != self.bearing_selector.currentIndex():
            self.bearing_selector.setCurrentIndex(row)
        elif row >= 0 and ref.index != anchor:
            self.selection.select(RotorEntityRef("bearings", anchor, station.name, station.position_mm))

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
        node = "unresolved" if station.ross_node is None else str(station.ross_node)
        self.target_node_label.setText(f"x = {station.position_mm:g} mm · exact ROSS node {node}")

    def _set_ui_state(self, state: BearingUiState, detail: str = "") -> None:
        self.ui_state = state
        labels = {
            BearingUiState.NO_STATION: "No station",
            BearingUiState.MODEL_SELECTED: "Model selected",
            BearingUiState.INPUT_READY: "Model ready for calculation",
            BearingUiState.CALCULATING: "Calculating...",
            BearingUiState.CALCULATED_PREVIEW: "Calculated preview",
            BearingUiState.STALE: "Inputs changed · recalculate",
            BearingUiState.APPLIED: "Applied",
            BearingUiState.ERROR: "Calculation error",
        }
        self.state_label.setText(labels[state] + (f" · {detail}" if detail else ""))
        self.state_label.setProperty("state", state.value)
        self.state_label.style().unpolish(self.state_label); self.state_label.style().polish(self.state_label)
        if state == BearingUiState.CALCULATING:
            self.calculate_button.setEnabled(False)
            self.apply_button.setEnabled(False)
        elif state == BearingUiState.STALE:
            self.apply_button.setEnabled(False)
        elif state == BearingUiState.CALCULATED_PREVIEW:
            self.apply_button.setEnabled(True)

    def set_calculating(self) -> None:
        self._set_ui_state(BearingUiState.CALCULATING)

    def set_error(self, message: str) -> None:
        self._set_ui_state(BearingUiState.ERROR)
        self.info_label.setText(message)
        status, _ = self.catalog.registry.effective_status(self._current_ross_class())
        self.calculate_button.setEnabled(status == AdapterStatus.VALIDATED and self._current_spec().executable)

    def _mark_stale(self) -> None:
        if self.ui_state == BearingUiState.CALCULATED_PREVIEW:
            self._input_dirty = True
            self._set_ui_state(BearingUiState.STALE)
        elif self.ui_state not in {BearingUiState.CALCULATING, BearingUiState.ERROR}:
            self._set_ui_state(BearingUiState.INPUT_READY)

    # ------------------------------------------------------------------
    # Scientific input contract
    # ------------------------------------------------------------------
    def _selected_analysis(self) -> BearingAnalysisFormulation:
        return BearingAnalysisFormulation(str(self.analysis_formulation.currentData()))

    def _selected_coordinates(self) -> BearingCoordinateConvention:
        return BearingCoordinateConvention(str(self.coordinate_convention.currentData()))

    def _sync_parity_contract(self) -> None:
        ross_class = self._current_ross_class()
        if ross_class not in self.BEPERF_FLUID_CLASSES:
            return
        contract = contract_for(ross_class)
        analysis = self._selected_analysis()
        coords = self._selected_coordinates()
        a = contract.analyses[analysis]
        c = contract.coordinates[coords]
        if a.status is not CapabilityStatus.ROSS_NATIVE or c.status is not CapabilityStatus.ROSS_NATIVE:
            self.calculate_button.setEnabled(False)

    def input_values(self) -> dict:
        values = self.input_panel.values()
        ross_class = self._current_ross_class()
        if ross_class in self.BEPERF_FLUID_CLASSES:
            analysis = self._selected_analysis()
            coordinates = self._selected_coordinates()
            require_executable_contract(ross_class, analysis, coordinates)
            values["studio_analysis_formulation"] = analysis.value
            values["studio_coordinate_convention"] = coordinates.value
        return values

    # ------------------------------------------------------------------
    # Results / cache presentation
    # ------------------------------------------------------------------
    def _configure_tabs(self, spec: BearingModelSpec) -> None:
        enabled = set(spec.result_tabs)
        for i in range(self.tabs.count()):
            name = self.tabs.tabText(i)
            on = name in enabled
            self.tabs.setTabEnabled(i, on)
            if hasattr(self.tabs, "setTabVisible"):
                self.tabs.setTabVisible(i, on)
        if "K & C Coefficients" in enabled:
            self.tabs.setCurrentIndex(self.kc_tab_index)

    def _tab_index(self, name: str) -> int:
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == name:
                return i
        return -1

    def set_results_available(self, available: bool, *, show: bool = False) -> None:
        self._result_available = bool(available)
        self.results_button.setEnabled(bool(available))
        self.output_kc_button.setEnabled(bool(available))
        self.output_dimensional_button.setEnabled(bool(available and self._current_spec().family == BearingGroup.THD))
        if not available:
            self.result_card.hide()
            return
        self.result_card.setVisible(True if show or available else False)
        self._input_dirty = False
        self._set_ui_state(BearingUiState.CALCULATED_PREVIEW)

    def set_results_visible(self, visible: bool) -> None:
        if visible and not self._result_available:
            return
        self.result_card.setVisible(bool(visible))
        if visible:
            self.workspace_scroll.ensureWidgetVisible(self.result_card, 0, 20)

    def _rows_from_bearing(self, bearing: BearingModel) -> tuple[list[str], list[list[Any]], int]:
        headers = ["RPM", "Kxx\n(N/m)", "Kxy\n(N/m)", "Kyx\n(N/m)", "Kyy\n(N/m)", "Cxx\n(N·s/m)", "Cxy\n(N·s/m)", "Cyx\n(N·s/m)", "Cyy\n(N·s/m)"]
        rows = [[float(c.rpm), float(c.kxx), float(c.kxy), float(c.kyx), float(c.kyy), float(c.cxx), float(c.cxy), float(c.cyx), float(c.cyy)] for c in bearing.coefficients]
        nominal = -1
        if rows and self.project.engineering is not None:
            rated = float(self.project.engineering.operating_cases[0].rated_speed_rpm)
            nominal = min(range(len(rows)), key=lambda i: abs(rows[i][0] - rated))
        return headers, rows, nominal

    def set_bearing_preview(self, bearing: BearingModel) -> None:
        self.bearing = bearing
        headers, rows, nominal = self._rows_from_bearing(bearing)
        self.nominal_index = nominal
        self.coefficient_model.set_data(headers, rows, nominal)
        self.kc_table.resizeColumnsToContents()
        self.coefficient_chart.bearing = bearing
        self.coefficient_chart.update()
        if self._current_spec().family == BearingGroup.THD:
            self.plot_stack.setCurrentWidget(self.kc_native_view)
        else:
            self.plot_stack.setCurrentWidget(self.coefficient_chart)
        if rows:
            self.kc_table.selectRow(max(0, nominal))
            self._update_general_operating_point(max(0, nominal))
        self.set_results_available(True, show=True)

    def set_thd_result(self, result) -> None:
        self._result_object = result
        self._load_native_outputs(getattr(result, "native_element", None))
        spec = MODEL_BY_CLASS[result.source_model]
        self._configure_tabs(spec)
        self.additional_results.set_results(spec.additional_results, self._available_additional_results(spec))
        if result.source_model == "SqueezeFilmDamper":
            self._set_sfd_table(result)
        if getattr(result, "operating_points", None):
            self._update_thd_operating_point(max(0, self.nominal_index))
        self.set_results_available(True, show=True)

    def set_thrust_result(self, result) -> None:
        self._result_object = result
        headers = ["RPM", "Kzz\n(N/m)", "Czz\n(N·s/m)"]
        rows = [[float(c.rpm), float(c.kzz), float(c.czz)] for c in result.axial_coefficients]
        rated = float(self.project.engineering.operating_cases[0].rated_speed_rpm)
        nominal = min(range(len(rows)), key=lambda i: abs(rows[i][0] - rated)) if rows else -1
        self.nominal_index = nominal
        self.coefficient_model.set_data(headers, rows, nominal)
        self.kc_table.resizeColumnsToContents()
        if rows:
            self.kc_table.selectRow(max(0, nominal))
        self._load_native_outputs(getattr(result, "native_element", None))
        spec = MODEL_BY_CLASS["ThrustPad"]
        self._configure_tabs(spec)
        self.additional_results.set_results(spec.additional_results, self._available_additional_results(spec))
        self._update_thrust_operating_point(max(0, nominal))
        self.plot_stack.setCurrentWidget(self.kc_native_view)
        self.set_results_available(True, show=True)

    def _set_sfd_table(self, result) -> None:
        native = getattr(result, "native_element", None)
        pmax = np.asarray(getattr(native, "p_max", []), dtype=float).reshape(-1) if native is not None else np.array([])
        theta = np.asarray(getattr(native, "theta", []), dtype=float).reshape(-1) if native is not None else np.array([])
        headers = ["RPM", "Kxx\n(N/m)", "Cxx\n(N·s/m)", "p_max\n(Pa)", "theta"]
        rows = []
        for i, coeff in enumerate(result.coefficients):
            rows.append([float(coeff.rpm), float(coeff.kxx), float(coeff.cxx), float(pmax[i]) if i < pmax.size else float("nan"), float(theta[i]) if i < theta.size else float("nan")])
        rated = float(self.project.engineering.operating_cases[0].rated_speed_rpm)
        nominal = min(range(len(rows)), key=lambda i: abs(rows[i][0] - rated)) if rows else -1
        self.nominal_index = nominal
        self.coefficient_model.set_data(headers, rows, nominal)
        if rows:
            self.kc_table.selectRow(max(0, nominal))

    def _coefficient_row_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        if not current.isValid():
            return
        row = current.row()
        result = self._result_object
        if result is None:
            self._update_general_operating_point(row)
            return
        if getattr(result, "source_model", "") == "ThrustPad":
            self._update_thrust_operating_point(row)
        else:
            self._update_thd_operating_point(row)
        if self._native_element is not None:
            self._reload_dimensional_outputs(row)

    def _update_general_operating_point(self, row: int) -> None:
        if row < 0 or row >= len(self.coefficient_model.rows):
            return
        data = self.coefficient_model.rows[row]
        headers = self.coefficient_model.headers
        metrics = []
        for i, name in enumerate(headers):
            label = name.replace("\n", " ")
            value = data[i]
            metrics.append((label, f"{value:.4e}" if i else f"{value:,.0f} rpm"))
        self.operating_panel.set_metrics(metrics[:9])

    @staticmethod
    def _fmt(value: Any, unit: str = "", scale: float = 1.0) -> str:
        if value is None:
            return "—"
        try:
            number = float(value) * scale
        except Exception:
            return str(value)
        if not np.isfinite(number):
            return "—"
        return f"{number:.5g}{(' ' + unit) if unit else ''}"

    def _update_thd_operating_point(self, row: int) -> None:
        result = self._result_object
        if result is None or not getattr(result, "operating_points", None):
            return
        row = min(max(0, row), len(result.operating_points) - 1)
        op = result.operating_points[row]
        source = result.source_model
        metrics: list[tuple[str, str]] = [("Operating Speed", self._fmt(op.rpm, "rpm"))]
        if source == "SqueezeFilmDamper":
            coeff = result.coefficients[row]
            theta = getattr(result.native_element, "theta", None)
            theta_value = None
            try: theta_value = np.asarray(theta, dtype=float).reshape(-1)[row]
            except Exception: pass
            metrics += [
                ("Eccentricity Ratio", self._fmt(op.eccentricity_ratio)),
                ("Maximum Pressure", self._fmt(op.max_pressure_pa, "Pa")),
                ("Pressure Angle", self._fmt(theta_value, "rad")),
                ("Kxx", self._fmt(coeff.kxx, "N/m")),
                ("Cxx", self._fmt(coeff.cxx, "N·s/m")),
            ]
        elif source == "TiltingPad":
            metrics += [
                ("Eccentricity", self._fmt(op.eccentricity_ratio)),
                ("Attitude Angle", self._fmt(op.attitude_angle_rad, "deg", 180.0 / pi)),
                ("Maximum Pressure", self._fmt(op.max_pressure_pa, "Pa")),
                ("Maximum Temperature", self._fmt(op.max_temperature_c, "°C")),
                ("Minimum Film Thickness", self._fmt(op.min_film_thickness_m, "µm", 1e6)),
                ("Equilibrium Status", "Solved"),
            ]
        else:
            metrics += [
                ("Eccentricity Ratio", self._fmt(op.eccentricity_ratio)),
                ("Attitude Angle", self._fmt(op.attitude_angle_rad, "deg", 180.0 / pi)),
                ("Maximum Pressure", self._fmt(op.max_pressure_pa, "Pa")),
                ("Maximum Temperature", self._fmt(op.max_temperature_c, "°C")),
                ("Optimization Status", "Converged"),
                ("Execution Time", "ROSS native"),
            ]
        self.operating_panel.set_metrics(metrics)

    def _update_thrust_operating_point(self, row: int) -> None:
        result = self._result_object
        if result is None or not getattr(result, "operating_points", None):
            return
        row = min(max(0, row), len(result.operating_points) - 1)
        op = result.operating_points[row]
        coeff = result.axial_coefficients[row]
        axial_load = result.metadata.get("axial_load_n")
        self.operating_panel.set_metrics([
            ("Operating Speed", self._fmt(op.rpm, "rpm")),
            ("Axial Load", self._fmt(axial_load, "N")),
            ("Maximum Pressure", self._fmt(op.max_pressure_pa, "Pa")),
            ("Maximum Temperature", self._fmt(op.max_temperature_c, "°C")),
            ("Minimum Film Thickness", self._fmt(op.min_film_thickness_m, "µm", 1e6)),
            ("Pivot Film Thickness", self._fmt(op.pivot_film_thickness_m, "µm", 1e6)),
            ("Kzz", self._fmt(coeff.kzz, "N/m")),
            ("Czz", self._fmt(coeff.czz, "N·s/m")),
        ])

    # ------------------------------------------------------------------
    # Native ROSS plots; no bearing re-solve occurs here
    # ------------------------------------------------------------------
    def _load_native_outputs(self, native_element) -> None:
        self._native_element = native_element
        if native_element is None:
            self.kc_native_view.set_unavailable("ROSS did not retain a native bearing object for this preview.")
            return
        frequency = np.atleast_1d(getattr(native_element, "frequency", []))
        self.native_frequency_selector.blockSignals(True)
        self.native_frequency_selector.clear()
        for i, omega in enumerate(frequency):
            self.native_frequency_selector.addItem(f"{float(omega) * 30.0 / pi:,.1f} rpm", i)
        self.native_frequency_selector.blockSignals(False)
        try:
            figure = self.native_plot_service.kc_figure(native_element)
        except NativeRossPlotUnavailable as exc:
            self.kc_native_view.set_unavailable(str(exc))
        else:
            if figure is None:
                self.kc_native_view.set_unavailable("ROSS 2.3.0 did not return a native K/C figure for this model.")
            else:
                self.kc_native_view.set_figure(figure, tooltip="ROSS native bearing K/C")
        self.plot_stack.setCurrentWidget(self.kc_native_view)
        self._reload_dimensional_outputs(max(0, self.nominal_index))

    def _reload_dimensional_outputs(self, freq_index: int) -> None:
        if self._native_element is None:
            return
        try:
            output = self.native_plot_service.dimensional_outputs(self._native_element, freq_index=max(0, int(freq_index)))
        except NativeRossPlotUnavailable as exc:
            self._dimensional_outputs = NativeFigureSet(type(self._native_element).__name__, {})
            for view in self.result_views.values():
                view.set_unavailable(str(exc))
            return
        self._dimensional_outputs = output
        self.native_plot_selector.blockSignals(True); self.native_plot_selector.clear()
        for name in output.figures: self.native_plot_selector.addItem(name)
        self.native_plot_selector.blockSignals(False)
        self.native_text_selector.blockSignals(True); self.native_text_selector.clear()
        for name in output.text_outputs: self.native_text_selector.addItem(name)
        self.native_text_selector.blockSignals(False)
        self._route_native_figures(output)

    def _route_native_figures(self, output: NativeFigureSet) -> None:
        names = list(output.figures)
        routes = {
            "Pressure": ("pressure",),
            "Temperature": ("temperature", "babbitt", "solid pad"),
            "Film Thickness": ("film", "thickness"),
            "Journal Position": ("journal", "position", "bearing representation"),
            "Convergence": ("convergence", "optimization"),
            "Dimensional": ("bearing representation", "results"),
        }
        for tab, tokens in routes.items():
            match = next((name for name in names if any(token in name.lower() for token in tokens)), None)
            view = self.result_views[tab]
            if match is not None:
                view.set_figure(output.figures[match], tooltip=f"ROSS native · {match}")
            else:
                view.set_unavailable(f"ROSS did not return a qualified native {tab.lower()} figure for this result.")

    def _available_additional_results(self, spec: BearingModelSpec) -> set[str]:
        figure_names = {name.lower() for name in self._dimensional_outputs.figures}
        text_names = {name.lower() for name in self._dimensional_outputs.text_outputs}
        available: set[str] = set()
        for name in spec.additional_results:
            key = name.lower()
            tokens = {
                "pressure field": ("pressure",),
                "temperature field": ("temperature",),
                "convergence": ("convergence", "optimization"),
                "bearing representation": ("bearing representation",),
                "pad pressure": ("pad pressure", "pressure"),
                "babbitt temperature": ("babbitt",),
                "solid pad temperature": ("solid pad",),
            }.get(key, (key,))
            if any(any(token in source for token in tokens) for source in figure_names | text_names):
                available.add(name)
        return available

    def _open_additional_result(self, name: str) -> None:
        lower = name.lower()
        tab = "Dimensional"
        if "pressure" in lower: tab = "Pressure"
        elif "temperature" in lower or "babbitt" in lower or "solid" in lower: tab = "Temperature"
        elif "convergence" in lower: tab = "Convergence"
        idx = self._tab_index(tab)
        if idx >= 0 and self.tabs.isTabEnabled(idx):
            self.tabs.setCurrentIndex(idx)
            self.workspace_scroll.ensureWidgetVisible(self.result_card, 0, 20)

    def _tab_changed(self, _index: int) -> None:
        # Presentation-only by contract. Native figures are read from the retained
        # result cache; this signal must never invoke a bearing solver.
        return

    def _frequency_changed(self, row: int) -> None:
        if row >= 0:
            self._reload_dimensional_outputs(int(self.native_frequency_selector.itemData(row) or 0))

    def _open_output(self, tab_index: int) -> None:
        if not self._result_available:
            return
        self.set_results_visible(True)
        self.tabs.setCurrentIndex(tab_index)

    def _open_dimensional_output(self) -> None:
        if self.dimensional_tab_index >= 0 and self.tabs.isTabEnabled(self.dimensional_tab_index):
            self._open_output(self.dimensional_tab_index)


__all__ = ["BearingStudioPage", "CoefficientTableModel", "BearingModelCard", "BearingFamilyPanel"]
