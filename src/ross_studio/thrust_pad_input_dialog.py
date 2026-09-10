from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .bearing_input_dialog import BearingInputDialog
from .domain import RotorProject


FIELDS = [
    ("speed_rpm", "Speed stations (rpm; comma separated)", [90.0]),
    ("pad_inner_radius_mm", "Pad inner radius (mm)", 1150.0),
    ("pad_outer_radius_mm", "Pad outer radius (mm)", 1725.0),
    ("pad_pivot_radius_mm", "Pad pivot radius (mm)", 1442.5),
    ("pad_arc_deg", "Pad arc (deg)", 26.0),
    ("angular_pivot_position_deg", "Angular pivot position (deg)", 15.0),
    ("oil_supply_temperature_c", "Oil supply temperature (°C)", 40.0),
    ("lubricant", "Lubricant (ROSS oil identifier)", "ISOVG68"),
    ("n_pad", "Pads (count)", 12),
    ("n_theta", "Circumferential volumes (count)", 10),
    ("n_radial", "Radial volumes (count)", 10),
    ("equilibrium_position_mode", "Equilibrium position mode", ("calculate", "imposed")),
    ("axial_load_n", "Axial load (N)", 13.320e6),
    ("radial_inclination_angle_mrad", "Initial radial inclination (mrad)", -0.275),
    ("circumferential_inclination_angle_mrad", "Initial circumferential inclination (mrad)", -0.017),
    ("initial_film_thickness_um", "Initial pivot film thickness (µm)", 200.0),
    ("tolerance_force_moment_n", "Force / moment convergence tolerance (N)", 0.1),
    ("residual_force_moment_n", "Initial residual force / moment (N)", 50.0),
]


class ThrustPadInputDialog(QDialog):
    """Engineering input editor for the independent axial ROSS ThrustPad model."""

    def __init__(self, project: RotorProject, bearing_index: int, ross_class: str, parent=None):
        super().__init__(parent)
        if ross_class != "ThrustPad":
            raise ValueError(f"ThrustPadInputDialog cannot edit {ross_class}.")
        self.ross_class = ross_class
        self.fields: dict[str, QWidget] = {}
        self.setWindowTitle("Bearing Studio · Axial ThrustPad")
        self.resize(720, 780)

        root = QVBoxLayout(self)
        anchor = project.bearings[bearing_index]
        intro = QLabel(
            f"This model is axial. The selected radial bearing '{anchor.name}' at {anchor.position_mm:g} mm is used only as a placement anchor. "
            "Calculate solves native ROSS 2.3 THD fields and Kzz/Czz; Apply adds a separate axial BearingElement and never overwrites radial K/C."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        holder = QWidget()
        form = QFormLayout(holder)

        stored = {}
        for bearing in project.bearings:
            if (
                bearing.metadata.get("source_model") == "ThrustPad"
                and abs(float(bearing.position_mm) - float(anchor.position_mm)) <= 1e-9
            ):
                stored = dict(bearing.metadata.get("engineering_input", {}))
                break

        for key, label, default in FIELDS:
            value = stored.get(key, default)
            if isinstance(default, tuple):
                widget = QComboBox()
                widget.addItems(default)
                widget.setCurrentText(str(value))
            elif isinstance(default, list):
                widget = QLineEdit(", ".join(f"{float(v):.15g}" for v in value))
            elif isinstance(default, str):
                widget = QLineEdit(str(value))
            elif isinstance(default, int):
                widget = BearingInputDialog._integer(value, maximum=10000)
            else:
                widget = BearingInputDialog._double(value, minimum=-1e15, decimals=12)
            widget.setObjectName(key)
            widget.setToolTip(f"ThrustPadStudioService input: {key}")
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
        values: dict[str, Any] = {}
        for key, widget in self.fields.items():
            if isinstance(widget, QComboBox):
                values[key] = widget.currentText()
            elif isinstance(widget, QLineEdit):
                values[key] = (
                    [float(v.strip()) for v in widget.text().split(",")]
                    if key == "speed_rpm"
                    else widget.text().strip()
                )
            else:
                values[key] = widget.value()
        return values

    def _accept_valid(self) -> None:
        try:
            values = self.values()
            speeds = values["speed_rpm"]
            if not speeds or any(v <= 0 for v in speeds) or any(b <= a for a, b in zip(speeds, speeds[1:])):
                raise ValueError("Speeds must be positive and strictly increasing.")
        except ValueError as exc:
            self.error_label.setText(str(exc) or "Enter numeric values using a decimal point.")
            return
        self.accept()


__all__ = ["ThrustPadInputDialog"]
