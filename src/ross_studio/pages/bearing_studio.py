from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ..domain import AdapterStatus, BearingGroup
from ..icons import engineering_icon
from ..models import BearingModel, ProjectModel
from ..services import BearingCatalogService
from ..widgets import BearingCoefficientChart, Card, ProjectInfoCard, SectionCard, configure_table, item


class BearingStudioPage(QWidget):
    status_message = Signal(str)

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
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.bearing = bearing
        self.catalog = catalog or BearingCatalogService()
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
        title = QLabel("Bearing Studio")
        title.setObjectName("cardHeader")
        header_row.addWidget(title)
        self.crumb = QLabel()
        self.crumb.setObjectName("muted")
        header_row.addWidget(self.crumb)
        header_row.addStretch(1)
        page_layout.addLayout(header_row)

        group_row = QHBoxLayout()
        group_label = QLabel("Bearing Group")
        group_label.setObjectName("subHeader")
        group_row.addWidget(group_label)
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

        input_row = QHBoxLayout()
        input_row.setSpacing(10)
        input_row.addWidget(self._geometry_box(), 1)
        input_row.addWidget(self._operation_box(), 1)
        input_row.addWidget(self._lubrication_box(), 1)
        input_row.addWidget(self._operating_point_box(), 1)
        page_layout.addLayout(input_row)
        center.addWidget(page_card, 5)

        result_card = Card()
        result_layout = QVBoxLayout(result_card)
        result_layout.setContentsMargins(10, 0, 10, 10)
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        result_layout.addWidget(tabs, 1)
        tabs.addTab(self._kc_tab(), "K & C Coefficients")
        for name in ("Pressure", "Temperature", "Film Thickness", "Journal Position", "Convergence"):
            holder = QWidget()
            layout = QVBoxLayout(holder)
            label = QLabel(f"{name} field visualization")
            label.setObjectName("muted")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
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

    def set_group(self, group: str, *, announce: bool = True) -> None:
        selected_group = BearingGroup(group)
        self.current_group = selected_group
        self.group_badge.setText(selected_group.value)
        self.crumb.setText(f"Model  /  Bearings  /  {selected_group.value}  /  {self.bearing.name}")

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
        self.apply_button.setEnabled(status == AdapterStatus.VALIDATED)

        if group == BearingGroup.GENERAL:
            self.editor_note.setText(
                "General / Parametric classes use direct or analytical engineering inputs. "
                "The imported OP-W60 BearingElement K/C table is preserved without recomputation."
            )
        elif group == BearingGroup.THD:
            self.editor_note.setText(
                "THD classes remain visible for model definition, but execution is disabled until "
                "their geometry, lubricant, thermal and discretization adapters are scientifically qualified."
            )
        else:
            self.editor_note.setText(
                "AMB execution is intentionally blocked until actuator, sensor and controller definitions "
                "exist in the ROSS Studio domain."
            )

        if announce:
            if status == AdapterStatus.VALIDATED:
                self.status_message.emit(f"{title}: validated ROSS Studio adapter")
            else:
                detail = f" {reason}" if reason else ""
                self.status_message.emit(f"{title}: {status.value}.{detail}")

    def _spin(self, value: float, decimals: int = 2) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setDecimals(decimals)
        widget.setRange(-1e12, 1e12)
        widget.setValue(value)
        widget.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        return widget

    def _geometry_box(self) -> QWidget:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        title = QLabel("Geometry")
        title.setObjectName("subHeader")
        layout.addWidget(title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(7)
        rows = [
            ("Shaft Diameter (D)", self._spin(self.bearing.shaft_diameter_mm, 0), "mm"),
            ("Pad Length (L)", self._spin(self.bearing.pad_length_mm, 0), "mm"),
            ("Radial Clearance (c)", self._spin(self.bearing.radial_clearance_mm, 2), "mm"),
            ("Pad Arc (α)", self._spin(self.bearing.pad_arc_deg, 0), "deg"),
            ("Preload", self._spin(self.bearing.preload, 2), "-"),
        ]
        pads = QSpinBox()
        pads.setRange(1, 20)
        pads.setValue(self.bearing.number_of_pads)
        rows.append(("Number of Pads", pads, ""))
        for row, (text, widget, unit) in enumerate(rows):
            grid.addWidget(QLabel(text), row, 0)
            grid.addWidget(widget, row, 1)
            unit_label = QLabel(unit)
            unit_label.setObjectName("muted")
            grid.addWidget(unit_label, row, 2)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch(1)
        return card

    def _operation_box(self) -> QWidget:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        title = QLabel("Operation")
        title.setObjectName("subHeader")
        layout.addWidget(title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(7)
        grid.addWidget(QLabel("Speed Range"), 0, 0)
        speed_row = QHBoxLayout()
        start = QSpinBox()
        start.setRange(0, 999999)
        start.setValue(self.bearing.speed_min_rpm)
        end = QSpinBox()
        end.setRange(0, 999999)
        end.setValue(self.bearing.speed_max_rpm)
        speed_row.addWidget(start)
        speed_row.addWidget(QLabel("to"))
        speed_row.addWidget(end)
        box = QWidget()
        box.setLayout(speed_row)
        grid.addWidget(box, 0, 1, 1, 2)
        grid.addWidget(QLabel("rpm"), 0, 3)
        rows = [
            ("Load X (Fx)", self._spin(self.bearing.load_x_n, 0), "N"),
            ("Load Y (Fy)", self._spin(self.bearing.load_y_n, 0), "N"),
            ("Oil Inlet\nTemperature", self._spin(self.bearing.oil_inlet_temperature_c, 0), "°C"),
            ("Supply Pressure", self._spin(self.bearing.supply_pressure_bar, 1), "bar"),
        ]
        for row, (text, widget, unit) in enumerate(rows, 1):
            grid.addWidget(QLabel(text), row, 0)
            grid.addWidget(widget, row, 1, 1, 2)
            grid.addWidget(QLabel(unit), row, 3)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch(1)
        return card

    def _lubrication_box(self) -> QWidget:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        title = QLabel("Lubrication / Model")
        title.setObjectName("subHeader")
        layout.addWidget(title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(10)
        data = [
            ("Lubricant Grade", ["ISO VG 32", "ISO VG 46", "ISO VG 68"], self.bearing.lubricant_grade),
            ("Thermal Model", ["Energy Equation", "Isothermal"], self.bearing.thermal_model),
            ("Viscosity Model", ["Roelands", "Walther"], self.bearing.viscosity_model),
            ("Mesh /\nDiscretization", ["Medium (60 × 30)", "Coarse (30 × 15)", "Fine (120 × 60)"], self.bearing.mesh),
        ]
        for row, (label, options, current) in enumerate(data):
            grid.addWidget(QLabel(label), row, 0)
            combo = QComboBox()
            combo.addItems(options)
            combo.setCurrentText(current)
            grid.addWidget(combo, row, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch(1)
        return card

    def _operating_point_box(self) -> QWidget:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QLabel(f"Operating Point (at {self.bearing.operating_rpm:,} rpm)")
        header.setObjectName("subHeader")
        header.setContentsMargins(12, 10, 0, 6)
        layout.addWidget(header)
        table = QTableWidget(6, 3)
        table.setHorizontalHeaderLabels(["", "", ""])
        table.horizontalHeader().hide()
        configure_table(table, row_height=30)
        table.verticalHeader().hide()
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        rows = [
            ("Eccentricity Ratio (ε)", f"{self.bearing.eccentricity_ratio:.3f}", "-"),
            ("Attitude Angle (φ)", f"{self.bearing.attitude_angle_deg:.1f}", "deg"),
            ("Minimum Film Thickness (hmin)", f"{self.bearing.min_film_thickness_mm:.3f}", "mm"),
            ("Power Loss", f"{self.bearing.power_loss_kw:.2f}", "kW"),
            ("Flow Rate", f"{self.bearing.flow_rate_l_min:.1f}", "L/min"),
            ("Max Temperature (Pad)", f"{self.bearing.max_temperature_c:.1f}", "°C"),
        ]
        for row, values in enumerate(rows):
            for col, value in enumerate(values):
                table.setItem(row, col, item(value, center=col > 0))
        table.setColumnWidth(0, 165)
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table, 1)
        return card

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
            table.selectRow(min(4, len(self.bearing.coefficients) - 1))
        table.resizeColumnsToContents()
        layout.addWidget(table, 3)
        chart_card = Card()
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
        chart_layout.addWidget(BearingCoefficientChart(self.bearing), 1)
        layout.addWidget(chart_card, 2)
        return page

    def _bearing_info_card(self) -> QWidget:
        card = SectionCard("Bearing Information")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(9)
        rows = [
            ("Bearing Name", self.bearing.name),
            ("Bearing Type", self.bearing.bearing_type),
            ("ROSS Class", self.bearing.ross_class),
            ("Node Position", self.bearing.node_position),
            ("Connected Shaft", self.bearing.connected_shaft),
            ("Number of Pads", str(self.bearing.number_of_pads)),
            ("Preload", f"{self.bearing.preload:.2f}"),
            ("Clearance", f"{self.bearing.radial_clearance_mm:.2f} mm"),
            ("Pad Arc", f"{self.bearing.pad_arc_deg:.0f} deg"),
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
        card = SectionCard("Quick Actions")
        self.adapter_state_label = QLabel()
        self.adapter_state_label.setObjectName("muted")
        self.adapter_state_label.setWordWrap(True)
        card.root.addWidget(self.adapter_state_label)

        self.calculate_button = QPushButton("Calculate Bearing")
        self.calculate_button.setObjectName("primaryButton")
        self.calculate_button.setIcon(engineering_icon("gear", 20, "#ffffff"))
        self.calculate_button.clicked.connect(lambda: self.status_message.emit("Bearing calculation requested through application service"))
        card.root.addWidget(self.calculate_button)

        self.apply_button = QPushButton("Apply to Rotor")
        self.apply_button.setObjectName("successButton")
        self.apply_button.setIcon(engineering_icon("check", 20))
        card.root.addWidget(self.apply_button)

        export = QPushButton("Export Curves")
        export.setObjectName("softButton")
        export.setIcon(engineering_icon("export", 20))
        card.root.addWidget(export)
        return card
