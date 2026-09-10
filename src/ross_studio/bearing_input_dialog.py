from __future__ import annotations

from math import pi
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .domain import BearingCoefficientPoint, BearingSpec, RotorProject


class BearingInputDialog(QDialog):
    """Class-specific SI-safe input editor for validated General bearing models."""

    KC_HEADERS = ("RPM", "Kxx", "Kxy", "Kyx", "Kyy", "Cxx", "Cxy", "Cyx", "Cyy")

    def __init__(self, project: RotorProject, bearing_index: int, ross_class: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.bearing_index = int(bearing_index)
        self.spec: BearingSpec = project.bearings[self.bearing_index]
        self.ross_class = ross_class
        self.fields: dict[str, QDoubleSpinBox | QSpinBox] = {}
        self.kc_table: QTableWidget | None = None

        self.setWindowTitle(f"Bearing Studio · {ross_class}")
        self.setMinimumWidth(440 if ross_class != "BearingElement" else 980)
        root = QVBoxLayout(self)
        intro = QLabel(self._description())
        intro.setWordWrap(True)
        root.addWidget(intro)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        root.addLayout(form)
        self._build_fields(form)
        if ross_class == "BearingElement":
            root.addLayout(self._kc_toolbar())
            self.kc_table = self._build_kc_table()
            root.addWidget(self.kc_table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _description(self) -> str:
        if self.ross_class == "BallBearingElement":
            return "ROSS analytical rolling-ball model. Geometry and load are converted to SI only at the service boundary."
        if self.ross_class == "RollerBearingElement":
            return "ROSS analytical rolling-roller model. The calculated K/C is previewed before it is applied to the rotor."
        if self.ross_class == "CylindricalBearing":
            return "ROSS hydrodynamic cylindrical-bearing model. For a flexible support, ROSS Studio applies its calculated K/C table through a BearingElement n_link adapter."
        return "Direct BearingElement K/C table. Speeds must be strictly increasing; coefficients remain in N/m and N·s/m and are applied without fitting."

    @staticmethod
    def _double(value: float, *, minimum: float = 0.0, maximum: float = 1.0e12, decimals: int = 6) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setDecimals(decimals)
        box.setRange(minimum, maximum)
        box.setValue(float(value))
        box.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        return box

    @staticmethod
    def _integer(value: int, *, minimum: int = 1, maximum: int = 10000) -> QSpinBox:
        box = QSpinBox()
        box.setRange(minimum, maximum)
        box.setValue(int(value))
        return box

    def _add(self, form: QFormLayout, key: str, label: str, widget: QDoubleSpinBox | QSpinBox) -> None:
        self.fields[key] = widget
        form.addRow(label, widget)

    def _meta(self, key: str, default: Any) -> Any:
        return self.spec.metadata.get(key, default)

    def _build_fields(self, form: QFormLayout) -> None:
        if self.ross_class == "BallBearingElement":
            self._add(form, "n_balls", "Number of balls", self._integer(int(self._meta("n_balls", 8)), minimum=3, maximum=100))
            self._add(form, "d_balls_mm", "Ball diameter (mm)", self._double(float(self._meta("d_balls_m", 0.03)) * 1000.0, maximum=1000.0, decimals=3))
            self._add(form, "static_load_n", "Static load (N)", self._double(float(self._meta("static_load_n", 500.0)), maximum=1e9, decimals=2))
            self._add(form, "contact_angle_deg", "Contact angle (deg)", self._double(float(self._meta("contact_angle_rad", 0.0)) * 180.0 / pi, maximum=89.9, decimals=3))
            return

        if self.ross_class == "RollerBearingElement":
            self._add(form, "n_rollers", "Number of rollers", self._integer(int(self._meta("n_rollers", 8)), minimum=3, maximum=100))
            self._add(form, "roller_length_mm", "Roller length (mm)", self._double(float(self._meta("roller_length_m", 0.03)) * 1000.0, maximum=2000.0, decimals=3))
            self._add(form, "static_load_n", "Static load (N)", self._double(float(self._meta("static_load_n", 500.0)), maximum=1e9, decimals=2))
            self._add(form, "contact_angle_deg", "Contact angle (deg)", self._double(float(self._meta("contact_angle_rad", 0.0)) * 180.0 / pi, maximum=89.9, decimals=3))
            return

        if self.ross_class == "CylindricalBearing":
            case = self.project.operating_cases[0]
            stored_speed = self.spec.metadata.get("speed_rpm")
            low_default = max(1.0, float(case.speed_min_rpm))
            high_default = max(low_default, float(case.speed_max_rpm))
            if isinstance(stored_speed, list) and stored_speed:
                low_default = max(1.0, float(stored_speed[0]))
                high_default = float(stored_speed[-1])
            self._add(form, "speed_min_rpm", "Minimum speed (rpm)", self._double(low_default, minimum=0.1, maximum=300000.0, decimals=1))
            self._add(form, "speed_max_rpm", "Maximum speed (rpm)", self._double(high_default, minimum=0.1, maximum=300000.0, decimals=1))
            self._add(form, "speed_points", "Speed stations", self._integer(11, minimum=2, maximum=1001))
            self._add(form, "weight_n", "Bearing load / weight (N)", self._double(float(self._meta("weight_n", 525.0)), maximum=1e9, decimals=2))
            self._add(form, "bearing_length_mm", "Bearing length (mm)", self._double(float(self._meta("bearing_length_m", 0.03)) * 1000.0, maximum=5000.0, decimals=3))
            self._add(form, "journal_diameter_mm", "Journal diameter (mm)", self._double(float(self._meta("journal_diameter_m", 0.10)) * 1000.0, maximum=5000.0, decimals=3))
            self._add(form, "radial_clearance_mm", "Radial clearance (mm)", self._double(float(self._meta("radial_clearance_m", 1.0e-4)) * 1000.0, maximum=100.0, decimals=6))
            self._add(form, "oil_viscosity_pa_s", "Dynamic viscosity (Pa·s)", self._double(float(self._meta("oil_viscosity_pa_s", 0.10)), maximum=1000.0, decimals=6))

    def _kc_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel("Speed-dependent K/C coefficients"))
        row.addStretch(1)
        add = QPushButton("Add Row")
        add.clicked.connect(self._add_kc_row)
        delete = QPushButton("Delete Row")
        delete.clicked.connect(self._delete_kc_row)
        row.addWidget(add)
        row.addWidget(delete)
        return row

    @staticmethod
    def _table_item(value: float) -> QTableWidgetItem:
        item = QTableWidgetItem(f"{float(value):.12g}")
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    def _build_kc_table(self) -> QTableWidget:
        points = list(self.spec.coefficients)
        if not points:
            case = self.project.operating_cases[0]
            rpm = float(case.rated_speed_rpm)
            points = [BearingCoefficientPoint(
                rpm=rpm,
                kxx=self.spec.kxx,
                kxy=self.spec.kxy,
                kyx=self.spec.kyx,
                kyy=self.spec.kyy or self.spec.kxx,
                cxx=self.spec.cxx,
                cxy=self.spec.cxy,
                cyx=self.spec.cyx,
                cyy=self.spec.cyy or self.spec.cxx,
            )]
        table = QTableWidget(len(points), len(self.KC_HEADERS))
        table.setHorizontalHeaderLabels(list(self.KC_HEADERS))
        table.setMinimumHeight(300)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for r, point in enumerate(points):
            values = (point.rpm, point.kxx, point.kxy, point.kyx, point.kyy, point.cxx, point.cxy, point.cyx, point.cyy)
            for c, value in enumerate(values):
                table.setItem(r, c, self._table_item(value))
        if points:
            table.selectRow(0)
        return table

    def _add_kc_row(self) -> None:
        if self.kc_table is None:
            return
        table = self.kc_table
        row = table.rowCount()
        table.insertRow(row)
        previous_rpm = 0.0
        if row:
            try:
                previous_rpm = float(table.item(row - 1, 0).text())
            except Exception:
                previous_rpm = 0.0
        defaults = (previous_rpm + 100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        for col, value in enumerate(defaults):
            table.setItem(row, col, self._table_item(value))
        table.selectRow(row)

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
            for col in range(len(self.KC_HEADERS)):
                cell = self.kc_table.item(row, col)
                if cell is None or not cell.text().strip():
                    raise ValueError(f"K/C table row {row + 1}, column {self.KC_HEADERS[col]} is empty.")
                numbers.append(float(cell.text().strip().replace(",", ".")))
            points.append(BearingCoefficientPoint(*numbers))
        return points

    def values(self) -> dict[str, Any]:
        raw = {key: widget.value() for key, widget in self.fields.items()}
        if self.ross_class == "BearingElement":
            return {
                "coefficients": self._kc_values(),
                "rated_speed_rpm": float(self.project.operating_cases[0].rated_speed_rpm),
            }
        if self.ross_class == "BallBearingElement":
            return {
                "n_balls": int(raw["n_balls"]),
                "d_balls_m": float(raw["d_balls_mm"]) / 1000.0,
                "static_load_n": float(raw["static_load_n"]),
                "contact_angle_rad": float(raw["contact_angle_deg"]) * pi / 180.0,
            }
        if self.ross_class == "RollerBearingElement":
            return {
                "n_rollers": int(raw["n_rollers"]),
                "roller_length_m": float(raw["roller_length_mm"]) / 1000.0,
                "static_load_n": float(raw["static_load_n"]),
                "contact_angle_rad": float(raw["contact_angle_deg"]) * pi / 180.0,
            }
        if self.ross_class == "CylindricalBearing":
            return {
                "speed_min_rpm": float(raw["speed_min_rpm"]),
                "speed_max_rpm": float(raw["speed_max_rpm"]),
                "speed_points": int(raw["speed_points"]),
                "weight_n": float(raw["weight_n"]),
                "bearing_length_m": float(raw["bearing_length_mm"]) / 1000.0,
                "journal_diameter_m": float(raw["journal_diameter_mm"]) / 1000.0,
                "radial_clearance_m": float(raw["radial_clearance_mm"]) / 1000.0,
                "oil_viscosity_pa_s": float(raw["oil_viscosity_pa_s"]),
            }
        return {}


__all__ = ["BearingInputDialog"]
