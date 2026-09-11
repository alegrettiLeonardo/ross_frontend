from __future__ import annotations

from math import pi
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .bearing_schema import MODEL_BY_CLASS, BearingFieldSpec, BearingModelSpec
from .domain import RotorProject


class EngineeringDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, value: float = 0.0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDecimals(12)
        self.setRange(-1.0e15, 1.0e15)
        self.setValue(float(value))
        self.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.setKeyboardTracking(False)

    def textFromValue(self, value: float) -> str:  # noqa: N802
        return f"{float(value):.12g}"


class PadDataDialog(QDialog):
    """Compact per-pad editor used by the TiltingPad model."""

    HEADERS = (
        "Pivot angle (deg)",
        "Pad arc (deg)",
        "Axial length (mm)",
        "Preload",
        "Offset",
        "Initial angle (deg)",
    )

    def __init__(self, rows: list[list[float]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tilting Pad · Edit Pad Data")
        self.resize(820, 420)
        root = QVBoxLayout(self)
        note = QLabel(
            "One row per physical pad. Values remain in engineering units here and are converted only at the ROSS service boundary."
        )
        note.setWordWrap(True)
        root.addWidget(note)
        self.table = QTableWidget(len(rows), len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.verticalHeader().setVisible(True)
        for r, values in enumerate(rows):
            self.table.setVerticalHeaderItem(r, QTableWidgetItem(str(r + 1)))
            for c, value in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(f"{float(value):.12g}"))
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)
        self.error_label = QLabel()
        self.error_label.setObjectName("validationError")
        self.error_label.hide()
        root.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _validate_accept(self) -> None:
        try:
            self.rows()
        except ValueError as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self.accept()

    def rows(self) -> list[list[float]]:
        rows: list[list[float]] = []
        for r in range(self.table.rowCount()):
            row: list[float] = []
            for c, header in enumerate(self.HEADERS):
                item = self.table.item(r, c)
                if item is None or not item.text().strip():
                    raise ValueError(f"Pad {r + 1}: {header} is required.")
                try:
                    row.append(float(item.text().replace(",", ".")))
                except ValueError as exc:
                    raise ValueError(f"Pad {r + 1}: {header} must be numeric; received {item.text()!r}.") from exc
            if not (0.0 <= row[3] < 1.0):
                raise ValueError(f"Pad {r + 1}: preload must satisfy 0 <= preload < 1; received {row[3]:g}.")
            if not (0.0 <= row[4] <= 1.0):
                raise ValueError(f"Pad {r + 1}: offset must be in [0, 1]; received {row[4]:g}.")
            rows.append(row)
        return rows


class AdvancedFieldsDialog(QDialog):
    def __init__(self, specs: tuple[BearingFieldSpec, ...], values: dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bearing Studio · Advanced Solver Options")
        self.fields: dict[str, QWidget] = {}
        root = QVBoxLayout(self)
        form = QFormLayout()
        for spec in specs:
            widget: QWidget
            value = values.get(spec.key, 0.0)
            if spec.widget_type == "int":
                box = QSpinBox(); box.setRange(1, 1_000_000); box.setValue(int(value or 1)); widget = box
            else:
                widget = EngineeringDoubleSpinBox(float(value or 0.0))
            self.fields[spec.key] = widget
            form.addRow(f"{spec.label}{f' ({spec.unit})' if spec.unit else ''}", widget)
        root.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def values(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, widget in self.fields.items():
            result[key] = int(widget.value()) if isinstance(widget, QSpinBox) else float(widget.value())
        return result


class BearingInputWorkspace(QWidget):
    """Schema-driven input surface with the three approved golden panels."""

    changed = Signal()

    VECTOR_KEYS = {"speed_rpm", "groove_factor"}

    def __init__(self, project: RotorProject, bearing_index: int, ross_class: str, parent=None) -> None:
        super().__init__(parent)
        self.project = project
        self.bearing_index = int(bearing_index)
        self.ross_class = ross_class
        self.spec: BearingModelSpec = MODEL_BY_CLASS[ross_class]
        self.fields: dict[str, QWidget] = {}
        self._rows: dict[str, QWidget] = {}
        self._advanced_values: dict[str, Any] = {}
        self._pad_rows: list[list[float]] = []
        self._building = False

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        self._root = root
        self.set_model(project, bearing_index, ross_class)

    def set_model(self, project: RotorProject, bearing_index: int, ross_class: str) -> None:
        self.project = project
        self.bearing_index = int(bearing_index)
        self.ross_class = ross_class
        self.spec = MODEL_BY_CLASS[ross_class]
        self._building = True
        while self._root.count():
            item = self._root.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.fields.clear(); self._rows.clear()
        defaults = self._initial_values()
        self._advanced_values = {field.key: defaults.get(field.key, self._default_for(field)) for field in self.spec.fields if field.advanced}
        if ross_class == "TiltingPad":
            self._pad_rows = self._initial_pad_rows(defaults)

        for section in ("Geometry", "Operation", "Lubrication / Model"):
            panel = QFrame()
            panel.setObjectName("bearingInputSection")
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(12, 8, 12, 10)
            panel_layout.setSpacing(4)
            title = QLabel(section)
            title.setObjectName("bearingInputSectionTitle")
            panel_layout.addWidget(title)
            form = QFormLayout()
            form.setContentsMargins(0, 4, 0, 0)
            form.setHorizontalSpacing(10)
            form.setVerticalSpacing(6)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            panel_layout.addLayout(form)
            panel_layout.addStretch(1)
            for field in self.spec.fields:
                if field.section != section or field.advanced:
                    continue
                row = self._row_widget(field, defaults.get(field.key, self._default_for(field)))
                form.addRow(field.label, row)
            if section == "Lubrication / Model" and any(field.advanced for field in self.spec.fields):
                advanced = QPushButton("Advanced...")
                advanced.setObjectName("outlineButton")
                advanced.clicked.connect(self._edit_advanced)
                panel_layout.insertWidget(panel_layout.count() - 1, advanced)
                self.advanced_button = advanced
            self._root.addWidget(panel, 1)
        self._building = False
        self._sync_conditions()

    def _row_widget(self, spec: BearingFieldSpec, value: Any) -> QWidget:
        row = QWidget()
        row.setObjectName(f"bearingFieldRow_{spec.key}")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        if spec.widget_type == "choice":
            widget = QComboBox(); widget.addItems(list(spec.choices)); widget.setCurrentText(str(value))
            widget.currentTextChanged.connect(self._field_changed)
        elif spec.widget_type == "bool":
            widget = QCheckBox(); widget.setChecked(bool(value)); widget.toggled.connect(self._field_changed)
        elif spec.widget_type == "int":
            widget = QSpinBox(); widget.setRange(1, 1_000_000); widget.setValue(int(value)); widget.valueChanged.connect(self._field_changed)
        elif spec.widget_type == "vector":
            widget = QLineEdit(", ".join(f"{float(v):.12g}" for v in value)); widget.editingFinished.connect(self._field_changed)
        elif spec.widget_type == "text":
            widget = QLineEdit(str(value)); widget.editingFinished.connect(self._field_changed)
        elif spec.widget_type == "pad_table":
            widget = QPushButton("Edit Pad Data...")
            widget.setObjectName("outlineButton")
            widget.clicked.connect(self._edit_pad_data)
        else:
            widget = EngineeringDoubleSpinBox(float(value)); widget.valueChanged.connect(self._field_changed)
        widget.setObjectName(spec.key)
        widget.setToolTip(spec.tooltip or f"ROSS {self.ross_class}: {spec.key}")
        self.fields[spec.key] = widget
        self._rows[spec.key] = row
        layout.addWidget(widget, 1)
        if spec.unit:
            unit = QLabel(spec.unit); unit.setObjectName("muted"); unit.setMinimumWidth(36); layout.addWidget(unit)
        return row

    def _default_for(self, field: BearingFieldSpec) -> Any:
        if field.widget_type == "choice": return field.choices[0] if field.choices else ""
        if field.widget_type == "bool": return False
        if field.widget_type == "int": return 1
        if field.widget_type == "vector": return [900.0, 1800.0, 3600.0]
        if field.widget_type == "text": return "ISOVG32"
        return 0.0

    def _initial_values(self) -> dict[str, Any]:
        bearing = self.project.bearings[self.bearing_index]
        metadata = dict(bearing.metadata)
        stored = metadata.get("engineering_input", {}) if metadata.get("source_model") == self.ross_class else {}
        case = self.project.operating_cases[0]
        speeds = sorted({float(case.speed_min_rpm), float(case.rated_speed_rpm), float(case.speed_max_rpm)})
        speeds = [v for v in speeds if v > 0.0]
        defaults: dict[str, dict[str, Any]] = {
            "BallBearingElement": {"n_balls": 8, "d_balls_mm": 30.0, "contact_angle_deg": 0.0, "static_load_n": 500.0},
            "RollerBearingElement": {"n_rollers": 8, "roller_length_mm": 30.0, "contact_angle_deg": 0.0, "static_load_n": 500.0},
            "CylindricalBearing": {"bearing_length_mm": 30.0, "journal_diameter_mm": 100.0, "radial_clearance_mm": 0.1, "speed_min_rpm": max(1.0, float(case.speed_min_rpm)), "speed_max_rpm": float(case.speed_max_rpm), "speed_points": 11, "weight_n": 525.0, "oil_viscosity_pa_s": 0.1},
            "PlainJournal": {"axial_length_mm": 263.144, "journal_diameter_mm": 400.0, "radial_clearance_um": 195.0, "elements_circumferential": 11, "elements_axial": 3, "n_pad": 2, "pad_arc_deg": 176.0, "preload": 0.0, "geometry": "circular", "speed_rpm": speeds, "fxs_load_n": 0.0, "fys_load_n": -112814.91, "reference_temperature_c": 50.0, "operating_type": "flooded", "oil_supply_pressure_bar": 0.0, "lubricant": "ISOVG32", "sommerfeld_type": "2", "method": "perturbation", "initial_eccentricity_ratio": 0.1, "initial_attitude_angle_deg": -5.7295779513, "groove_factor": [0.52, 0.48], "oil_flow_l_min": 37.86},
            "TiltingPad": {"journal_diameter_mm": 101.6, "radial_clearance_um": 74.9, "pad_thickness_mm": 12.7, "n_pads": 5, "speed_rpm": speeds, "fxs_load_n": 884.05, "fys_load_n": -2670.4, "oil_supply_temperature_c": 40.0, "lubricant": "ISOVG32", "nx": 10, "nz": 10, "thermal_type": "adiabatic", "equilibrium_type": "match_eccentricity", "eccentricity_ratio": 0.35, "attitude_angle_deg": 287.5, "xtol": 1e-8, "ftol": 1e-8, "maxiter": 200, "nr_pad": 10, "k_pad": 50.0, "h_edge": 100.0, "hot_oil_carry_over": 0.5, "journal_temperature": 60.0, "max_jtemp_iter": 30, "jtemp_error": 0.1, "max_inlet_iterations": 30, "inlet_temperature_tolerance": 0.1},
            "ThrustPad": {"pad_inner_radius_mm": 1150.0, "pad_outer_radius_mm": 1725.0, "pad_pivot_radius_mm": 1442.5, "pad_arc_deg": 26.0, "angular_pivot_position_deg": 15.0, "n_pad": 12, "n_theta": 10, "n_radial": 10, "speed_rpm": speeds, "axial_load_n": 13.320e6, "oil_supply_temperature_c": 40.0, "equilibrium_position_mode": "calculate", "radial_inclination_angle_mrad": -0.275, "circumferential_inclination_angle_mrad": -0.017, "initial_film_thickness_um": 200.0, "lubricant": "ISOVG68"},
            "SqueezeFilmDamper": {"axial_length_mm": 22.86, "journal_diameter_mm": 129.54, "radial_clearance_um": 76.2, "geometry": "groove", "speed_rpm": speeds, "eccentricity_ratio": 0.5, "lubricant": "ISOVG32", "cavitation": True},
            "MagneticBearingElement": {"g0": 0.001, "i0": 2.0, "ag": 0.001, "nw": 100, "alpha": 45.0, "kp_pid": 0.0, "ki_pid": 0.0, "kd_pid": 0.0, "k_sense": 1.0, "k_amp": 1.0, "sensors_axis_rotation": 0.0},
        }
        values = dict(defaults.get(self.ross_class, {}))
        values.update(stored)
        if self.ross_class == "BallBearingElement":
            values.update(n_balls=int(metadata.get("n_balls", values["n_balls"])), d_balls_mm=float(metadata.get("d_balls_m", values["d_balls_mm"] / 1000.0)) * 1000.0, static_load_n=float(metadata.get("static_load_n", values["static_load_n"])), contact_angle_deg=float(metadata.get("contact_angle_rad", values["contact_angle_deg"] * pi / 180.0)) * 180.0 / pi)
        elif self.ross_class == "RollerBearingElement":
            values.update(n_rollers=int(metadata.get("n_rollers", values["n_rollers"])), roller_length_mm=float(metadata.get("roller_length_m", values["roller_length_mm"] / 1000.0)) * 1000.0, static_load_n=float(metadata.get("static_load_n", values["static_load_n"])), contact_angle_deg=float(metadata.get("contact_angle_rad", values["contact_angle_deg"] * pi / 180.0)) * 180.0 / pi)
        return values

    def _initial_pad_rows(self, values: dict[str, Any]) -> list[list[float]]:
        n = int(values.get("n_pads", 5))
        pivots = values.get("pivot_angles_deg", [18.0, 90.0, 162.0, 234.0, 306.0])
        arcs = values.get("pad_arc_deg", 60.0)
        lengths = values.get("pad_axial_length_mm", 50.8)
        preloads = values.get("preload", 0.5)
        offsets = values.get("offset", 0.5)
        initials = values.get("initial_pads_angles_deg", [0.0] * n)
        def vector(value, default):
            if isinstance(value, (list, tuple)):
                return list(value)
            return [value if value is not None else default] * n
        pivots = vector(pivots, 0.0); arcs = vector(arcs, 60.0); lengths = vector(lengths, 50.8)
        preloads = vector(preloads, 0.5); offsets = vector(offsets, 0.5); initials = vector(initials, 0.0)
        while len(pivots) < n: pivots.append((18.0 + 72.0 * len(pivots)) % 360.0)
        rows = []
        for i in range(n):
            rows.append([float(pivots[i]), float(arcs[min(i, len(arcs)-1)]), float(lengths[min(i, len(lengths)-1)]), float(preloads[min(i, len(preloads)-1)]), float(offsets[min(i, len(offsets)-1)]), float(initials[min(i, len(initials)-1)])])
        return rows

    def _field_changed(self, *_args) -> None:
        if self._building:
            return
        if self.ross_class == "TiltingPad" and "n_pads" in self.fields:
            n = int(self.fields["n_pads"].value())
            if len(self._pad_rows) != n:
                existing = list(self._pad_rows)
                self._pad_rows = (existing[:n] + [[(18.0 + 72.0 * i) % 360.0, 60.0, 50.8, 0.5, 0.5, 0.0] for i in range(len(existing), n)])
        self._sync_conditions()
        self.changed.emit()

    def _sync_conditions(self) -> None:
        values = self.raw_values(strict=False)
        for field in self.spec.fields:
            if field.advanced or field.key not in self._rows:
                continue
            visible = True
            if field.visible_if:
                visible = all(values.get(k) == expected for k, expected in field.visible_if.items())
            self._rows[field.key].setVisible(visible)

    def _edit_pad_data(self) -> None:
        dialog = PadDataDialog(self._pad_rows, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._pad_rows = dialog.rows()
            self.changed.emit()

    def _edit_advanced(self) -> None:
        values = self.raw_values(strict=False)
        specs = tuple(field for field in self.spec.fields if field.advanced and (not field.visible_if or all(values.get(k) == v for k, v in field.visible_if.items())))
        dialog = AdvancedFieldsDialog(specs, self._advanced_values, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._advanced_values.update(dialog.values())
            self.changed.emit()

    def raw_values(self, *, strict: bool = True) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for field in self.spec.fields:
            if field.advanced or field.widget_type == "pad_table":
                continue
            widget = self.fields.get(field.key)
            if widget is None:
                continue
            if isinstance(widget, QComboBox): values[field.key] = widget.currentText()
            elif isinstance(widget, QCheckBox): values[field.key] = widget.isChecked()
            elif isinstance(widget, QSpinBox): values[field.key] = int(widget.value())
            elif isinstance(widget, QDoubleSpinBox): values[field.key] = float(widget.value())
            elif isinstance(widget, QLineEdit):
                text = widget.text().strip()
                if field.widget_type == "vector":
                    try:
                        values[field.key] = [float(v.strip()) for v in text.split(",") if v.strip()]
                    except ValueError:
                        if strict: raise ValueError(f"{field.label}: expected comma-separated numeric values; received {text!r}.")
                        values[field.key] = []
                else: values[field.key] = text
        values.update(self._advanced_values)
        if self.ross_class == "TiltingPad":
            values.update(
                pivot_angles_deg=[r[0] for r in self._pad_rows],
                pad_arc_deg=[r[1] for r in self._pad_rows],
                pad_axial_length_mm=[r[2] for r in self._pad_rows],
                preload=[r[3] for r in self._pad_rows],
                offset=[r[4] for r in self._pad_rows],
                initial_pads_angles_deg=[r[5] for r in self._pad_rows],
            )
        return values

    @staticmethod
    def _validate_speed_vector(values: dict[str, Any]) -> None:
        if "speed_rpm" not in values:
            return
        speeds = [float(v) for v in values["speed_rpm"]]
        if not speeds or any(v <= 0 for v in speeds) or any(b <= a for a, b in zip(speeds, speeds[1:])):
            raise ValueError(f"Speed stations: received {speeds!r}; expected positive strictly increasing RPM values. Correct the speed grid.")

    def values(self) -> dict[str, Any]:
        raw = self.raw_values(strict=True)
        self._validate_speed_vector(raw)
        if self.ross_class == "BallBearingElement":
            return {"n_balls": int(raw["n_balls"]), "d_balls_m": float(raw["d_balls_mm"]) / 1000.0, "static_load_n": float(raw["static_load_n"]), "contact_angle_rad": float(raw["contact_angle_deg"]) * pi / 180.0}
        if self.ross_class == "RollerBearingElement":
            return {"n_rollers": int(raw["n_rollers"]), "roller_length_m": float(raw["roller_length_mm"]) / 1000.0, "static_load_n": float(raw["static_load_n"]), "contact_angle_rad": float(raw["contact_angle_deg"]) * pi / 180.0}
        if self.ross_class == "CylindricalBearing":
            if float(raw["speed_max_rpm"]) <= float(raw["speed_min_rpm"]):
                raise ValueError(f"Maximum speed: received {raw['speed_max_rpm']:g} RPM; expected greater than minimum {raw['speed_min_rpm']:g} RPM. Correct the operating range.")
            return {"speed_min_rpm": float(raw["speed_min_rpm"]), "speed_max_rpm": float(raw["speed_max_rpm"]), "speed_points": int(raw["speed_points"]), "weight_n": float(raw["weight_n"]), "bearing_length_m": float(raw["bearing_length_mm"]) / 1000.0, "journal_diameter_m": float(raw["journal_diameter_mm"]) / 1000.0, "radial_clearance_m": float(raw["radial_clearance_mm"]) / 1000.0, "oil_viscosity_pa_s": float(raw["oil_viscosity_pa_s"])}
        return raw


__all__ = ["BearingInputWorkspace", "EngineeringDoubleSpinBox", "PadDataDialog", "AdvancedFieldsDialog"]
