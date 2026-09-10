from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from .domain import ProbeSpec, ShaftSection, SupportSpec


def _double(value: float, *, minimum: float = -1.0e15, maximum: float = 1.0e15, decimals: int = 6) -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setDecimals(decimals)
    widget.setRange(minimum, maximum)
    widget.setValue(float(value))
    widget.setKeyboardTracking(False)
    return widget


def _buttons(dialog: QDialog) -> QDialogButtonBox:
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


class ShaftSectionEditorDialog(QDialog):
    """Edit local shaft geometry without silently remapping downstream stations."""

    def __init__(self, section: ShaftSection, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit Shaft Section {section.section}")
        root = QVBoxLayout(self)
        note = QLabel(
            "Section length is intentionally read-only in this gate. OD/ID and FE mesh are qualified through a strict ROSS preview before commit."
        )
        note.setWordWrap(True)
        root.addWidget(note)
        form = QFormLayout()
        self.length = _double(section.length_mm, minimum=1.0e-9)
        self.length.setEnabled(False)
        self.od_left = _double(section.od_left_mm, minimum=1.0e-9)
        self.od_right = _double(section.odr_mm, minimum=1.0e-9)
        self.id_left = _double(section.id_left_mm, minimum=0.0)
        self.id_right = _double(section.idr_mm, minimum=0.0)
        self.fe_elements = QSpinBox()
        self.fe_elements.setRange(1, 1000)
        self.fe_elements.setValue(section.fe_elements)
        self.material = QLineEdit(section.material)
        self.material.setReadOnly(True)
        form.addRow("Length (mm)", self.length)
        form.addRow("OD left (mm)", self.od_left)
        form.addRow("OD right (mm)", self.od_right)
        form.addRow("ID left (mm)", self.id_left)
        form.addRow("ID right (mm)", self.id_right)
        form.addRow("Base FE elements", self.fe_elements)
        form.addRow("Material", self.material)
        root.addLayout(form)
        root.addWidget(_buttons(self))

    def changes(self) -> dict[str, object]:
        return {
            "od_left_mm": self.od_left.value(),
            "od_right_mm": self.od_right.value(),
            "id_left_mm": self.id_left.value(),
            "id_right_mm": self.id_right.value(),
            "fe_elements": self.fe_elements.value(),
        }


class SupportEditorDialog(QDialog):
    def __init__(self, support: SupportSpec, bearing_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit Support — {support.name}")
        root = QVBoxLayout(self)
        note = QLabel(
            f"Bearing ownership is fixed to {bearing_name}. Support mass and the complete lateral K/C matrix are reassembled in strict ROSS before commit."
        )
        note.setWordWrap(True)
        root.addWidget(note)
        form = QFormLayout()
        self.mass = _double(support.mass_kg, minimum=0.0)
        self.kxx = _double(support.kxx)
        self.kyy = _double(support.kyy)
        self.kxy = _double(support.kxy)
        self.kyx = _double(support.kyx)
        self.cxx = _double(support.cxx)
        self.cyy = _double(support.cyy)
        self.cxy = _double(support.cxy)
        self.cyx = _double(support.cyx)
        form.addRow("Mass (kg)", self.mass)
        form.addRow("Kxx (N/m)", self.kxx)
        form.addRow("Kyy (N/m)", self.kyy)
        form.addRow("Kxy (N/m)", self.kxy)
        form.addRow("Kyx (N/m)", self.kyx)
        form.addRow("Cxx (N·s/m)", self.cxx)
        form.addRow("Cyy (N·s/m)", self.cyy)
        form.addRow("Cxy (N·s/m)", self.cxy)
        form.addRow("Cyx (N·s/m)", self.cyx)
        root.addLayout(form)
        root.addWidget(_buttons(self))

    def changes(self) -> dict[str, object]:
        return {
            "mass_kg": self.mass.value(),
            "kxx": self.kxx.value(),
            "kyy": self.kyy.value(),
            "kxy": self.kxy.value(),
            "kyx": self.kyx.value(),
            "cxx": self.cxx.value(),
            "cyy": self.cyy.value(),
            "cxy": self.cxy.value(),
            "cyx": self.cyx.value(),
        }


class ProbeEditorDialog(QDialog):
    def __init__(self, probe: ProbeSpec | None = None, *, total_length_mm: float, parent=None) -> None:
        super().__init__(parent)
        source = probe or ProbeSpec("Probe", 0.5 * total_length_mm, 1, 0.0)
        self.setWindowTitle("Add Probe" if probe is None else f"Edit Probe — {probe.name}")
        root = QVBoxLayout(self)
        note = QLabel(
            "Probe position is a physical station. Apply is accepted only if exact FE-node insertion and strict ROSS assembly both succeed."
        )
        note.setWordWrap(True)
        root.addWidget(note)
        form = QFormLayout()
        self.name = QLineEdit(source.name)
        self.position = _double(source.position_mm, minimum=0.0, maximum=max(total_length_mm, 0.0))
        self.coordinate = QSpinBox()
        self.coordinate.setRange(1, 2)
        self.coordinate.setValue(source.coordinate)
        self.orientation = _double(source.orientation_deg, minimum=-360.0, maximum=360.0)
        form.addRow("Name", self.name)
        form.addRow("Position (mm)", self.position)
        form.addRow("Coordinate", self.coordinate)
        form.addRow("Orientation (deg)", self.orientation)
        root.addLayout(form)
        root.addWidget(_buttons(self))

    def record(self) -> ProbeSpec:
        return ProbeSpec(
            name=self.name.text().strip(),
            position_mm=self.position.value(),
            coordinate=self.coordinate.value(),
            orientation_deg=self.orientation.value(),
        )

    def changes(self) -> dict[str, object]:
        record = self.record()
        return {
            "name": record.name,
            "position_mm": record.position_mm,
            "coordinate": record.coordinate,
            "orientation_deg": record.orientation_deg,
        }


__all__ = ["ShaftSectionEditorDialog", "SupportEditorDialog", "ProbeEditorDialog"]
