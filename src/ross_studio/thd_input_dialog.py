from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QLineEdit, QScrollArea, QVBoxLayout, QWidget,
)

from .bearing_input_dialog import BearingInputDialog
from .domain import RotorProject


# Engineering-domain values: conversion happens in THDBearingStudioService.
# Keys are also the documented service arguments; no presentation-only controls.
COMMON = [
    ("speed_rpm", "Speed stations (rpm; comma separated)", [900., 1800., 3600.]),
    ("journal_diameter_mm", "Journal diameter (mm)", 400.),
    ("radial_clearance_um", "Radial clearance (µm)", 195.),
    ("lubricant", "Lubricant (ROSS oil identifier)", "ISOVG32"),
]
PLAIN = [
    ("axial_length_mm", "Axial length (mm)", 263.144),
    ("n_pad", "Pads / lands (count)", 2),
    ("pad_arc_deg", "Pad arc (deg)", 176.),
    ("preload", "Preload (dimensionless)", 0.),
    ("geometry", "Geometry", ("circular", "lobe", "elliptical")),
    ("reference_temperature_c", "Reference oil temperature (°C)", 50.),
    ("fxs_load_n", "Fx (N)", 0.), ("fys_load_n", "Fy (N)", -112814.91),
    ("groove_factor", "Groove factor per pad (dimensionless; comma separated)", [0.52, 0.48]),
    ("sommerfeld_type", "Sommerfeld type (1 or 2)", ("1", "2")),
    ("initial_eccentricity_ratio", "Initial eccentricity ratio (dimensionless)", 0.1),
    ("initial_attitude_angle_deg", "Initial attitude angle (deg)", -5.729577951308233),
    ("method", "Coefficient method", ("perturbation", "lund")),
    ("operating_type", "Oil operating condition", ("flooded", "starvation")),
    ("oil_flow_l_min", "Oil flow (L/min)", 37.86),
    ("oil_supply_pressure_bar", "Oil supply pressure (bar)", 0.),
    ("elements_circumferential", "Circumferential elements (count)", 11),
    ("elements_axial", "Axial elements (count)", 3),
]
TILTING = [
    ("pad_thickness_mm", "Pad thickness (mm)", 12.7),
    ("n_pads", "Pads (count)", 5),
    ("pivot_angles_deg", "Pivot angle per pad (deg; comma separated)", [18., 90., 162., 234., 306.]),
    ("pad_arc_deg", "Pad arc (deg)", 60.),
    ("pad_axial_length_mm", "Pad axial length (mm)", 50.8),
    ("preload", "Preload (dimensionless)", 0.5),
    ("offset", "Pivot offset (fraction of pad arc)", 0.5),
    ("oil_supply_temperature_c", "Oil supply temperature (°C)", 40.),
    ("fxs_load_n", "Fx (N; used for determine_eccentricity)", 884.05),
    ("fys_load_n", "Fy (N; used for determine_eccentricity)", -2670.4),
    ("equilibrium_type", "Equilibrium", ("match_eccentricity", "determine_eccentricity")),
    ("eccentricity_ratio", "Eccentricity ratio (dimensionless; match_eccentricity)", 0.35),
    ("attitude_angle_deg", "Attitude angle (deg)", 287.5),
    ("thermal_type", "Thermal model", ("adiabatic", "full")),
    ("nx", "Circumferential volumes nx (count)", 10),
    ("nz", "Axial volumes nz (count)", 10),
]
SFD = [
    ("axial_length_mm", "Axial length (mm)", 22.86),
    ("eccentricity_ratio", "Eccentricity ratio (dimensionless)", 0.5),
    ("geometry", "Geometry", ("groove", "end_seals", "groove-end_seals")),
    ("cavitation", "Cavitation", True),
]
FIELDS = {"PlainJournal": PLAIN, "TiltingPad": TILTING, "SqueezeFilmDamper": SFD}


class THDBearingInputDialog(QDialog):
    """Scrollable, class-specific engineering input with explicit physical units."""

    def __init__(self, project: RotorProject, bearing_index: int, ross_class: str, parent=None):
        super().__init__(parent)
        self.ross_class = ross_class
        self.fields: dict[str, QWidget] = {}
        self.setWindowTitle(f"Bearing Studio · {ross_class}")
        self.resize(700, 760)
        root = QVBoxLayout(self)
        intro = QLabel("Review every input before calculating. Defaults are example bearing data, not a calibration of the imported rotor. Enter explicit, increasing speed stations in rpm.")
        intro.setWordWrap(True)
        root.addWidget(intro)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        holder = QWidget()
        form = QFormLayout(holder)
        meta = project.bearings[bearing_index].metadata
        stored = meta.get("engineering_input", {}) if meta.get("source_model") == ross_class else {}
        overrides = {
            "TiltingPad": {"journal_diameter_mm": 101.6, "radial_clearance_um": 74.9},
            "SqueezeFilmDamper": {"journal_diameter_mm": 129.54, "radial_clearance_um": 76.2},
        }.get(ross_class, {})
        for key, label, default in COMMON + FIELDS[ross_class]:
            value = stored.get(key, overrides.get(key, default))
            if isinstance(default, tuple):
                widget = QComboBox()
                widget.addItems(default)
                widget.setCurrentText(str(stored.get(key, "2" if key == "sommerfeld_type" else default[0])))
            elif isinstance(default, bool):
                widget = QCheckBox()
                widget.setChecked(bool(value))
            elif isinstance(default, list):
                widget = QLineEdit(", ".join(f"{v:.15g}" for v in value))
            elif isinstance(default, str):
                widget = QLineEdit(str(value))
            elif isinstance(default, int):
                widget = BearingInputDialog._integer(value, maximum=10000)
            else:
                widget = BearingInputDialog._double(value, minimum=-1e12, decimals=12)
            widget.setObjectName(key)
            widget.setToolTip(f"THDBearingStudioService input: {key}")
            self.fields[key] = widget
            form.addRow(label, widget)
        scroll.setWidget(holder)
        root.addWidget(scroll)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        root.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept_valid)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def values(self) -> dict[str, Any]:
        values = {}
        for key, widget in self.fields.items():
            if isinstance(widget, QComboBox):
                values[key] = widget.currentText()
            elif isinstance(widget, QCheckBox):
                values[key] = widget.isChecked()
            elif isinstance(widget, QLineEdit):
                values[key] = ([float(v.strip()) for v in widget.text().split(",")]
                               if key in {"speed_rpm", "groove_factor", "pivot_angles_deg"}
                               else widget.text().strip())
            else:
                values[key] = widget.value()
        return values

    def _accept_valid(self):
        try:
            self.values()
        except ValueError:
            self.error_label.setText("Enter numeric vectors separated by commas; use a decimal point.")
            return
        self.accept()
