from __future__ import annotations

from PySide6.QtCore import QSize, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ..bearing_input_panel import BearingInputPanel
from ..bearing_workspace import BearingStation, BearingStationInventory, BearingWorkspaceService
from ..domain import AdapterStatus, BearingGroup
from ..icons import engineering_icon
from ..models import BearingModel, ProjectModel
from ..rotor_selection import RotorEntityRef, WORKSPACE_SELECTION
from ..services import BearingCatalogService
from ..widgets import BearingCoefficientChart, Card, ProjectInfoCard, SectionCard, configure_table, item
from .thd_results import THDResultTab


class BearingStudioPage(QWidget):
    """Bearing Studio engineering workspace with inline class-specific inputs.

    The physical bearing station remains the primary identity. Clicking one bearing
    model icon immediately replaces the engineering input panel in the main work area.
    Calculation results live below the editor and can be reached either by scrolling
    or through the explicit View Results action. Calculate remains preview-only and
    Apply is the only operation that mutates the selected station.
    """

    status_message = Signal(str)
    bearing_selected = Signal(int)

    TYPE_DEFINITIONS = (
        ("kc", "Coefficient K/C", "bearing_kc", "BearingElement", BearingGroup.GENERAL),
        ("ball", "Ball Bearing", "ball_bearing", "BallBearingElement", BearingGroup.GENERAL),
        ("roller", "Roller Bearing", "roller_bearing", "RollerBearingElement", BearingGroup.GENERAL),
        ("cyl", "Cylindrical", "cylindrical_bearing", "CylindricalBearing", BearingGroup.GENERAL),
        ("plain", "Plain Journal", "plain_journal", "PlainJournal", BearingGroup.THD),
        ("tilting", "Tilting Pad", "tilting_pad", "TiltingPad", BearingGroup.THD),
        ("thrust", "Thrust Pad", "thrust_pad", "ThrustPad", BearingGroup.THD),
        ("sfd", "Squeeze Film Damper", "sfd", "SqueezeFilmDamper", BearingGroup.THD),
        ("amb", "Active Magnetic Bearing", "amb", "MagneticBearingElement", BearingGroup.AMB),
    )

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
        self.stations: tuple[BearingStation, ...] = (
            self.workspace.stations(project.engineering) if project.engineering is not None else ()
        )
        self.station = next((row for row in self.stations if row.index == self.bearing_index), None)
        self.inventory: BearingStationInventory | None = (
            self.workspace.inventory(project.engineering, self.bearing_index)
            if project.engineering is not None and self.station is not None
            else None
        )
        try:
            self.current_group = BearingGroup(bearing.group)
        except ValueError:
            self.current_group = BearingGroup.GENERAL

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        self.workspace_scroll = QScrollArea()
        self.workspace_scroll.setObjectName("bearingWorkspaceScroll")
        self.workspace_scroll.setWidgetResizable(True)
        self.workspace_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.workspace_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(self.workspace_scroll, 1)

        center_holder = QWidget()
        center_holder.setObjectName("bearingWorkspaceContent")
        center = QVBoxLayout(center_holder)
        center.setContentsMargins(0, 0, 4, 0)
        center.setSpacing(10)
        self.workspace_scroll.setWidget(center_holder)

        page_card = Card()
        page_layout = QVBoxLayout(page_card)
        page_layout.setContentsMargins(14, 10, 14, 12)
        page_layout.setSpacing(9)

        header_row = QHBoxLayout()
        title = QLabel("Bearing Studio 2.0")
        title.setObjectName("cardHeader")
        header_row.addWidget(title)
        self.crumb = QLabel()
        self.crumb.setObjectName("muted")
        header_row.addWidget(self.crumb)
        header_row.addStretch(1)
        page_layout.addLayout(header_row)

        station_row = QHBoxLayout()
        station_label = QLabel("Bearing Station")
        station_label.setObjectName("subHeader")
        station_row.addWidget(station_label)
        self.bearing_selector = QComboBox()
        self.bearing_selector.setObjectName("bearingStationSelector")
        for station in self.stations:
            self.bearing_selector.addItem(station.display_label, station.index)
        selected_row = self.bearing_selector.findData(self.bearing_index)
        if selected_row >= 0:
            self.bearing_selector.setCurrentIndex(selected_row)
        self.bearing_selector.setEnabled(bool(self.stations))
        self.bearing_selector.currentIndexChanged.connect(self._bearing_combo_changed)
        station_row.addWidget(self.bearing_selector, 1)
        page_layout.addLayout(station_row)

        # Family remains a domain classification and compatibility API, but is no
        # longer an extra navigation step. Model icons are the user's direct selector.
        self.group_selector = QComboBox(self)
        self.group_selector.setObjectName("bearingFamilySelector")
        for group in (BearingGroup.GENERAL, BearingGroup.THD, BearingGroup.AMB):
            self.group_selector.addItem(group.value, group.value)
        self.group_selector.currentTextChanged.connect(self.set_group)
        self.group_selector.hide()
        self.group_badge = QLabel()
        self.group_badge.setObjectName("bearingFamilyBadge")
        self.group_badge.hide()

        bearing_type_header = QHBoxLayout()
        lab = QLabel("Bearing Type")
        lab.setObjectName("subHeader")
        bearing_type_header.addWidget(lab)
        hint = QLabel("Click a model icon to display its engineering inputs")
        hint.setObjectName("muted")
        bearing_type_header.addWidget(hint)
        bearing_type_header.addStretch(1)
        page_layout.addLayout(bearing_type_header)

        types = QGridLayout()
        types.setHorizontalSpacing(8)
        types.setVerticalSpacing(8)
        self.type_buttons: dict[str, QPushButton] = {}
        self.type_metadata: dict[str, tuple[str, str, BearingGroup]] = {}
        for i, (key, text, icon, ross_class, group) in enumerate(self.TYPE_DEFINITIONS):
            button = QPushButton(text)
            button.setObjectName("bearingType")
            button.setCheckable(True)
            button.setIcon(engineering_icon(icon, 42))
            button.setIconSize(QSize(42, 42))
            button.setToolTip(f"{group.value} · ROSS {ross_class}")
            button.clicked.connect(lambda checked=False, k=key: self._select_type(k))
            self.type_buttons[key] = button
            self.type_metadata[key] = (text, ross_class, group)
            types.addWidget(button, i // 4, i % 4)
        for col in range(4):
            types.setColumnStretch(col, 1)
        page_layout.addLayout(types)

        self.editor_note = QLabel()
        self.editor_note.setObjectName("bearingEditorNote")
        self.editor_note.setWordWrap(True)
        page_layout.addWidget(self.editor_note)
        center.addWidget(page_card)

        self.input_card = SectionCard("Bearing Engineering Inputs")
        if project.engineering is None:
            raise RuntimeError("Bearing Studio requires a loaded engineering domain.")
        self.input_panel = BearingInputPanel(
            project.engineering,
            self.bearing_index,
            self.bearing.ross_class,
        )
        self.input_card.root.addWidget(self.input_panel)
        self.input_summary = QLabel(
            "Edit the selected model inputs above. Calculate Bearing is preview-only; "
            "Apply to Rotor commits only the selected physical station."
        )
        self.input_summary.setObjectName("bearingInputSummary")
        self.input_summary.setWordWrap(True)
        self.input_card.root.addWidget(self.input_summary)
        center.addWidget(self.input_card)

        self.result_card = SectionCard("Bearing Results")
        result_toolbar = QHBoxLayout()
        result_help = QLabel("Solved coefficients and native ROSS fields")
        result_help.setObjectName("muted")
        result_toolbar.addWidget(result_help)
        result_toolbar.addStretch(1)
        hide_results = QPushButton("Hide Results")
        hide_results.setObjectName("outlineButton")
        hide_results.setIcon(engineering_icon("minus", 18))
        hide_results.clicked.connect(lambda: self.set_results_visible(False))
        result_toolbar.addWidget(hide_results)
        self.result_card.root.addLayout(result_toolbar)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        self.result_card.root.addWidget(tabs)
        tabs.addTab(self._kc_tab(), "K & C Coefficients")
        self.result_tabs: dict[str, THDResultTab] = {}
        self.tabs = tabs
        for name in ("Pressure", "Temperature", "Film Thickness", "Journal Position", "Convergence"):
            holder = THDResultTab(name)
            self.result_tabs[name] = holder
            tabs.addTab(holder, name)
        self.result_card.setMinimumHeight(500)
        self.result_card.hide()
        center.addWidget(self.result_card)
        center.addStretch(1)

        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        right = QWidget()
        right.setFixedWidth(326)
        right.setLayout(right_layout)
        root.addWidget(right)
        right_layout.addWidget(ProjectInfoCard(project))
        right_layout.addWidget(self._bearing_info_card(), 1)
        right_layout.addWidget(self._actions_card())

        self.selection.selection_changed.connect(self._workspace_selection_changed)
        self.set_group(self.current_group.value, announce=False)
        self.set_results_available(False)

    def input_values(self) -> dict:
        """Return visible engineering inputs for the currently selected model."""
        return self.input_panel.values()

    def _bearing_combo_changed(self, row: int) -> None:
        index = self.bearing_selector.itemData(row)
        if index is None:
            return
        index = int(index)
        station = next((candidate for candidate in self.stations if candidate.index == index), None)
        if station is not None:
            self.selection.select(RotorEntityRef("bearings", index, station.name, station.position_mm))
        if index != self.bearing_index:
            self.bearing_selected.emit(index)

    def _workspace_selection_changed(self, ref: RotorEntityRef | None) -> None:
        """Mirror rotor-sketch bearing selection into the physical station selector."""
        engineering = self.project.engineering
        if ref is None or ref.kind != "bearings" or engineering is None:
            return
        try:
            anchor = self.workspace.anchor_index(engineering, ref.index)
            station = self.workspace.station(engineering, anchor)
        except Exception:
            return
        row = self.bearing_selector.findData(anchor)
        if row < 0:
            return
        if row != self.bearing_selector.currentIndex():
            self.bearing_selector.setCurrentIndex(row)
        elif ref.index != anchor:
            self.selection.select(RotorEntityRef("bearings", anchor, station.name, station.position_mm))

    def set_group(self, group: str, *, announce: bool = True) -> None:
        """Select one model family without making family navigation a visible extra step."""
        selected_group = BearingGroup(group)
        self.current_group = selected_group
        self.group_badge.setText(selected_group.value)
        combo_index = self.group_selector.findData(selected_group.value)
        if combo_index >= 0 and combo_index != self.group_selector.currentIndex():
            self.group_selector.blockSignals(True)
            self.group_selector.setCurrentIndex(combo_index)
            self.group_selector.blockSignals(False)

        group_keys = [
            key
            for key, (_title, _ross_class, button_group) in self.type_metadata.items()
            if button_group == selected_group
        ]
        preferred = next(
            (key for key in group_keys if self.type_metadata[key][1] == self.bearing.ross_class),
            group_keys[0] if group_keys else None,
        )
        if preferred is not None:
            self._select_type(preferred, announce=announce)

    def _select_type(self, key: str, *, announce: bool = True) -> None:
        for name, button in self.type_buttons.items():
            button.setChecked(name == key)
        title, ross_class, group = self.type_metadata[key]
        self.current_group = group
        self.group_badge.setText(group.value)
        combo_index = self.group_selector.findData(group.value)
        if combo_index >= 0 and combo_index != self.group_selector.currentIndex():
            self.group_selector.blockSignals(True)
            self.group_selector.setCurrentIndex(combo_index)
            self.group_selector.blockSignals(False)
        self.crumb.setText(f"Model  /  Bearings  /  {self.bearing.name}  /  {title}")

        status, reason = self.catalog.registry.effective_status(ross_class)
        self.adapter_state_label.setText(f"{ross_class}: {status.value}")
        self.calculate_button.setEnabled(status == AdapterStatus.VALIDATED)
        self.apply_button.setEnabled(False)
        self.set_results_available(False)

        if self.project.engineering is not None:
            self.input_panel.set_model(self.project.engineering, self.bearing_index, ross_class)

        station_name = self.station.name if self.station is not None else self.bearing.name
        if group == BearingGroup.GENERAL:
            self.editor_note.setText(
                f"Target station: {station_name}. General / Parametric classes use direct or analytical engineering inputs. "
                "Calculate never mutates the rotor; Apply replaces only this selected radial bearing."
            )
        elif ross_class == "ThrustPad":
            self.editor_note.setText(
                f"Target station: {station_name}. ThrustPad is axial-only. Apply adds/updates an independent Kzz/Czz "
                "BearingElement at this shaft station and never overwrites the existing radial K/C or lateral n_link."
            )
        elif group == BearingGroup.THD:
            self.editor_note.setText(
                f"Target station: {station_name}. Lateral THD retains native fields and solved K/C speed stations. "
                "Apply commits the solved BearingElement table only to the selected radial bearing."
            )
        else:
            self.editor_note.setText(
                "AMB execution remains blocked until actuator, sensor and controller definitions exist in the engineering domain."
            )

        if announce:
            self.workspace_scroll.ensureWidgetVisible(self.input_card, 0, 20)
            if status == AdapterStatus.VALIDATED:
                self.status_message.emit(f"{title}: engineering inputs ready for {station_name}")
            else:
                detail = f" {reason}" if reason else ""
                self.status_message.emit(f"{title}: {status.value}.{detail}")

    def set_results_available(self, available: bool, *, show: bool = False) -> None:
        self.results_button.setEnabled(bool(available))
        if not available:
            self.result_card.hide()
            self.results_button.setText("View Results")
            self.results_button.setIcon(engineering_icon("results", 19))
            return
        if show:
            self.set_results_visible(True)
        else:
            self.results_button.setText("View Results")
            self.results_button.setIcon(engineering_icon("results", 19))

    def set_results_visible(self, visible: bool) -> None:
        if visible and not self.results_button.isEnabled():
            return
        self.result_card.setVisible(bool(visible))
        self.results_button.setText("Hide Results" if visible else "View Results")
        self.results_button.setIcon(engineering_icon("minus" if visible else "results", 19))
        if visible:
            QTimer.singleShot(0, lambda: self.workspace_scroll.ensureWidgetVisible(self.result_card, 0, 20))
        else:
            QTimer.singleShot(0, lambda: self.workspace_scroll.ensureWidgetVisible(self.input_card, 0, 20))

    def set_bearing_preview(self, bearing: BearingModel) -> None:
        """Refresh result-only widgets while preserving the visible input editor."""
        self.bearing = bearing
        headers = [
            "RPM",
            "Kxx\n(N/m)",
            "Kxy\n(N/m)",
            "Kyx\n(N/m)",
            "Kyy\n(N/m)",
            "Cxx\n(N·s/m)",
            "Cxy\n(N·s/m)",
            "Cyx\n(N·s/m)",
            "Cyy\n(N·s/m)",
        ]
        self.kc_table.clear()
        self.kc_table.setRowCount(len(bearing.coefficients))
        self.kc_table.setColumnCount(len(headers))
        self.kc_table.setHorizontalHeaderLabels(headers)
        configure_table(self.kc_table, row_height=30)
        self.kc_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, coeff in enumerate(bearing.coefficients):
            values = [
                f"{coeff.rpm:g}",
                f"{coeff.kxx:.2e}",
                f"{coeff.kxy:.2e}",
                f"{coeff.kyx:.2e}",
                f"{coeff.kyy:.2e}",
                f"{coeff.cxx:.2e}",
                f"{coeff.cxy:.2e}",
                f"{coeff.cyx:.2e}",
                f"{coeff.cyy:.2e}",
            ]
            for col, value in enumerate(values):
                self.kc_table.setItem(row, col, item(value))
        if bearing.coefficients:
            rated = self.project.engineering.operating_cases[0].rated_speed_rpm
            self.nominal_index = min(
                range(len(bearing.coefficients)),
                key=lambda i: abs(bearing.coefficients[i].rpm - rated),
            )
            self.kc_table.selectRow(self.nominal_index)
            self.kc_table.item(self.nominal_index, 0).setToolTip(
                f"Nearest solved station to rated {rated:g} rpm"
            )
        self.kc_table.resizeColumnsToContents()
        self.coefficient_chart.bearing = bearing
        self.coefficient_chart.update()
        self.chart_card.setVisible(True)
        self.set_results_available(True)

    def set_thd_result(self, result) -> None:
        self.thd_result = result
        rated = self.project.engineering.operating_cases[0].rated_speed_rpm
        for tab in self.result_tabs.values():
            tab.set_result(result, rated)
        self.input_summary.setText(
            f"Preview for {self.bearing.name}: {result.source_model} → {result.application_class} · "
            f"ROSS {result.metadata['ross_api_contract']} · {len(result.coefficients)} solved stations · "
            f"lubricant: {result.metadata['lubricant']}. Apply is required to commit this station."
        )
        self.set_results_available(True)

    def set_thrust_result(self, result) -> None:
        """Render the axial contract without mapping Kzz/Czz into lateral columns."""
        self.thd_result = result
        rated = self.project.engineering.operating_cases[0].rated_speed_rpm
        for tab in self.result_tabs.values():
            tab.set_result(result, rated)

        headers = ["RPM", "Kzz\n(N/m)", "Czz\n(N·s/m)"]
        self.kc_table.clear()
        self.kc_table.setRowCount(len(result.axial_coefficients))
        self.kc_table.setColumnCount(len(headers))
        self.kc_table.setHorizontalHeaderLabels(headers)
        configure_table(self.kc_table, row_height=30)
        self.kc_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, coeff in enumerate(result.axial_coefficients):
            values = [f"{coeff.rpm:g}", f"{coeff.kzz:.6e}", f"{coeff.czz:.6e}"]
            for col, value in enumerate(values):
                self.kc_table.setItem(row, col, item(value))
        if result.axial_coefficients:
            self.nominal_index = min(
                range(len(result.axial_coefficients)),
                key=lambda i: abs(result.axial_coefficients[i].rpm - rated),
            )
            self.kc_table.selectRow(self.nominal_index)
            self.kc_table.item(self.nominal_index, 0).setToolTip(
                f"Nearest solved axial station to rated {rated:g} rpm"
            )
        self.kc_table.resizeColumnsToContents()
        self.chart_card.setVisible(False)
        self.input_summary.setText(
            f"Preview for {self.bearing.name}: ThrustPad → BearingElement (axial-only) · "
            f"ROSS {result.metadata['ross_api_contract']} · {len(result.axial_coefficients)} solved Kzz/Czz station(s) · "
            f"axial load: {result.metadata['axial_load_n']:.6g} N · lubricant: {result.metadata['lubricant']}. "
            "The radial bearing remains separate after Apply."
        )
        self.set_results_available(True)

    def _kc_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)
        headers = [
            "RPM",
            "Kxx\n(N/m)",
            "Kxy\n(N/m)",
            "Kyx\n(N/m)",
            "Kyy\n(N/m)",
            "Cxx\n(N·s/m)",
            "Cxy\n(N·s/m)",
            "Cyx\n(N·s/m)",
            "Cyy\n(N·s/m)",
        ]
        table = QTableWidget(len(self.bearing.coefficients), len(headers))
        table.setHorizontalHeaderLabels(headers)
        configure_table(table, row_height=30)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, coeff in enumerate(self.bearing.coefficients):
            values = [
                f"{coeff.rpm:,}",
                f"{coeff.kxx:.2e}",
                f"{coeff.kxy:.2e}",
                f"{coeff.kyx:.2e}",
                f"{coeff.kyy:.2e}",
                f"{coeff.cxx:.2e}",
                f"{coeff.cxy:.2e}",
                f"{coeff.cyx:.2e}",
                f"{coeff.cyy:.2e}",
            ]
            for col, value in enumerate(values):
                table.setItem(row, col, item(value))
        if self.bearing.coefficients:
            rated = self.project.engineering.operating_cases[0].rated_speed_rpm
            self.nominal_index = min(
                range(len(self.bearing.coefficients)),
                key=lambda i: abs(self.bearing.coefficients[i].rpm - rated),
            )
            table.selectRow(self.nominal_index)
            table.item(self.nominal_index, 0).setToolTip(f"Nearest solved station to rated {rated:g} rpm")
        self.kc_table = table
        table.resizeColumnsToContents()
        layout.addWidget(table, 3)

        chart_card = Card()
        self.chart_card = chart_card
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(10, 8, 10, 8)
        top = QHBoxLayout()
        title = QLabel("Stiffness and Damping Coefficients")
        title.setObjectName("subHeader")
        top.addWidget(title)
        top.addStretch(1)
        combo = QComboBox()
        combo.addItems(["Stiffness (K)", "Damping (C)"])
        top.addWidget(combo)
        chart_layout.addLayout(top)
        self.coefficient_chart = BearingCoefficientChart(self.bearing)
        combo.currentIndexChanged.connect(self.coefficient_chart.set_coefficient_kind)
        chart_layout.addWidget(self.coefficient_chart, 1)
        layout.addWidget(chart_card, 2)
        return page

    def _bearing_info_card(self) -> QWidget:
        card = SectionCard("Selected Bearing Station")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(9)
        support = "Grounded / rigid" if self.station is None or not self.station.support_names else ", ".join(self.station.support_names)
        ross_node = "—" if self.station is None or self.station.ross_node is None else str(self.station.ross_node)
        radial = "—"
        axial = "None"
        if self.inventory is not None:
            anchor = self.inventory.radial_anchor
            radial = f"#{anchor.element_index + 1} {anchor.source_model} → {anchor.ross_class}"
            if self.inventory.axial_auxiliaries:
                axial = "; ".join(
                    f"#{element.element_index + 1} {element.source_model} → {element.ross_class}"
                    for element in self.inventory.axial_auxiliaries
                )
        rows = [
            ("Station Index", str(self.bearing_index + 1)),
            ("Bearing Name", self.bearing.name),
            ("Current Model", self.bearing.bearing_type),
            ("ROSS Class", self.bearing.ross_class),
            ("Node Position", self.bearing.node_position),
            ("ROSS Node", ross_node),
            ("Support", support),
            ("Radial Element", radial),
            ("Axial Elements", axial),
        ]
        for row, (key, value) in enumerate(rows):
            label = QLabel(key)
            label.setObjectName("muted")
            grid.addWidget(label, row, 0)
            field = QLabel(value)
            field.setWordWrap(True)
            grid.addWidget(field, row, 1)
        grid.setColumnStretch(1, 1)
        card.root.addLayout(grid)
        return card

    def _actions_card(self) -> QWidget:
        card = SectionCard("Transaction")
        self.adapter_state_label = QLabel()
        self.adapter_state_label.setObjectName("muted")
        self.adapter_state_label.setWordWrap(True)
        card.root.addWidget(self.adapter_state_label)

        self.calculate_button = QPushButton("Calculate Bearing")
        self.calculate_button.setObjectName("primaryButton")
        self.calculate_button.setIcon(engineering_icon("gear", 20, "#ffffff"))
        self.calculate_button.clicked.connect(
            lambda: self.status_message.emit("Bearing calculation requested through application service")
        )
        card.root.addWidget(self.calculate_button)

        self.apply_button = QPushButton("Apply to Rotor")
        self.apply_button.setObjectName("successButton")
        self.apply_button.setIcon(engineering_icon("check", 20))
        card.root.addWidget(self.apply_button)

        self.results_button = QPushButton("View Results")
        self.results_button.setObjectName("softButton")
        self.results_button.setIcon(engineering_icon("results", 19))
        self.results_button.setEnabled(False)
        self.results_button.clicked.connect(
            lambda: self.set_results_visible(not self.result_card.isVisible())
        )
        card.root.addWidget(self.results_button)

        export = QPushButton("Export Curves")
        export.setObjectName("softButton")
        export.setIcon(engineering_icon("export", 20))
        export.setEnabled(False)
        export.setToolTip("Curve export is not implemented.")
        card.root.addWidget(export)
        return card
