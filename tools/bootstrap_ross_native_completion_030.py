from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one exact match, found {count}: {old[:100]!r}")
    write(path, text.replace(old, new, 1))


def regex_replace(path: str, pattern: str, replacement: str) -> None:
    text = read(path)
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{path}: regex did not match exactly once: {pattern[:120]!r}")
    write(path, updated)


replace("pyproject.toml", 'version = "0.24.0"', 'version = "0.30.0"')

replace(
    "src/ross_studio/domain.py",
    'class LateralConvention(StrEnum):\n',
    'class SealModel(StrEnum):\n    """ROSS-native seal model families exposed by Seal Studio."""\n\n    DIRECT = "DIRECT"\n    LABYRINTH = "LABYRINTH"\n    HOLE_PATTERN = "HOLE_PATTERN"\n    HYBRID = "HYBRID"\n\n\nclass LateralConvention(StrEnum):\n',
)
replace(
    "src/ross_studio/domain.py",
    '    material: str = "Steel"\n    fe_elements: int = 1\n',
    '    material: str = "Steel"\n    fe_elements: int = 1\n    shear_effects: bool = True\n    rotary_inertia: bool = True\n    gyroscopic: bool = True\n',
)
regex_replace(
    "src/ross_studio/domain.py",
    r'@dataclass\(slots=True\)\nclass SealSpec:.*?\n\n@dataclass\(slots=True\)\nclass LoadSpec:',
    '''@dataclass(slots=True)
class SealSpec:
    name: str
    position_mm: float
    kxx: float
    kyy: float
    cxx: float
    cyy: float
    kxy: float = 0.0
    kyx: float = 0.0
    cxy: float = 0.0
    cyx: float = 0.0
    model: SealModel = SealModel.DIRECT
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class CouplingSpec:
    """Native ROSS CouplingElement contract spanning two adjacent shaft stations."""

    name: str
    position_mm: float
    left_mass_kg: float
    right_mass_kg: float
    left_ip_kg_m2: float
    right_ip_kg_m2: float
    length_mm: float = 0.0
    left_id_kg_m2: float = 0.0
    right_id_kg_m2: float = 0.0
    kt_x_n_m: float = 0.0
    kt_y_n_m: float = 0.0
    kt_z_n_m: float = 0.0
    kr_x_n_m_rad: float = 0.0
    kr_y_n_m_rad: float = 0.0
    kr_z_n_m_rad: float = 0.0
    ct_x_n_s_m: float = 0.0
    ct_y_n_s_m: float = 0.0
    ct_z_n_s_m: float = 0.0
    cr_x_n_m_s_rad: float = 0.0
    cr_y_n_m_s_rad: float = 0.0
    cr_z_n_m_s_rad: float = 0.0
    od_mm: float = 0.0

    @property
    def end_mm(self) -> float:
        return self.position_mm + self.length_mm


@dataclass(slots=True)
class LoadSpec:''',
)
replace(
    "src/ross_studio/domain.py",
    '        for element in [*self.seals, *self.couplings, *self.loads, *self.probes]:\n            position_ok(element.position_mm, getattr(element, "name", type(element).__name__))\n',
    '''        for seal in self.seals:
            position_ok(seal.position_mm, seal.name)
            if not isinstance(seal.model, SealModel):
                try:
                    seal.model = SealModel(str(seal.model))
                except ValueError as exc:
                    raise EngineeringError(f"Seal {seal.name!r} has unsupported model {seal.model!r}.") from exc

        for coupling in self.couplings:
            position_ok(coupling.position_mm, coupling.name)
            if coupling.length_mm < 0:
                raise EngineeringError(f"Coupling {coupling.name!r}: length cannot be negative.")
            if coupling.length_mm > 0:
                position_ok(coupling.end_mm, f"{coupling.name} end")
            values = (
                coupling.left_mass_kg, coupling.right_mass_kg, coupling.left_ip_kg_m2, coupling.right_ip_kg_m2,
                coupling.left_id_kg_m2, coupling.right_id_kg_m2, coupling.od_mm,
            )
            if any(not isfinite(value) or value < 0 for value in values):
                raise EngineeringError(f"Coupling {coupling.name!r}: masses, inertias and OD must be finite and non-negative.")

        for element in [*self.loads, *self.probes]:
            position_ok(element.position_mm, getattr(element, "name", type(element).__name__))
''',
)

replace(
    "src/ross_studio/topology.py",
    '        for index, coupling in enumerate(project.couplings, 1):\n            request(coupling.position_mm, f"coupling:{index}:{coupling.name}")\n',
    '        for index, coupling in enumerate(project.couplings, 1):\n            request(coupling.position_mm, f"coupling-left:{index}:{coupling.name}")\n            if coupling.length_mm > 0:\n                request(coupling.end_mm, f"coupling-right:{index}:{coupling.name}")\n',
)

replace("src/ross_studio/project_io.py", "    SealSpec,\n", "    SealModel,\n    SealSpec,\n")
replace(
    "src/ross_studio/project_io.py",
    'SCHEMA_VERSION = 2\n_SUPPORTED_SCHEMA_VERSIONS = (1, SCHEMA_VERSION)\n',
    'SCHEMA_VERSION = 3\n_SUPPORTED_SCHEMA_VERSIONS = (1, 2, SCHEMA_VERSION)\n',
)
replace("src/ross_studio/project_io.py", '"app_version": "0.24.0",', '"app_version": "0.30.0",')
regex_replace(
    "src/ross_studio/project_io.py",
    r'def _migrate_payload\(payload: dict\[str, Any\], schema: int\) -> dict\[str, Any\]:.*?\n    return migrated\n',
    '''def _migrate_payload(payload: dict[str, Any], schema: int) -> dict[str, Any]:
    """Migrate old files without inventing physical ROSS data.

    Schema 2 introduced Foundation Studio. Schema 3 adds explicit shaft theory
    switches, seal model provenance and the physical two-node coupling contract.
    A legacy single-station coupling is retained with ``length_mm=0`` and is
    therefore readable but fails the strict native CouplingElement execution gate
    until the user supplies the second station.
    """
    migrated = deepcopy(payload)
    engineering = migrated.get("engineering")
    if schema == 1 and isinstance(engineering, dict):
        engineering.setdefault("foundations", [])
        schema = 2
    if schema <= 2 and isinstance(engineering, dict):
        for section in engineering.get("shaft_sections", []):
            section.setdefault("shear_effects", True)
            section.setdefault("rotary_inertia", True)
            section.setdefault("gyroscopic", True)
        for seal in engineering.get("seals", []):
            seal.setdefault("model", "DIRECT")
            seal.setdefault("metadata", {})
        for coupling in engineering.get("couplings", []):
            coupling.setdefault("length_mm", 0.0)
            coupling.setdefault("left_id_kg_m2", 0.0)
            coupling.setdefault("right_id_kg_m2", 0.0)
            coupling.setdefault("cr_x_n_m_s_rad", 0.0)
            coupling.setdefault("cr_y_n_m_s_rad", 0.0)
            coupling.setdefault("cr_z_n_m_s_rad", 0.0)
            coupling.setdefault("od_mm", 0.0)
    migrated["schema_version"] = SCHEMA_VERSION
    migrated["app_version"] = "0.30.0"
    return migrated
''',
)
replace(
    "src/ross_studio/project_io.py",
    'def _seal(row: dict[str, Any]) -> SealSpec:\n    return SealSpec(**row)\n',
    'def _seal(row: dict[str, Any]) -> SealSpec:\n    data = dict(row)\n    data["model"] = SealModel(data.get("model", SealModel.DIRECT.value))\n    return SealSpec(**data)\n',
)

replace(
    "src/ross_studio/shaft_section_dialog.py",
    '    QComboBox,\n    QDialog,\n',
    '    QCheckBox,\n    QComboBox,\n    QDialog,\n',
)
replace(
    "src/ross_studio/shaft_section_dialog.py",
    '        self.material = QLineEdit(section.material)\n        self.material.setReadOnly(True)\n',
    '        self.material = QLineEdit(section.material)\n        self.material.setReadOnly(True)\n        self.shear_effects = QCheckBox("Include shear deformation")\n        self.shear_effects.setChecked(bool(section.shear_effects))\n        self.rotary_inertia = QCheckBox("Include rotary inertia")\n        self.rotary_inertia.setChecked(bool(section.rotary_inertia))\n        self.gyroscopic = QCheckBox("Include gyroscopic matrix")\n        self.gyroscopic.setChecked(bool(section.gyroscopic))\n',
)
replace(
    "src/ross_studio/shaft_section_dialog.py",
    '        form.addRow("Base FE elements", self.fe_elements)\n        form.addRow("Material", self.material)\n',
    '        form.addRow("Base FE elements", self.fe_elements)\n        form.addRow("Material", self.material)\n        form.addRow("Shear effects", self.shear_effects)\n        form.addRow("Rotary inertia", self.rotary_inertia)\n        form.addRow("Gyroscopic", self.gyroscopic)\n',
)
replace(
    "src/ross_studio/shaft_section_dialog.py",
    '            "fe_elements": self.fe_elements.value(),\n        }\n',
    '            "fe_elements": self.fe_elements.value(),\n            "shear_effects": self.shear_effects.isChecked(),\n            "rotary_inertia": self.rotary_inertia.isChecked(),\n            "gyroscopic": self.gyroscopic.isChecked(),\n        }\n',
)

regex_replace(
    "src/ross_studio/model_entity_dialogs.py",
    r'class CouplingEditorDialog\(QDialog\):.*?\n\nclass LoadEditorDialog\(QDialog\):',
    '''class CouplingEditorDialog(QDialog):
    def __init__(self, coupling: CouplingSpec | None = None, *, total_length_mm: float, parent=None) -> None:
        super().__init__(parent)
        source = coupling or CouplingSpec("Coupling", 0.5 * total_length_mm, 0.0, 0.0, 0.0, 0.0)
        self.setWindowTitle("Add Coupling" if coupling is None else f"Edit Coupling — {coupling.name}")
        root = QVBoxLayout(self)
        _note(
            root,
            "Native ROSS CouplingElement replaces one shaft interval and connects two adjacent FE stations. "
            "Set left position + physical length explicitly. Misalignment remains a separate fault analysis.",
        )
        form = QFormLayout()
        self.name = QLineEdit(source.name)
        self.position = _double(source.position_mm, minimum=0.0, maximum=max(total_length_mm, 0.0))
        self.length = _double(source.length_mm, minimum=0.0, maximum=max(total_length_mm, 0.0))
        self.od = _double(source.od_mm, minimum=0.0)
        self.left_mass = _double(source.left_mass_kg, minimum=0.0)
        self.right_mass = _double(source.right_mass_kg, minimum=0.0)
        self.left_id = _double(source.left_id_kg_m2, minimum=0.0)
        self.right_id = _double(source.right_id_kg_m2, minimum=0.0)
        self.left_ip = _double(source.left_ip_kg_m2, minimum=0.0)
        self.right_ip = _double(source.right_ip_kg_m2, minimum=0.0)
        self.kt_x = _double(source.kt_x_n_m); self.kt_y = _double(source.kt_y_n_m); self.kt_z = _double(source.kt_z_n_m)
        self.kr_x = _double(source.kr_x_n_m_rad); self.kr_y = _double(source.kr_y_n_m_rad); self.kr_z = _double(source.kr_z_n_m_rad)
        self.ct_x = _double(source.ct_x_n_s_m); self.ct_y = _double(source.ct_y_n_s_m); self.ct_z = _double(source.ct_z_n_s_m)
        self.cr_x = _double(source.cr_x_n_m_s_rad); self.cr_y = _double(source.cr_y_n_m_s_rad); self.cr_z = _double(source.cr_z_n_m_s_rad)
        for label, widget in (
            ("Name", self.name), ("Left station / n (mm)", self.position), ("Length to n+1 (mm)", self.length),
            ("Outer diameter for plot (mm)", self.od), ("Left mass (kg)", self.left_mass), ("Right mass (kg)", self.right_mass),
            ("Left Id (kg·m²)", self.left_id), ("Right Id (kg·m²)", self.right_id),
            ("Left Ip (kg·m²)", self.left_ip), ("Right Ip (kg·m²)", self.right_ip),
            ("Kt x (N/m)", self.kt_x), ("Kt y (N/m)", self.kt_y), ("Kt z / axial (N/m)", self.kt_z),
            ("Kr x (N·m/rad)", self.kr_x), ("Kr y (N·m/rad)", self.kr_y), ("Kr z / torsion (N·m/rad)", self.kr_z),
            ("Ct x (N·s/m)", self.ct_x), ("Ct y (N·s/m)", self.ct_y), ("Ct z (N·s/m)", self.ct_z),
            ("Cr x (N·m·s/rad)", self.cr_x), ("Cr y (N·m·s/rad)", self.cr_y), ("Cr z (N·m·s/rad)", self.cr_z),
        ):
            form.addRow(label, widget)
        root.addLayout(form)
        root.addWidget(_buttons(self))

    def record(self) -> CouplingSpec:
        return CouplingSpec(
            name=self.name.text().strip(), position_mm=self.position.value(), length_mm=self.length.value(), od_mm=self.od.value(),
            left_mass_kg=self.left_mass.value(), right_mass_kg=self.right_mass.value(),
            left_id_kg_m2=self.left_id.value(), right_id_kg_m2=self.right_id.value(),
            left_ip_kg_m2=self.left_ip.value(), right_ip_kg_m2=self.right_ip.value(),
            kt_x_n_m=self.kt_x.value(), kt_y_n_m=self.kt_y.value(), kt_z_n_m=self.kt_z.value(),
            kr_x_n_m_rad=self.kr_x.value(), kr_y_n_m_rad=self.kr_y.value(), kr_z_n_m_rad=self.kr_z.value(),
            ct_x_n_s_m=self.ct_x.value(), ct_y_n_s_m=self.ct_y.value(), ct_z_n_s_m=self.ct_z.value(),
            cr_x_n_m_s_rad=self.cr_x.value(), cr_y_n_m_s_rad=self.cr_y.value(), cr_z_n_m_s_rad=self.cr_z.value(),
        )

    def changes(self) -> dict[str, object]:
        record = self.record()
        return {name: getattr(record, name) for name in (
            "name", "position_mm", "length_mm", "od_mm", "left_mass_kg", "right_mass_kg",
            "left_id_kg_m2", "right_id_kg_m2", "left_ip_kg_m2", "right_ip_kg_m2",
            "kt_x_n_m", "kt_y_n_m", "kt_z_n_m", "kr_x_n_m_rad", "kr_y_n_m_rad", "kr_z_n_m_rad",
            "ct_x_n_s_m", "ct_y_n_s_m", "ct_z_n_s_m", "cr_x_n_m_s_rad", "cr_y_n_m_s_rad", "cr_z_n_m_s_rad"
        )}


class LoadEditorDialog(QDialog):''',
)

replace(
    "src/ross_studio/ross_backend_base.py",
    '    material: str\n\n    @property\n',
    '    material: str\n    shear_effects: bool = True\n    rotary_inertia: bool = True\n    gyroscopic: bool = True\n\n    @property\n',
)
replace(
    "src/ross_studio/ross_backend_base.py",
    '            plan.append(ShaftElementPlan(n, x0, x1, section.section, od0, od1, id0, id1, section.material))\n',
    '            plan.append(ShaftElementPlan(\n                n, x0, x1, section.section, od0, od1, id0, id1, section.material,\n                bool(section.shear_effects), bool(section.rotary_inertia), bool(section.gyroscopic),\n            ))\n',
)
replace(
    "src/ross_studio/ross_backend_base.py",
    '        if spec.ross_class != "BearingElement":\n            raise EngineeringError(f"Bearing class {spec.ross_class} is not enabled in the qualified builder.")\n',
    '''        if spec.ross_class == "MagneticBearingElement":
            data = spec.metadata.get("engineering_input", spec.metadata)
            required = ("g0_m", "i0_a", "ag_m2", "nw")
            missing = [key for key in required if key not in data]
            if missing:
                raise EngineeringError(f"AMB {spec.name!r} is missing engineering inputs: {', '.join(missing)}")
            speed_rpm = data.get("speed_rpm")
            frequency = None if speed_rpm is None else np.asarray(speed_rpm, dtype=float) * 2.0 * pi / 60.0
            return rs.MagneticBearingElement(
                n=mapping.node, n_link=n_link, tag=spec.name,
                g0=float(data["g0_m"]), i0=float(data["i0_a"]), ag=float(data["ag_m2"]), nw=float(data["nw"]),
                frequency=frequency, alpha=float(data.get("alpha_rad", pi / 8.0)),
                k_amp=float(data.get("k_amp", 1.0)), k_sense=float(data.get("k_sense", 1.0)),
                kp_pid=float(data.get("kp_pid", 0.0)), kd_pid=float(data.get("kd_pid", 0.0)),
                ki_pid=float(data.get("ki_pid", 0.0)), n_f=float(data.get("n_f_rad_s", 10000.0)),
                sensors_axis_rotation=float(data.get("sensors_axis_rotation_rad", pi / 4.0)),
            )

        if spec.ross_class != "BearingElement":
            raise EngineeringError(f"Bearing class {spec.ross_class} is not enabled in the qualified builder.")
''',
)
regex_replace(
    "src/ross_studio/ross_backend_base.py",
    r'        shaft_elements = \[.*?\n        \]\n\n        support_by_bearing =',
    '''        coupling_by_interval: dict[tuple[float, float], Any] = {}
        for coupling in project.couplings:
            if coupling.length_mm <= 0:
                raise EngineeringError(
                    f"Coupling {coupling.name!r} still uses the legacy single-station contract. "
                    "Edit it and provide a positive length to create native ROSS CouplingElement nodes n and n+1."
                )
            key = (round(coupling.position_mm, 10), round(coupling.end_mm, 10))
            if key in coupling_by_interval:
                raise EngineeringError(f"More than one coupling occupies interval {key} mm.")
            coupling_by_interval[key] = coupling

        shaft_elements: list[Any] = []
        for element in plan:
            coupling = coupling_by_interval.get((round(element.x0_mm, 10), round(element.x1_mm, 10)))
            if coupling is not None:
                shaft_elements.append(
                    rs.CouplingElement(
                        m_l=coupling.left_mass_kg, m_r=coupling.right_mass_kg,
                        Ip_l=coupling.left_ip_kg_m2, Ip_r=coupling.right_ip_kg_m2,
                        Id_l=coupling.left_id_kg_m2, Id_r=coupling.right_id_kg_m2,
                        kt_x=coupling.kt_x_n_m, kt_y=coupling.kt_y_n_m, kt_z=coupling.kt_z_n_m,
                        kr_x=coupling.kr_x_n_m_rad, kr_y=coupling.kr_y_n_m_rad, kr_z=coupling.kr_z_n_m_rad,
                        ct_x=coupling.ct_x_n_s_m, ct_y=coupling.ct_y_n_s_m, ct_z=coupling.ct_z_n_s_m,
                        cr_x=coupling.cr_x_n_m_s_rad, cr_y=coupling.cr_y_n_m_s_rad, cr_z=coupling.cr_z_n_m_s_rad,
                        o_d=None if coupling.od_mm <= 0 else coupling.od_mm / 1000.0,
                        L=coupling.length_mm / 1000.0, n=element.n, tag=coupling.name,
                    )
                )
                continue
            shaft_elements.append(
                rs.ShaftElement(
                    L=element.length_mm / 1000.0, idl=element.id0_mm / 1000.0, odl=element.od0_mm / 1000.0,
                    idr=element.id1_mm / 1000.0, odr=element.od1_mm / 1000.0,
                    material=material_cache[element.material], n=element.n, tag=f"S{element.physical_section:02d}.{element.n:02d}",
                    shear_effects=element.shear_effects, rotary_inertia=element.rotary_inertia, gyroscopic=element.gyroscopic,
                )
            )

        unmatched = set(coupling_by_interval) - {(round(item.x0_mm, 10), round(item.x1_mm, 10)) for item in plan}
        if unmatched:
            joined = ", ".join(f"{a:g}-{b:g}" for a, b in sorted(unmatched))
            raise EngineeringError(
                "Native CouplingElement must replace exactly one adjacent shaft interval; "
                f"these coupling spans contain intermediate nodes or boundaries: {joined} mm."
            )

        support_by_bearing =''',
)

replace(
    "src/ross_studio/ross_backend.py",
    'from .ross_backend_base import RossBuildResult, RossModelBuilder as _BaseRossModelBuilder\n',
    'from .ross_backend_base import RossBuildResult, RossModelBuilder as _BaseRossModelBuilder\nfrom .seal_studio_service import SealStudioService\n',
)
regex_replace(
    "src/ross_studio/ross_backend.py",
    r'        rs = self\._ross\(\)\n        seals: list\[Any\] = \[\]\n        for spec in project\.seals:.*?\n            \)\n\n        existing_bearings =',
    '''        rs = self._ross()
        seal_service = SealStudioService(rs)
        seals: list[Any] = []
        for spec in project.seals:
            mapping = self.map_position(project, spec.position_mm)
            if mapping.node is None:
                if strict:
                    raise EngineeringError(f"Seal {spec.name!r} is not located at an exact FE node.")
                continue
            seals.append(seal_service.native_from_spec(spec, node=mapping.node))

        existing_bearings =''',
)

replace(
    "src/ross_studio/services.py",
    '        Capability(BearingGroup.AMB, "MagneticBearingElement", "Active Magnetic Bearing", AdapterStatus.BLOCKED, "Requires an explicit actuator/sensor/controller domain before execution is enabled."),\n',
    '        Capability(BearingGroup.AMB, "MagneticBearingElement", "Active Magnetic Bearing", AdapterStatus.VALIDATED, "Native ROSS MagneticBearingElement with physical actuator inputs, PID sensor/controller loop, Newmark time integration and ISO 14839 sensitivity workflow."),\n',
)
replace(
    "src/ross_studio/services.py",
    '        plan = NodeInsertionService.plan(project)\n        node_positions = set(plan.positions_mm)\n',
    '''        plan = NodeInsertionService.plan(project)
        for coupling in project.couplings:
            if coupling.length_mm <= 0:
                issues.append(ValidationIssue(
                    "error", "COUPLING_TWO_NODE_REQUIRED",
                    f"{coupling.name} requires a positive length so native ROSS CouplingElement can connect n to n+1.",
                ))
                continue
            left = plan.node_for(coupling.position_mm)
            right = plan.node_for(coupling.end_mm)
            if left is None or right is None or right != left + 1:
                issues.append(ValidationIssue(
                    "error", "COUPLING_NOT_ADJACENT",
                    f"{coupling.name} must span exactly one adjacent ROSS shaft interval; received nodes {left} and {right}.",
                ))

        node_positions = set(plan.positions_mm)
''',
)

replace(
    "src/ross_studio/bearing_input_panel.py",
    '            "MagneticBearingElement": (\n                "AMB remains blocked until actuator, sensor and controller engineering-domain contracts are qualified."\n            ),\n',
    '            "MagneticBearingElement": (\n                "Native ROSS active magnetic bearing. Physical air-gap/coil parameters and PID sensor/controller gains are retained; "\n                "time-domain feedback is evaluated only through Newmark integration."\n            ),\n',
)
replace(
    "src/ross_studio/bearing_input_panel.py",
    '        if self.ross_class in THD_FIELDS:\n            return list(THD_COMMON + THD_FIELDS[self.ross_class])\n',
    '''        if self.ross_class == "MagneticBearingElement":
            return [
                ("speed_rpm", "Controller frequency stations (rpm)", [500.0, 1000.0, 3000.0, 6000.0]),
                ("g0_mm", "Nominal air gap g0 (mm)", 1.0),
                ("i0_a", "Bias current i0 (A)", 1.0),
                ("ag_mm2", "Effective pole area Ag (mm²)", 100.0),
                ("nw", "Windings per coil", 200),
                ("alpha_deg", "Pole angle α (deg)", 22.5),
                ("k_amp", "Amplifier gain", 1.0),
                ("k_sense", "Sensor gain", 1.0),
                ("kp_pid", "PID Kp", 1500.0),
                ("kd_pid", "PID Kd", 10.0),
                ("ki_pid", "PID Ki", 100.0),
                ("n_f_rad_s", "Derivative filter cutoff (rad/s)", 10000.0),
                ("sensors_axis_rotation_deg", "Sensor/actuator axis rotation (deg)", 45.0),
            ]
        if self.ross_class in THD_FIELDS:
            return list(THD_COMMON + THD_FIELDS[self.ross_class])
''',
)
replace(
    "src/ross_studio/bearing_input_panel.py",
    '        def meta(key: str, default: Any) -> Any:\n',
    '        if self.ross_class == "MagneticBearingElement":\n            stored = metadata.get("engineering_input", {}) if metadata.get("source_model") == self.ross_class else {}\n            return {key: stored.get(key, default) for key, _label, default in definitions}\n\n        def meta(key: str, default: Any) -> Any:\n',
)
replace(
    "src/ross_studio/bearing_input_panel.py",
    '            elif self.ross_class == "CylindricalBearing":\n                if float(raw["speed_max_rpm"]) <= float(raw["speed_min_rpm"]):\n',
    '''            elif self.ross_class == "MagneticBearingElement":
                self._validate_speeds([float(v) for v in raw["speed_rpm"]])
                values = {
                    "speed_rpm": [float(v) for v in raw["speed_rpm"]],
                    "g0_m": float(raw["g0_mm"]) / 1000.0,
                    "i0_a": float(raw["i0_a"]),
                    "ag_m2": float(raw["ag_mm2"]) * 1e-6,
                    "nw": int(raw["nw"]),
                    "alpha_rad": float(raw["alpha_deg"]) * pi / 180.0,
                    "k_amp": float(raw["k_amp"]), "k_sense": float(raw["k_sense"]),
                    "kp_pid": float(raw["kp_pid"]), "kd_pid": float(raw["kd_pid"]), "ki_pid": float(raw["ki_pid"]),
                    "n_f_rad_s": float(raw["n_f_rad_s"]),
                    "sensors_axis_rotation_rad": float(raw["sensors_axis_rotation_deg"]) * pi / 180.0,
                }
            elif self.ross_class == "CylindricalBearing":
                if float(raw["speed_max_rpm"]) <= float(raw["speed_min_rpm"]):
''',
)

replace(
    "src/ross_studio/bearing_studio_service.py",
    '    THD and AMB classes are not accepted here; they keep their independent\n    qualification gates.\n',
    '    THD classes keep their specialized solvers. MagneticBearingElement is\n    accepted here because its native ROSS constructor already owns the complete\n    electromagnetic/PID coefficient model; time-domain feedback is qualified separately.\n',
)
replace(
    "src/ross_studio/bearing_studio_service.py",
    '        "CylindricalBearing",\n    }\n',
    '        "CylindricalBearing",\n        "MagneticBearingElement",\n    }\n',
)
replace(
    "src/ross_studio/bearing_studio_service.py",
    '        if ross_class not in self.GENERAL_CLASSES:\n            raise EngineeringError(\n                f"{ross_class} is not a General / Parametric Bearing Studio model. THD/AMB execution remains separately gated."\n            )\n',
    '        if ross_class not in self.GENERAL_CLASSES:\n            raise EngineeringError(f"{ross_class} has no qualified Bearing Studio service.")\n',
)
replace(
    "src/ross_studio/bearing_studio_service.py",
    '        if ross_class == "RollerBearingElement":\n            return self._calculate_roller(inputs)\n        return self._calculate_cylindrical(project, index, inputs)\n',
    '        if ross_class == "RollerBearingElement":\n            return self._calculate_roller(inputs)\n        if ross_class == "MagneticBearingElement":\n            return self._calculate_magnetic(project, inputs)\n        return self._calculate_cylindrical(project, index, inputs)\n',
)
replace(
    "src/ross_studio/bearing_studio_service.py",
    '    def apply(self, project: RotorProject, index: int, result: BearingCalculationResult) -> BearingSpec:\n',
    '''    def _calculate_magnetic(self, project: RotorProject, inputs: dict[str, Any]) -> BearingCalculationResult:
        rs = self._ross()
        speeds_rpm = np.asarray(inputs.get("speed_rpm", [project.operating_cases[0].rated_speed_rpm]), dtype=float)
        if speeds_rpm.ndim != 1 or speeds_rpm.size == 0 or np.any(speeds_rpm <= 0) or np.any(np.diff(speeds_rpm) <= 0):
            raise EngineeringError("AMB speed_rpm must be positive and strictly increasing.")
        required_positive = ("g0_m", "i0_a", "ag_m2", "nw")
        for key in required_positive:
            self._finite_positive(inputs.get(key), key)
        frequency = speeds_rpm * 2.0 * pi / 60.0
        element = rs.MagneticBearingElement(
            n=0, g0=float(inputs["g0_m"]), i0=float(inputs["i0_a"]), ag=float(inputs["ag_m2"]), nw=float(inputs["nw"]),
            frequency=frequency, alpha=float(inputs.get("alpha_rad", pi / 8.0)),
            k_amp=float(inputs.get("k_amp", 1.0)), k_sense=float(inputs.get("k_sense", 1.0)),
            kp_pid=float(inputs.get("kp_pid", 0.0)), kd_pid=float(inputs.get("kd_pid", 0.0)), ki_pid=float(inputs.get("ki_pid", 0.0)),
            n_f=float(inputs.get("n_f_rad_s", 10000.0)), sensors_axis_rotation=float(inputs.get("sensors_axis_rotation_rad", pi / 4.0)),
        )
        points = tuple(self._point(rpm, self._matrix_kc(element, omega)) for rpm, omega in zip(speeds_rpm, frequency))
        rated = min(points, key=lambda point: abs(point.rpm - project.operating_cases[0].rated_speed_rpm))
        scalar = (rated.kxx, rated.kxy, rated.kyx, rated.kyy, rated.cxx, rated.cxy, rated.cyx, rated.cyy)
        engineering_input = {key: value for key, value in inputs.items()}
        engineering_input["speed_rpm"] = [float(value) for value in speeds_rpm]
        return BearingCalculationResult(
            source_model="MagneticBearingElement", application_class="MagneticBearingElement",
            coefficients=points, scalar_kc=scalar,
            metadata={"source_model": "MagneticBearingElement", "engineering_input": engineering_input},
            note="Native ROSS MagneticBearingElement electromagnetic/PID model; Newmark is mandatory for active time-domain feedback.",
        )

    def apply(self, project: RotorProject, index: int, result: BearingCalculationResult) -> BearingSpec:
''',
)
replace(
    "src/ross_studio/bearing_studio_service.py",
    '        spec.ross_class = result.application_class\n        spec.group = BearingGroup.GENERAL\n',
    '        spec.ross_class = result.application_class\n        spec.group = BearingGroup.AMB if result.source_model == "MagneticBearingElement" else BearingGroup.GENERAL\n',
)
replace(
    "src/ross_studio/app_legacy.py",
    '            "ThrustPad": "Axial Thrust Pad",\n',
    '            "ThrustPad": "Axial Thrust Pad",\n            "MagneticBearingElement": "Active Magnetic Bearing",\n',
)

replace(
    "src/ross_studio/navigation_registry.py",
    '    NavigationNode("model.bearings.amb", "Active Magnetic Bearings", "route",\n                   parent="model.bearings", icon="bearing", locked=True,\n                   tooltip="Visible by design; blocked until the AMB controller/sensor/Newmark contract is qualified."),\n',
    '    NavigationNode("model.bearings.amb", "Active Magnetic Bearings", "route",\n                   parent="model.bearings", icon="bearing",\n                   tooltip="Native MagneticBearingElement with PID feedback, Newmark time integration and ISO 14839 sensitivity."),\n',
)
replace(
    "src/ross_studio/page_registry.py",
    'PageOwner = Literal["home", "rotor", "bearing", "foundation", "analysis"]\n',
    'PageOwner = Literal["home", "rotor", "bearing", "seal", "foundation", "analysis"]\n',
)
replace(
    "src/ross_studio/page_registry.py",
    '    "model.bearings.amb": PageRouteSpec(\n        "model.bearings.amb", "bearing", bearing_group="AMB", title="Active Magnetic Bearings", operational=False,\n        note="Blocked until the AMB actuator/sensor/controller/Newmark feedback contract is qualified.",\n    ),\n    "model.seals": PageRouteSpec("model.seals", "rotor", editor_key="seals", title="Seals"),\n',
    '    "model.bearings.amb": PageRouteSpec(\n        "model.bearings.amb", "bearing", bearing_group="AMB", title="Active Magnetic Bearings", implementation_phase="0.30.0",\n        operational=True, note="Native MagneticBearingElement qualified with physical actuator/PID inputs and Newmark feedback."\n    ),\n    "model.seals": PageRouteSpec(\n        "model.seals", "seal", title="Seal Studio", implementation_phase="0.30.0", operational=True,\n        note="Native SealElement, LabyrinthSeal, HolePatternSeal and HybridSeal with Preview → Apply provenance."\n    ),\n',
)
replace(
    "src/ross_studio/page_registry.py",
    '        "analysis.time_frequency", "analysis", title="Time & Frequency", implementation_phase="0.21.0", operational=True,\n',
    '        "analysis.time_frequency", "analysis", title="Time & Frequency", implementation_phase="0.30.0", operational=True,\n',
)
replace(
    "src/ross_studio/page_registry.py",
    '            "run_harmonic_balance_response(), run_ucs() and run_clearance_analysis() transactions with native plots."\n',
    '            "run_harmonic_balance_response(), run_ucs(), run_clearance_analysis(), native Misalignment/Rubbing/Crack faults, "\n            "AMB Newmark controller outputs and run_amb_sensitivity() transactions with native plots."\n',
)

replace("src/ross_studio/app.py", '"""ROSS Studio 0.24 application composition root.\n', '"""ROSS Studio 0.30 application composition root.\n')
replace(
    "src/ross_studio/app.py",
    'adds the editable Foundation Studio without introducing a public/global Results route.\n',
    'adds the editable Foundation Studio; 0.30 completes native ROSS seals, couplings, faults, shaft switches and AMB workflows.\n',
)
replace(
    "src/ross_studio/app.py",
    'from .pages.rotor_workspace import RotorModelPage\n',
    'from .pages.rotor_workspace import RotorModelPage\nfrom .pages.seal_workspace import SealStudioPage\n',
)
replace(
    "src/ross_studio/app.py",
    '    """0.24 shell with deterministic, stochastic, MultiRotor and Foundation workspaces."""\n',
    '    """0.30 shell with native ROSS deterministic, stochastic and component workspaces."""\n',
)
replace(
    "src/ross_studio/app.py",
    '        elif spec.owner == "foundation":\n            page = FoundationWorkspacePage(self.project)\n',
    '        elif spec.owner == "foundation":\n            page = FoundationWorkspacePage(self.project)\n        elif spec.owner == "seal":\n            page = SealStudioPage(self.project)\n',
)
replace("src/ross_studio/app.py", '        if spec.owner in {"foundation", "analysis"}:\n', '        if spec.owner in {"seal", "foundation", "analysis"}:\n')
replace(
    "src/ross_studio/app.py",
    '            if route == "model.supports.foundation":\n',
    '            if route == "model.seals":\n                detail = "Native Direct / Labyrinth / Hole Pattern / Hybrid Seal Studio with leakage, pressure and convergence outputs"\n            elif route == "model.supports.foundation":\n',
)
replace(
    "src/ross_studio/app.py",
    '                    "Independent native ROSS Frequency, Unbalance, Time, HBM, UCS and Clearance transactions "\n                    "with per-analysis caches and plot-only post-processing"\n',
    '                    "Native ROSS Frequency, Unbalance, Time, HBM, UCS, Clearance, Faults and AMB sensitivity; "\n                    "Newmark AMB outputs expose displacement, current and magnetic force"\n',
)

replace(
    "src/ross_studio/pages/time_frequency_workspace.py",
    'from .architecture_workspaces import AnalysisRoutePage\n',
    'from .architecture_workspaces import AnalysisRoutePage\nfrom .faults_workspace import FaultsWorkspace\nfrom .amb_sensitivity_workspace import AMBSensitivityWorkspace\n',
)
replace(
    "src/ross_studio/pages/time_frequency_workspace.py",
    '        self.tabs.addTab(self._clearance_tab(), "Clearance")\n',
    '        self.tabs.addTab(self._clearance_tab(), "Clearance")\n        self.tabs.addTab(FaultsWorkspace(self.project), "Faults")\n        self.tabs.addTab(AMBSensitivityWorkspace(self.project), "AMB Sensitivity")\n',
)
replace(
    "src/ross_studio/pages/time_frequency_workspace.py",
    '            "Harmonic Balance, UCS and Clearance as independent ROSS 2.3.0 transactions. "\n',
    '            "Harmonic Balance, UCS, Clearance, Faults and AMB sensitivity as native ROSS 2.3.0 transactions. "\n',
)
replace(
    "src/ross_studio/time_frequency_analysis.py",
    '        build = self._build(project, elapsed, progress=progress, cancelled=cancelled, label="Time Response")\n        t = np.linspace(0.0, float(request.duration_s), int(request.samples), dtype=float)\n',
    '        build = self._build(project, elapsed, progress=progress, cancelled=cancelled, label="Time Response")\n        has_amb = any(type(element).__name__ == "MagneticBearingElement" for element in build.rotor.bearing_elements)\n        if has_amb and request.method.strip().casefold() != "newmark":\n            raise EngineeringError(\n                "Active Magnetic Bearings require method=\'newmark\' so the sensor/controller/actuator force is updated at every time step."\n            )\n        t = np.linspace(0.0, float(request.duration_s), int(request.samples), dtype=float)\n',
)
replace(
    "src/ross_studio/time_frequency_native.py",
    '    "dfft": "DFFT · probes",\n}\n',
    '    "dfft": "DFFT · probes",\n    "amb_disps": "AMB · sensor displacements",\n    "amb_currents": "AMB · control currents",\n    "amb_forces": "AMB · magnetic forces",\n}\n',
)
replace(
    "src/ross_studio/time_frequency_native.py",
    '        elif key == "dfft":\n            figure = native.plot_dfft(\n                probe=self._probes(),\n                displacement_units=displacement_units,\n                frequency_units=frequency_units,\n                frequency_range=frequency_range,\n            )\n        else:\n            raise KeyError(key)\n',
    '        elif key == "dfft":\n            figure = native.plot_dfft(\n                probe=self._probes(),\n                displacement_units=displacement_units,\n                frequency_units=frequency_units,\n                frequency_range=frequency_range,\n            )\n        elif key == "amb_disps":\n            if not hasattr(native, "plot_amb_disps"):\n                raise EngineeringError("This time response contains no active magnetic bearing data.")\n            figure = native.plot_amb_disps(displacement_units=displacement_units, time_units=time_units)\n        elif key == "amb_currents":\n            if not hasattr(native, "plot_amb_currents"):\n                raise EngineeringError("This time response contains no active magnetic bearing data.")\n            figure = native.plot_amb_currents(current_units="A", time_units=time_units)\n        elif key == "amb_forces":\n            if not hasattr(native, "plot_amb_forces"):\n                raise EngineeringError("This time response contains no active magnetic bearing data.")\n            figure = native.plot_amb_forces(force_units="N", time_units=time_units)\n        else:\n            raise KeyError(key)\n',
)
replace(
    "src/ross_studio/time_frequency_native.py",
    '        "plot_1d", "plot_2d", "plot_3d", "plot_dfft", "data_time_response",\n        "t", "yout", "xout",\n',
    '        "plot_1d", "plot_2d", "plot_3d", "plot_dfft", "data_time_response",\n        "plot_amb_disps", "plot_amb_currents", "plot_amb_forces",\n        "t", "yout", "xout",\n',
)

replace(
    ".github/workflows/tests.yml",
    '      - name: Qualify Foundation Studio 0.24\n        run: python tools/qualify_foundation_024.py\n',
    '      - name: Qualify Foundation Studio 0.24\n        run: python tools/qualify_foundation_024.py\n\n      - name: Qualify native ROSS completion 0.30\n        run: python tools/qualify_ross_native_completion_030.py\n',
)

for path in (
    ROOT / "tools" / "bootstrap_ross_native_completion_030.py",
    ROOT / ".github" / "workflows" / "bootstrap-native-completion-030.yml",
):
    if path.exists():
        path.unlink()

print("ROSS Studio 0.30 native ROSS completion patch applied")
