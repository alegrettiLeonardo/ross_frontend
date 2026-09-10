from __future__ import annotations

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ..bearing_workspace import BearingStation, BearingWorkspaceService
from ..domain import AdapterStatus, BearingGroup
from ..icons import engineering_icon
from ..models import BearingModel, ProjectModel
from ..services import BearingCatalogService
from ..widgets import BearingCoefficientChart, Card, ProjectInfoCard, SectionCard, configure_table, item
from .thd_results import THDResultTab


class BearingStudioPage(QWidget):
    """Bearing Studio 2.0 workspace.

    A physical bearing station is selected first. The ROSS calculation family/class
    is selected independently after that. The application service owns the
    Calculate -> Preview -> Apply transaction and receives the explicit station
    index emitted by this page.
    """

    status_message = Signal(str)
    bearing_selected = Signal(int)

    TYPE_DEFINITIONS = (
        ("kc", "Coefficient K/C", "wave", "BearingElement", BearingGroup.GENERAL),
        ("ball", "Ball Bearing", "bearing", "BallBearingElement", BearingGroup.GENERAL),
        ("roller", "Roller Bearing", "bearing", "RollerBearingElement", BearingGroup.GENERAL),
        ("cyl", "Cylindrical", "bearing", "CylindricalBearing", BearingGroup.GENERAL),
        ("plain", "Plain Journal", "seal", "PlainJournal", BearingGroup.THD),
        ("tilting", "Tilting Pad", "disk", "TiltingPad", BearingGroup.THD),
        ("thrust", "Thrust Pad", "disk", "ThrustPad", BearingGroup.THD),
        ("sfd", "Squeeze Film Damper", "seal", "SqueezeFilmDamper", BearingGroup.THD),
        ("amb", "Active Magnetic Bearing", "wave", "MagneticBearingElement", BearingGroup.AMB),
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
        self.stations: tuple[BearingStation, ...] = (
            self.workspace.stations(project.engineering) if project.engineering is not None else ()
        )
        self.station = next((row for row in self.stations if row.index == self.bearing_index), None)
        try:
            self.current_group = BearingGroup(bearing.group)
        except ValueError:
            self.current_group = BearingGroup.GENERAL

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(10)
        root.addLayout(center, 1)

        page_card = Card()
        page_layout = QVBoxLayout(page_card)
        page_layout.setContentsMargins(14, 10, 14, 10)
        page_layout.setSpacing(8)

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

        group_row = QHBoxLayout()
        group_label = QLabel("Model Family")
        group_label.setObjectName("subHeader")
        group_row.addWidget(group_label)
        self.group_selector = QComboBox()
        self.group_selector.setObjectName("bearingFamilySelector")
        for group in (BearingGroup.GENERAL, BearingGroup.THD, BearingGroup.AMB):
            self.group_selector.addItem(group.value, group.value)
        self.group_selector.currentTextChanged.connect(self.set_group)
        group_row.addWidget(self.group_selector)
        self.group_badge = QLabel()
        self.group_badge.setObjectName("muted")
        group_row.addWidget(self.group_badge)
        group_row.addStretch(1)
        page_layout.addLayout(group_row)

        lab = QLabel("Bearing Class")
        lab.setObjectName("subHeader")
        page_layout.addWidget(lab)
        types = QHBoxLayout()
        types.setSpacing(8)
        self.type_buttons: dict[str, QPushButton] = {}
        self.type_metadata: dict[str, tuple[str, str, BearingGroup]] = {}
        for key, text, icon, ross_class, group in self.TYPE_DEFINITIONS:
            button = QPushButton(text)
            button.setObjectName("bearingType")
            button.setCheckable(True)
            button.setIcon(engineering_icon(icon, 30))
            button.setIconSize(QSize(30, 30))
            button.clicked.connect(lambda checked=False, k=key: self._select_type(k))
            self.type_buttons[key] = button
            self.type_metadata[key] = (text, ross_class, group)
            types.addWidget(button, 1)
        page_layout.addLayout(types)

        self.editor_note = QLabel()
        self.editor_note.setObjectName("muted")
        self.editor_note.setWordWrap(True)
        page_layout.addWidget(self.editor_note)

        self.input_summary = QLabel(
            "Select the physical bearing station, then the ROSS model. Calculate Bearing is preview-only; "
            "Apply to Rotor commits only the selected station."
        )
        self.input_summary.setWordWrap(True)
        page_layout.addWidget(self.input_summary)
        center.addWidget(page_card, 1)

        result_card = Card()
        result_layout = QVBoxLayout(result_card)
        result_layout.setContentsMargins(10, 0, 10, 10)
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        result_layout.addWidget(tabs, 1)
        tabs.addTab(self._kc_tab(), "K & C Coefficients")
        self.result_tabs: dict[str, THDResultTab] = {}
        self.tabs = tabs
        for name in ("Pressure", "Temperature", "Film Thickness", "Journal Position", "Convergence"):
            holder = THDResultTab(name)
            self.result_tabs[name] = holder
            tabs.addTab(holder, name)
        center.addWidget(result_card, 5)

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

        self.set_group(self.current_group.value, announce=False)

    def _bearing_combo_changed(self, row: int) -> None:
        index = self.bearing_selector.itemData(row)
        if index is None:
            return
        index = int(index)
        if index != self.bearing_index:
            self.bearing_selected.emit(index)

    def set_group(self, group: str, *, announce: bool = True) -> None:
        selected_group = BearingGroup(group)
        self.current_group = selected_group
        self.group_badge.setText(selected_group.value)
        self.crumb.setText(
            f"Model  /  Bearings  /  {self.bearing.name}  /  {selected_group.value}"
        )
        combo_index = self.group_selector.findData(selected_group.value)
        if combo_index >= 0 and combo_index != self.group_selector.currentIndex():
            self.group_selector.blockSignals(True)
            self.group_selector.setCurrentIndex(combo_index)
            self.group_selector.blockSignals(False)

        visible_keys: list[str] = []
        for key, button in self.type_buttons.items():
            _title, _ross_class, button_group = self.type_metadata[key]
            visible = button_group == selected_group
            button.setVisible(visible)
            if visible:
                visible_keys.append(key)

        preferred = next(
            (
                key
                for key in visible_keys
                if self.type_metadata[key][1] == self.bearing.ross_class
            ),
            visible_keys[0] if visible_keys else None,
        )
        if preferred is not None:
            self._select_type(preferred, announce=announce)

    def _select_type(self, key: str, *, announce: bool = True) -> None:
        for name, button in self.type_buttons.items():
            button.setChecked(name == key)
        title, ross_class, group = self.type_metadata[key]
        status, reason = self.catalog.registry.effective_status(ross_class)
        self.adapter_state_label.setText(f"{ross_class}: {status.value}")
        self.calculate_button.setEnabled(status == AdapterStatus.VALIDATED)
        self.apply_button.setEnabled(False)

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
            if status == AdapterStatus.VALIDATED:
                self.status_message.emit(f"{title}: validated adapter for {station_name}")
            else:
                detail = f" {reason}" if reason else ""
                self.status_message.emit(f"{title}: {status.value}.{detail}")

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
        card = SectionCard("Selected Bearing")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(9)
        support = "Grounded / rigid" if self.station is None or not self.station.support_names else ", ".join(self.station.support_names)
        ross_node = "—" if self.station is None or self.station.ross_node is None else str(self.station.ross_node)
        rows = [
            ("Index", str(self.bearing_index)),
            ("Bearing Name", self.bearing.name),
            ("Current Model", self.bearing.bearing_type),
            ("ROSS Class", self.bearing.ross_class),
            ("Node Position", self.bearing.node_position),
            ("ROSS Node", ross_node),
            ("Support", support),
        ]
        for row, (key, value) in enumerate(rows):
            label = QLabel(key)
            label.setObjectName("muted")
            grid.addWidget(label, row, 0)
            grid.addWidget(QLabel(value), row, 1)
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

        export = QPushButton("Export Curves")
        export.setObjectName("softButton")
        export.setIcon(engineering_icon("export", 20))
        export.setEnabled(False)
        export.setToolTip("Curve export is not implemented.")
        card.root.addWidget(export)
        return card
