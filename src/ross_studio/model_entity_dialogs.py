from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from .domain import (
    CouplingSpec,
    DiskSpec,
    DistributedMassSpec,
    LoadSpec,
    PointMassSpec,
    ProbeSpec,
    SealSpec,
    ShaftSection,
    SupportSpec,
)


def _double(
    value: float,
    *,
    minimum: float = -1.0e15,
    maximum: float = 1.0e15,
    decimals: int = 6,
) -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setDecimals(decimals)
    widget.setRange(minimum, maximum)
    widget.setValue(float(value))
    widget.setKeyboardTracking(False)
    return widget


def _buttons(dialog: QDialog) -> QDialogButtonBox:
    box = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


def _note(root: QVBoxLayout, text: str) -> None:
    label = QLabel(text)
    label.setWordWrap(True)
    root.addWidget(label)


class ShaftSectionEditorDialog(QDialog):
    """Edit local shaft geometry without silently remapping downstream stations."""

    def __init__(self, section: ShaftSection, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit Shaft Section {section.section}")
        root = QVBoxLayout(self)
        _note(
            root,
            "Section length is intentionally read-only in this gate. OD/ID and FE mesh "
            "are qualified through a strict ROSS preview before commit.",
        )
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
        _note(
            root,
            f"Bearing ownership is fixed to {bearing_name}. Support mass and the complete "
            "lateral K/C matrix are reassembled in strict ROSS before commit.",
        )
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
        _note(
            root,
            "Probe position is a physical station. Apply is accepted only if exact FE-node "
            "insertion and strict ROSS assembly both succeed.",
        )
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


class MassTypeDialog(QDialog):
    """Choose the first-class engineering body added in the mass workspace."""

    TYPES = (
        ("Distributed rotor mass [Massas]", "distributed_mass"),
        ("Rigid disk", "disk"),
        ("Concentrated mass [Concent]", "point_mass"),
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Disk / Rotor Mass")
        root = QVBoxLayout(self)
        _note(
            root,
            "Choose the engineering body type. The selected body is inserted at exact "
            "physical coordinates and must pass the qualified transaction before commit.",
        )
        form = QFormLayout()
        self.kind = QComboBox()
        for label, value in self.TYPES:
            self.kind.addItem(label, value)
        form.addRow("Body type", self.kind)
        root.addLayout(form)
        root.addWidget(_buttons(self))

    def selected_kind(self) -> str:
        return str(self.kind.currentData())


class DistributedMassEditorDialog(QDialog):
    def __init__(self, mass: DistributedMassSpec | None = None, *, total_length_mm: float, parent=None) -> None:
        super().__init__(parent)
        source = mass or DistributedMassSpec(
            "Distributed mass", 0.25 * total_length_mm, max(1.0, 0.10 * total_length_mm), 1.0, 100.0, 0.0
        )
        self.setWindowTitle("Add Distributed Rotor Mass" if mass is None else f"Edit Distributed Mass — {mass.name}")
        root = QVBoxLayout(self)
        _note(
            root,
            "[Massas] remains a finite hollow-cylinder engineering body. ROSS realizes it "
            "as an equivalent DiskElement at the exact center node using Id/Ip calculated "
            "from mass, OD, ID and axial length.",
        )
        form = QFormLayout()
        self.name = QLineEdit(source.name)
        self.start = _double(source.start_mm, minimum=0.0, maximum=max(total_length_mm, 0.0))
        self.length = _double(source.length_mm, minimum=1.0e-9, maximum=max(total_length_mm, 1.0e-9))
        self.mass = _double(source.mass_kg, minimum=0.0)
        self.od = _double(source.od_mm, minimum=1.0e-9)
        self.id = _double(source.id_mm, minimum=0.0)
        self.is_package = QCheckBox()
        self.is_package.setChecked(bool(source.is_package))
        self.ump_enabled = QCheckBox()
        self.ump_enabled.setChecked(bool(source.ump_enabled))
        self.ump_value = _double(source.ump_value)
        form.addRow("Name", self.name)
        form.addRow("Start (mm)", self.start)
        form.addRow("Length (mm)", self.length)
        form.addRow("Mass (kg)", self.mass)
        form.addRow("OD (mm)", self.od)
        form.addRow("ID (mm)", self.id)
        form.addRow("Rotor package", self.is_package)
        form.addRow("UMP enabled", self.ump_enabled)
        form.addRow("UMP source value", self.ump_value)
        root.addLayout(form)
        root.addWidget(_buttons(self))

    def record(self) -> DistributedMassSpec:
        return DistributedMassSpec(
            name=self.name.text().strip(),
            start_mm=self.start.value(),
            length_mm=self.length.value(),
            mass_kg=self.mass.value(),
            od_mm=self.od.value(),
            id_mm=self.id.value(),
            is_package=self.is_package.isChecked(),
            ump_enabled=self.ump_enabled.isChecked(),
            ump_value=self.ump_value.value(),
        )

    def changes(self) -> dict[str, object]:
        record = self.record()
        return {
            "name": record.name,
            "start_mm": record.start_mm,
            "length_mm": record.length_mm,
            "mass_kg": record.mass_kg,
            "od_mm": record.od_mm,
            "id_mm": record.id_mm,
            "is_package": record.is_package,
            "ump_enabled": record.ump_enabled,
            "ump_value": record.ump_value,
        }


class PointMassEditorDialog(QDialog):
    def __init__(self, mass: PointMassSpec | None = None, *, total_length_mm: float, parent=None) -> None:
        super().__init__(parent)
        source = mass or PointMassSpec("Concentrated mass [Concent]", 0.5 * total_length_mm, 1.0, 0.0, 0.0, 0.0)
        self.setWindowTitle("Add Concentrated Mass [Concent]" if mass is None else f"Edit Concentrated Mass — {mass.name}")
        root = QVBoxLayout(self)
        _note(
            root,
            "[Concent] is a shaft-station rigid body. Its mass and independent principal "
            "inertias Ix/Iy/Iz are preserved by the qualified concentrated DiskElement adapter.",
        )
        form = QFormLayout()
        self.name = QLineEdit(source.name)
        self.position = _double(source.position_mm, minimum=0.0, maximum=max(total_length_mm, 0.0))
        self.mass = _double(source.mass_kg, minimum=0.0)
        self.ix = _double(source.ix_kg_m2, minimum=0.0)
        self.iy = _double(source.iy_kg_m2, minimum=0.0)
        self.iz = _double(source.iz_kg_m2, minimum=0.0)
        form.addRow("Name", self.name)
        form.addRow("Position (mm)", self.position)
        form.addRow("Mass (kg)", self.mass)
        form.addRow("Ix (kg·m²)", self.ix)
        form.addRow("Iy / polar (kg·m²)", self.iy)
        form.addRow("Iz (kg·m²)", self.iz)
        root.addLayout(form)
        root.addWidget(_buttons(self))

    def record(self) -> PointMassSpec:
        return PointMassSpec(
            self.name.text().strip(), self.position.value(), self.mass.value(),
            self.ix.value(), self.iy.value(), self.iz.value()
        )

    def changes(self) -> dict[str, object]:
        record = self.record()
        return {
            "name": record.name,
            "position_mm": record.position_mm,
            "mass_kg": record.mass_kg,
            "ix_kg_m2": record.ix_kg_m2,
            "iy_kg_m2": record.iy_kg_m2,
            "iz_kg_m2": record.iz_kg_m2,
        }


class DiskEditorDialog(QDialog):
    def __init__(self, disk: DiskSpec | None = None, *, total_length_mm: float, parent=None) -> None:
        super().__init__(parent)
        source = disk or DiskSpec("Rigid disk", 0.5 * total_length_mm, 1.0, 0.0, 0.0)
        self.setWindowTitle("Add Rigid Disk" if disk is None else f"Edit Disk — {disk.name}")
        root = QVBoxLayout(self)
        _note(
            root,
            "The rigid disk is applied to an exact shaft node. Mass, diametral inertia Id "
            "and polar inertia Ip are sent directly to ROSS DiskElement after validation.",
        )
        form = QFormLayout()
        self.name = QLineEdit(source.name)
        self.position = _double(source.position_mm, minimum=0.0, maximum=max(total_length_mm, 0.0))
        self.mass = _double(source.mass_kg, minimum=0.0)
        self.id = _double(source.id_kg_m2, minimum=0.0)
        self.ip = _double(source.ip_kg_m2, minimum=0.0)
        form.addRow("Name", self.name)
        form.addRow("Position (mm)", self.position)
        form.addRow("Mass (kg)", self.mass)
        form.addRow("Id (kg·m²)", self.id)
        form.addRow("Ip (kg·m²)", self.ip)
        root.addLayout(form)
        root.addWidget(_buttons(self))

    def record(self) -> DiskSpec:
        return DiskSpec(self.name.text().strip(), self.position.value(), self.mass.value(), self.id.value(), self.ip.value())

    def changes(self) -> dict[str, object]:
        record = self.record()
        return {
            "name": record.name,
            "position_mm": record.position_mm,
            "mass_kg": record.mass_kg,
            "id_kg_m2": record.id_kg_m2,
            "ip_kg_m2": record.ip_kg_m2,
        }


class SealEditorDialog(QDialog):
    def __init__(self, seal: SealSpec | None = None, *, total_length_mm: float, parent=None) -> None:
        super().__init__(parent)
        source = seal or SealSpec("Seal", 0.5 * total_length_mm, 0.0, 0.0, 0.0, 0.0)
        self.setWindowTitle("Add Seal" if seal is None else f"Edit Seal — {seal.name}")
        root = QVBoxLayout(self)
        _note(
            root,
            "Seal coefficients are independent rotor-dynamic coefficients. Position is "
            "exact-node qualified and direct/cross-coupled K/C terms retain their sign.",
        )
        form = QFormLayout()
        self.name = QLineEdit(source.name)
        self.position = _double(source.position_mm, minimum=0.0, maximum=max(total_length_mm, 0.0))
        self.kxx = _double(source.kxx)
        self.kyy = _double(source.kyy)
        self.kxy = _double(source.kxy)
        self.kyx = _double(source.kyx)
        self.cxx = _double(source.cxx)
        self.cyy = _double(source.cyy)
        self.cxy = _double(source.cxy)
        self.cyx = _double(source.cyx)
        form.addRow("Name", self.name)
        form.addRow("Position (mm)", self.position)
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

    def record(self) -> SealSpec:
        return SealSpec(
            name=self.name.text().strip(), position_mm=self.position.value(),
            kxx=self.kxx.value(), kyy=self.kyy.value(), cxx=self.cxx.value(), cyy=self.cyy.value(),
            kxy=self.kxy.value(), kyx=self.kyx.value(), cxy=self.cxy.value(), cyx=self.cyx.value(),
        )

    def changes(self) -> dict[str, object]:
        record = self.record()
        return {name: getattr(record, name) for name in (
            "name", "position_mm", "kxx", "kyy", "kxy", "kyx", "cxx", "cyy", "cxy", "cyx"
        )}


class CouplingEditorDialog(QDialog):
    def __init__(self, coupling: CouplingSpec | None = None, *, total_length_mm: float, parent=None) -> None:
        super().__init__(parent)
        source = coupling or CouplingSpec("Coupling", 0.5 * total_length_mm, 0.0, 0.0, 0.0, 0.0)
        self.setWindowTitle("Add Coupling" if coupling is None else f"Edit Coupling — {coupling.name}")
        root = QVBoxLayout(self)
        _note(
            root,
            "Coupling properties are stored as a first-class engineering joint. Position "
            "is exact-node qualified. This single-station legacy contract is not silently "
            "converted into a two-node ROSS CouplingElement.",
        )
        form = QFormLayout()
        self.name = QLineEdit(source.name)
        self.position = _double(source.position_mm, minimum=0.0, maximum=max(total_length_mm, 0.0))
        self.left_mass = _double(source.left_mass_kg, minimum=0.0)
        self.right_mass = _double(source.right_mass_kg, minimum=0.0)
        self.left_ip = _double(source.left_ip_kg_m2, minimum=0.0)
        self.right_ip = _double(source.right_ip_kg_m2, minimum=0.0)
        self.kt_x = _double(source.kt_x_n_m)
        self.kt_y = _double(source.kt_y_n_m)
        self.kt_z = _double(source.kt_z_n_m)
        self.kr_x = _double(source.kr_x_n_m_rad)
        self.kr_y = _double(source.kr_y_n_m_rad)
        self.kr_z = _double(source.kr_z_n_m_rad)
        self.ct_x = _double(source.ct_x_n_s_m)
        self.ct_y = _double(source.ct_y_n_s_m)
        self.ct_z = _double(source.ct_z_n_s_m)
        form.addRow("Name", self.name)
        form.addRow("Position (mm)", self.position)
        form.addRow("Left mass (kg)", self.left_mass)
        form.addRow("Right mass (kg)", self.right_mass)
        form.addRow("Left Ip (kg·m²)", self.left_ip)
        form.addRow("Right Ip (kg·m²)", self.right_ip)
        form.addRow("Kt x (N/m)", self.kt_x)
        form.addRow("Kt y (N/m)", self.kt_y)
        form.addRow("Kt z / axial (N/m)", self.kt_z)
        form.addRow("Kr x (N·m/rad)", self.kr_x)
        form.addRow("Kr y (N·m/rad)", self.kr_y)
        form.addRow("Kr z / torsion (N·m/rad)", self.kr_z)
        form.addRow("Ct x (N·s/m)", self.ct_x)
        form.addRow("Ct y (N·s/m)", self.ct_y)
        form.addRow("Ct z (N·s/m)", self.ct_z)
        root.addLayout(form)
        root.addWidget(_buttons(self))

    def record(self) -> CouplingSpec:
        return CouplingSpec(
            name=self.name.text().strip(), position_mm=self.position.value(),
            left_mass_kg=self.left_mass.value(), right_mass_kg=self.right_mass.value(),
            left_ip_kg_m2=self.left_ip.value(), right_ip_kg_m2=self.right_ip.value(),
            kt_x_n_m=self.kt_x.value(), kt_y_n_m=self.kt_y.value(), kt_z_n_m=self.kt_z.value(),
            kr_x_n_m_rad=self.kr_x.value(), kr_y_n_m_rad=self.kr_y.value(), kr_z_n_m_rad=self.kr_z.value(),
            ct_x_n_s_m=self.ct_x.value(), ct_y_n_s_m=self.ct_y.value(), ct_z_n_s_m=self.ct_z.value(),
        )

    def changes(self) -> dict[str, object]:
        record = self.record()
        return {name: getattr(record, name) for name in (
            "name", "position_mm", "left_mass_kg", "right_mass_kg", "left_ip_kg_m2", "right_ip_kg_m2",
            "kt_x_n_m", "kt_y_n_m", "kt_z_n_m", "kr_x_n_m_rad", "kr_y_n_m_rad", "kr_z_n_m_rad",
            "ct_x_n_s_m", "ct_y_n_s_m", "ct_z_n_s_m"
        )}


class LoadEditorDialog(QDialog):
    def __init__(self, load: LoadSpec | None = None, *, total_length_mm: float, parent=None) -> None:
        super().__init__(parent)
        source = load or LoadSpec("Load", "generic", 0.5 * total_length_mm, 0.0, 0.0)
        self._metadata = dict(source.metadata)
        self.setWindowTitle("Add Load" if load is None else f"Edit Load — {load.name}")
        root = QVBoxLayout(self)
        _note(
            root,
            "Load identity, type, magnitude and phase are model inputs. Existing metadata "
            "is preserved on edit and the physical station must remain an exact FE node.",
        )
        form = QFormLayout()
        self.name = QLineEdit(source.name)
        self.kind = QLineEdit(source.kind)
        self.position = _double(source.position_mm, minimum=0.0, maximum=max(total_length_mm, 0.0))
        self.magnitude = _double(source.magnitude)
        self.phase = _double(source.phase_deg, minimum=-3600.0, maximum=3600.0)
        form.addRow("Name", self.name)
        form.addRow("Type", self.kind)
        form.addRow("Position (mm)", self.position)
        form.addRow("Magnitude", self.magnitude)
        form.addRow("Phase (deg)", self.phase)
        root.addLayout(form)
        root.addWidget(_buttons(self))

    def record(self) -> LoadSpec:
        return LoadSpec(
            name=self.name.text().strip(), kind=self.kind.text().strip(),
            position_mm=self.position.value(), magnitude=self.magnitude.value(),
            phase_deg=self.phase.value(), metadata=dict(self._metadata),
        )

    def changes(self) -> dict[str, object]:
        record = self.record()
        return {
            "name": record.name,
            "kind": record.kind,
            "position_mm": record.position_mm,
            "magnitude": record.magnitude,
            "phase_deg": record.phase_deg,
            "metadata": dict(record.metadata),
        }


__all__ = [
    "CouplingEditorDialog",
    "DiskEditorDialog",
    "DistributedMassEditorDialog",
    "LoadEditorDialog",
    "MassTypeDialog",
    "PointMassEditorDialog",
    "ProbeEditorDialog",
    "SealEditorDialog",
    "ShaftSectionEditorDialog",
    "SupportEditorDialog",
]
