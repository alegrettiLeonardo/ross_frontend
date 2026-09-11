from __future__ import annotations

from math import pi
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .domain import BearingCoefficientPoint, BearingSpec, RotorProject
from .thd_input_dialog import COMMON as THD_COMMON, FIELDS as THD_FIELDS
from .thrust_pad_input_dialog import FIELDS as THRUST_FIELDS


class EngineeringDoubleSpinBox(QDoubleSpinBox):
    """Compact engineering numeric editor without visually noisy trailing zeroes."""

    def textFromValue(self, value: float) -> str:  # noqa: N802 - Qt API
        return f"{float(value):.12g}"


class BearingInputPanel(QWidget):
    """Inline, class-specific Bearing Studio engineering input editor.

    The old modal dialogs remain available as compatibility helpers and unit-test
    fixtures, but the production workspace owns one visible editor. Clicking a
    bearing model replaces this panel in place; no hidden input dialog is required.
    Values stay in engineering units until the existing scientific service boundary.
    """

    KC_HEADERS = ("RPM", "Kxx", "Kxy", "Kyx", "Kyy", "Cxx", "Cxy", "Cyx", "Cyy")
    VECTOR_KEYS = {"speed_rpm", "groove_factor", "pivot_angles_deg"}

    def __init__(
        self,
        project: RotorProject,
        bearing_index: int,
        ross_class: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.bearing_index = int(bearing_index)
        self.ross_class = ross_class
        self.spec: BearingSpec = project.bearings[self.bearing_index]
        self.fields: dict[str, QWidget] = {}
        self.kc_table: QTableWidget | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        self.description = QLabel()
        self.description.setObjectName("bearingInputDescription")
        self.description.setWordWrap(True)
        root.addWidget(self.description)
        self.sections = QGridLayout()
        self.sections.setContentsMargins(0, 0, 0, 0)
        self.sections.setHorizontalSpacing(10)
        self.sections.setVerticalSpacing(10)
        root.addLayout(self.sections)
        self.error_label = QLabel()
        self.error_label.setObjectName("validationError")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        root.addWidget(self.error_label)
        self.set_model(project, bearing_index, ross_class)

    @staticmethod
    def _double(
        value: float,
        *,
        minimum: float = -1.0e15,
        maximum: float = 1.0e15,
    ) -> EngineeringDoubleSpinBox:
        box = EngineeringDoubleSpinBox()
        box.setDecimals(12)
        box.setRange(minimum, maximum)
        box.setValue(float(value))
        box.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        box.setKeyboardTracking(False)
        return box

    @staticmethod
    def _integer(value: int, *, minimum: int = 1, maximum: int = 10000) -> QSpinBox:
        box = QSpinBox()
        box.setRange(minimum, maximum)
        box.setValue(int(value))
        box.setKeyboardTracking(False)
        return box

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child = item.layout()
            if child is not None:
                BearingInputPanel._clear_layout(child)
            if widget is not None:
                widget.deleteLater()

    def set_model(self, project: RotorProject, bearing_index: int, ross_class: str) -> None:
        self.project = project
        self.bearing_index = int(bearing_index)
        self.ross_class = ross_class
        self.spec = project.bearings[self.bearing_index]
        self.fields.clear()
        self.kc_table = None
        self.error_label.clear()
        self.error_label.hide()
        self._clear_layout(self.sections)
        self.description.setText(self._description_text())

        if ross_class == "BearingElement":
            self._build_kc_editor()
            return

        definitions = self._definitions()
        values = self._initial_values(definitions)
        grouped: dict[str, list[tuple[str, str, Any]]] = {}
        for key, label, default in definitions:
            grouped.setdefault(self._section_for_key(key), []).append((key, label, default))

        preferred_order = ("Geometry", "Operation", "Lubrication / Model", "Numerical / Solver")
        ordered = [name for name in preferred_order if name in grouped]
        ordered.extend(name for name in grouped if name not in ordered)
        for i, name in enumerate(ordered):
            card = self._section_card(name)
            form = QFormLayout()
            form.setContentsMargins(12, 4, 12, 12)
            form.setHorizontalSpacing(12)
            form.setVerticalSpacing(8)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            for key, label, default in grouped[name]:
                widget = self._field_widget(key, default, values[key])
                widget.setObjectName(key)
                widget.setToolTip(f"{ross_class} engineering input: {key}")
                self.fields[key] = widget
                form.addRow(label, widget)
            card.layout().addLayout(form)
            self.sections.addWidget(card, i // 3, i % 3)

        for col in range(3):
            self.sections.setColumnStretch(col, 1)

    def _description_text(self) -> str:
        descriptions = {
            "BearingElement": (
                "Direct speed-dependent bearing coefficients. Edit K/C here in engineering units; "
                "Calculate is preview-only and Apply commits only the selected physical station."
            ),
            "BallBearingElement": (
                "ROSS analytical rolling-ball model. Geometry and load remain in engineering units "
                "until conversion at the qualified service boundary."
            ),
            "RollerBearingElement": (
                "ROSS analytical rolling-roller model. The calculated K/C remains a preview until Apply."
            ),
            "CylindricalBearing": (
                "ROSS cylindrical fluid-film model. Flexible support realization continues through the "
                "qualified BearingElement n_link adapter."
            ),
            "PlainJournal": (
                "Native ROSS plain-journal THD/Reynolds input. Review geometry, load, lubricant and "
                "numerical settings before calculation."
            ),
            "TiltingPad": (
                "Native ROSS tilting-pad input. Pad geometry, operating point, lubricant/thermal model "
                "and discretization are edited directly in this workspace."
            ),
            "SqueezeFilmDamper": (
                "Native ROSS squeeze-film-damper input. Geometry and cavitation settings are edited here; "
                "the solved K/C and available fields are displayed in Results below."
            ),
            "ThrustPad": (
                "Axial-only ROSS ThrustPad input. The selected radial bearing is a placement anchor only; "
                "Apply adds or updates a separate Kzz/Czz axial element."
            ),
            "MagneticBearingElement": (
                "AMB remains blocked until actuator, sensor and controller engineering-domain contracts are qualified."
            ),
        }
        return descriptions.get(self.ross_class, self.ross_class)

    def _definitions(self) -> list[tuple[str, str, Any]]:
        if self.ross_class == "BallBearingElement":
            return [
                ("n_balls", "Number of balls", 8),
                ("d_balls_mm", "Ball diameter (mm)", 30.0),
                ("static_load_n", "Static load (N)", 500.0),
                ("contact_angle_deg", "Contact angle (deg)", 0.0),
            ]
        if self.ross_class == "RollerBearingElement":
            return [
                ("n_rollers", "Number of rollers", 8),
                ("roller_length_mm", "Roller length (mm)", 30.0),
                ("static_load_n", "Static load (N)", 500.0),
                ("contact_angle_deg", "Contact angle (deg)", 0.0),
            ]
        if self.ross_class == "CylindricalBearing":
            case = self.project.operating_cases[0]
            return [
                ("speed_min_rpm", "Minimum speed (rpm)", max(1.0, float(case.speed_min_rpm))),
                ("speed_max_rpm", "Maximum speed (rpm)", max(1.0, float(case.speed_max_rpm))),
                ("speed_points", "Speed stations", 11),
                ("weight_n", "Bearing load / weight (N)", 525.0),
                ("bearing_length_mm", "Bearing length (mm)", 30.0),
                ("journal_diameter_mm", "Journal diameter (mm)", 100.0),
                ("radial_clearance_mm", "Radial clearance (mm)", 0.1),
                ("oil_viscosity_pa_s", "Dynamic viscosity (Pa·s)", 0.1),
            ]
        if self.ross_class in THD_FIELDS:
            return list(THD_COMMON + THD_FIELDS[self.ross_class])
        if self.ross_class == "ThrustPad":
            return list(THRUST_FIELDS)
        return []

    def _initial_values(self, definitions: list[tuple[str, str, Any]]) -> dict[str, Any]:
        metadata = self.spec.metadata
        if self.ross_class in THD_FIELDS:
            stored = metadata.get("engineering_input", {}) if metadata.get("source_model") == self.ross_class else {}
            overrides = {
                "TiltingPad": {"journal_diameter_mm": 101.6, "radial_clearance_um": 74.9},
                "SqueezeFilmDamper": {"journal_diameter_mm": 129.54, "radial_clearance_um": 76.2},
            }.get(self.ross_class, {})
            return {key: stored.get(key, overrides.get(key, default)) for key, _label, default in definitions}

        if self.ross_class == "ThrustPad":
            stored: dict[str, Any] = {}
            for bearing in self.project.bearings:
                if (
                    bearing.metadata.get("source_model") == "ThrustPad"
                    and abs(float(bearing.position_mm) - float(self.spec.position_mm)) <= 1e-9
                ):
                    stored = dict(bearing.metadata.get("engineering_input", {}))
                    break
            case = self.project.operating_cases[0]
            speeds = sorted({float(case.speed_min_rpm), float(case.rated_speed_rpm), float(case.speed_max_rpm)})
            speeds = [speed for speed in speeds if speed > 0.0]
            values = {}
            for key, _label, default in definitions:
                fallback = speeds if key == "speed_rpm" else default
                values[key] = stored.get(key, fallback)
            return values

        def meta(key: str, default: Any) -> Any:
            return metadata.get(key, default)

        values = {key: default for key, _label, default in definitions}
        if self.ross_class == "BallBearingElement":
            values.update(
                n_balls=int(meta("n_balls", 8)),
                d_balls_mm=float(meta("d_balls_m", 0.03)) * 1000.0,
                static_load_n=float(meta("static_load_n", 500.0)),
                contact_angle_deg=float(meta("contact_angle_rad", 0.0)) * 180.0 / pi,
            )
        elif self.ross_class == "RollerBearingElement":
            values.update(
                n_rollers=int(meta("n_rollers", 8)),
                roller_length_mm=float(meta("roller_length_m", 0.03)) * 1000.0,
                static_load_n=float(meta("static_load_n", 500.0)),
                contact_angle_deg=float(meta("contact_angle_rad", 0.0)) * 180.0 / pi,
            )
        elif self.ross_class == "CylindricalBearing":
            stored_speed = metadata.get("speed_rpm")
            if isinstance(stored_speed, list) and stored_speed:
                values["speed_min_rpm"] = max(0.1, float(stored_speed[0]))
                values["speed_max_rpm"] = max(values["speed_min_rpm"], float(stored_speed[-1]))
                values["speed_points"] = max(2, len(stored_speed))
            values.update(
                weight_n=float(meta("weight_n", 525.0)),
                bearing_length_mm=float(meta("bearing_length_m", 0.03)) * 1000.0,
                journal_diameter_mm=float(meta("journal_diameter_m", 0.10)) * 1000.0,
                radial_clearance_mm=float(meta("radial_clearance_m", 1.0e-4)) * 1000.0,
                oil_viscosity_pa_s=float(meta("oil_viscosity_pa_s", 0.10)),
            )
        return values

    @staticmethod
    def _section_for_key(key: str) -> str:
        operation = {
            "speed_rpm", "speed_min_rpm", "speed_max_rpm", "speed_points",
            "static_load_n", "weight_n", "fxs_load_n", "fys_load_n", "axial_load_n",
            "eccentricity_ratio", "initial_eccentricity_ratio", "attitude_angle_deg",
            "initial_attitude_angle_deg", "radial_inclination_angle_mrad",
            "circumferential_inclination_angle_mrad",
        }
        lubrication = {
            "lubricant", "reference_temperature_c", "oil_supply_temperature_c",
            "oil_flow_l_min", "oil_supply_pressure_bar", "oil_viscosity_pa_s",
            "operating_type", "thermal_type",
        }
        numerical = {
            "method", "sommerfeld_type", "equilibrium_type", "equilibrium_position_mode",
            "elements_circumferential", "elements_axial", "nx", "nz", "n_theta", "n_radial",
            "tolerance_force_moment_n", "residual_force_moment_n",
        }
        if key in operation:
            return "Operation"
        if key in lubrication:
            return "Lubrication / Model"
        if key in numerical:
            return "Numerical / Solver"
        return "Geometry"

    @staticmethod
    def _section_card(title: str) -> QFrame:
        card = QFrame()
        card.setObjectName("bearingInputSection")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        header = QLabel(title)
        header.setObjectName("bearingInputSectionTitle")
        layout.addWidget(header)
        return card

    def _field_widget(self, key: str, default: Any, value: Any) -> QWidget:
        if isinstance(default, tuple):
            widget = QComboBox()
            widget.addItems([str(v) for v in default])
            default_text = "2" if key == "sommerfeld_type" else str(default[0])
            widget.setCurrentText(str(value if value is not None else default_text))
            return widget
        if isinstance(default, bool):
            widget = QCheckBox("Enabled")
            widget.setChecked(bool(value))
            return widget
        if isinstance(default, list):
            if value is None:
                value = []
            return QLineEdit(", ".join(f"{float(v):.15g}" for v in value))
        if isinstance(default, str):
            return QLineEdit(str(value))
        if isinstance(default, int):
            minimum = 2 if key == "speed_points" else 1
            if key in {"n_balls", "n_rollers"}:
                minimum = 3
            return self._integer(int(value), minimum=minimum, maximum=10000)
        return self._double(float(value))

    @staticmethod
    def _editable_item(value: float) -> QTableWidgetItem:
        table_item = QTableWidgetItem(f"{float(value):.12g}")
        table_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return table_item

    def _build_kc_editor(self) -> None:
        card = self._section_card("Speed-dependent K/C input")
        layout: QVBoxLayout = card.layout()
        toolbar = QHBoxLayout()
        note = QLabel("N/m for K · N·s/m for C")
        note.setObjectName("muted")
        toolbar.addWidget(note)
        toolbar.addStretch(1)
        add = QPushButton("Add Row")
        add.setObjectName("outlineButton")
        add.clicked.connect(self._add_kc_row)
        delete = QPushButton("Delete Row")
        delete.setObjectName("outlineButton")
        delete.clicked.connect(self._delete_kc_row)
        toolbar.addWidget(add)
        toolbar.addWidget(delete)
        layout.addLayout(toolbar)

        points = list(self.spec.coefficients)
        if not points:
            case = self.project.operating_cases[0]
            rpm = float(case.rated_speed_rpm)
            points = [
                BearingCoefficientPoint(
                    rpm=rpm,
                    kxx=self.spec.kxx,
                    kxy=self.spec.kxy,
                    kyx=self.spec.kyx,
                    kyy=self.spec.kyy or self.spec.kxx,
                    cxx=self.spec.cxx,
                    cxy=self.spec.cxy,
                    cyx=self.spec.cyx,
                    cyy=self.spec.cyy or self.spec.cxx,
                )
            ]
        table = QTableWidget(len(points), len(self.KC_HEADERS))
        table.setObjectName("bearingInputKcTable")
        table.setHorizontalHeaderLabels(list(self.KC_HEADERS))
        table.setMinimumHeight(230)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        for row, point in enumerate(points):
            values = (point.rpm, point.kxx, point.kxy, point.kyx, point.kyy, point.cxx, point.cxy, point.cyx, point.cyy)
            for col, number in enumerate(values):
                table.setItem(row, col, self._editable_item(number))
        if points:
            table.selectRow(0)
        self.kc_table = table
        layout.addWidget(table)
        self.sections.addWidget(card, 0, 0, 1, 3)
        for col in range(3):
            self.sections.setColumnStretch(col, 1)

    def _add_kc_row(self) -> None:
        if self.kc_table is None:
            return
        row = self.kc_table.rowCount()
        self.kc_table.insertRow(row)
        previous_rpm = 0.0
        if row:
            try:
                previous_rpm = float(self.kc_table.item(row - 1, 0).text())
            except Exception:
                previous_rpm = 0.0
        defaults = (previous_rpm + 100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        for col, number in enumerate(defaults):
            self.kc_table.setItem(row, col, self._editable_item(number))
        self.kc_table.selectRow(row)

    def _delete_kc_row(self) -> None:
        if self.kc_table is None or self.kc_table.rowCount() <= 1:
            return
        row = self.kc_table.currentRow()
        if row < 0:
            row = self.kc_table.rowCount() - 1
        self.kc_table.removeRow(row)

    def _kc_values(self) -> list[BearingCoefficientPoint]:
        if self.kc_table is None:
            return []
        points: list[BearingCoefficientPoint] = []
        for row in range(self.kc_table.rowCount()):
            numbers: list[float] = []
            for col, header in enumerate(self.KC_HEADERS):
                cell = self.kc_table.item(row, col)
                if cell is None or not cell.text().strip():
                    raise ValueError(f"K/C row {row + 1}, column {header} is empty.")
                numbers.append(float(cell.text().strip().replace(",", ".")))
            points.append(BearingCoefficientPoint(*numbers))
        speeds = [point.rpm for point in points]
        self._validate_speeds(speeds)
        return points

    @staticmethod
    def _validate_speeds(speeds: list[float]) -> None:
        if not speeds:
            raise ValueError("At least one positive speed station is required.")
        if any(speed <= 0.0 for speed in speeds):
            raise ValueError("Speed stations must be positive.")
        if any(b <= a for a, b in zip(speeds, speeds[1:])):
            raise ValueError("Speed stations must be strictly increasing.")

    def values(self) -> dict[str, Any]:
        """Return the exact engineering-unit dictionary expected by existing services."""
        try:
            if self.ross_class == "BearingElement":
                values = {
                    "coefficients": self._kc_values(),
                    "rated_speed_rpm": float(self.project.operating_cases[0].rated_speed_rpm),
                }
                self.error_label.hide()
                return values

            raw: dict[str, Any] = {}
            for key, widget in self.fields.items():
                if isinstance(widget, QComboBox):
                    raw[key] = widget.currentText()
                elif isinstance(widget, QCheckBox):
                    raw[key] = widget.isChecked()
                elif isinstance(widget, QLineEdit):
                    text = widget.text().strip()
                    if key in self.VECTOR_KEYS:
                        raw[key] = [float(v.strip()) for v in text.split(",") if v.strip()]
                    else:
                        raw[key] = text
                elif isinstance(widget, QSpinBox):
                    raw[key] = int(widget.value())
                elif isinstance(widget, QDoubleSpinBox):
                    raw[key] = float(widget.value())
                else:
                    raise TypeError(f"Unsupported bearing input widget for {key}: {type(widget).__name__}")

            if self.ross_class == "BallBearingElement":
                values = {
                    "n_balls": int(raw["n_balls"]),
                    "d_balls_m": float(raw["d_balls_mm"]) / 1000.0,
                    "static_load_n": float(raw["static_load_n"]),
                    "contact_angle_rad": float(raw["contact_angle_deg"]) * pi / 180.0,
                }
            elif self.ross_class == "RollerBearingElement":
                values = {
                    "n_rollers": int(raw["n_rollers"]),
                    "roller_length_m": float(raw["roller_length_mm"]) / 1000.0,
                    "static_load_n": float(raw["static_load_n"]),
                    "contact_angle_rad": float(raw["contact_angle_deg"]) * pi / 180.0,
                }
            elif self.ross_class == "CylindricalBearing":
                if float(raw["speed_max_rpm"]) <= float(raw["speed_min_rpm"]):
                    raise ValueError("Maximum speed must be greater than minimum speed.")
                values = {
                    "speed_min_rpm": float(raw["speed_min_rpm"]),
                    "speed_max_rpm": float(raw["speed_max_rpm"]),
                    "speed_points": int(raw["speed_points"]),
                    "weight_n": float(raw["weight_n"]),
                    "bearing_length_m": float(raw["bearing_length_mm"]) / 1000.0,
                    "journal_diameter_m": float(raw["journal_diameter_mm"]) / 1000.0,
                    "radial_clearance_m": float(raw["radial_clearance_mm"]) / 1000.0,
                    "oil_viscosity_pa_s": float(raw["oil_viscosity_pa_s"]),
                }
            else:
                values = raw
                if "speed_rpm" in values:
                    self._validate_speeds([float(v) for v in values["speed_rpm"]])

            self.error_label.hide()
            return values
        except (TypeError, ValueError) as exc:
            self.error_label.setText(str(exc) or "Enter valid engineering input values.")
            self.error_label.show()
            raise


__all__ = ["BearingInputPanel", "EngineeringDoubleSpinBox"]
