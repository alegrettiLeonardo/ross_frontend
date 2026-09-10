from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .domain import BearingCoefficientPoint, RotorProject
from .legacy_import import load_irdin_project


@dataclass(slots=True)
class ShaftSegment:
    section: int
    length_mm: float
    od_left_mm: float
    od_right_mm: float
    id_left_mm: float = 0.0
    id_right_mm: float = 0.0
    material: str = "Steel"


@dataclass(slots=True)
class ProjectModel:
    name: str = "OP-W60-500-60Hz-IC611-P3"
    description: str = "W60-500-60Hz-IC611-P3"
    created: str = "Imported from iRdin"
    modified: str = "Imported from iRdin"
    speed_rpm: int = 3600
    speed_min_rpm: int = 0
    speed_max_rpm: int = 4500
    frequency_hz: float = 60.0
    line: str = "W60"
    frame: str = "500"
    poles: int = 2
    material: str = "Steel"
    total_mass_kg: float = 808.5
    dof: int = 0
    disks: int = 4
    bearings: int = 2
    supports: int = 2
    segments: list[ShaftSegment] = field(default_factory=list)
    engineering: RotorProject | None = None

    @property
    def total_length_mm(self) -> float:
        return sum(s.length_mm for s in self.segments)

    @property
    def physical_sections(self) -> int:
        return len(self.segments)

    @property
    def ross_shaft_elements(self) -> int:
        return self.engineering.ross_shaft_element_count if self.engineering else len(self.segments)

    def touch(self) -> None:
        self.modified = datetime.now().strftime("%b %d, %Y  %H:%M")

    @classmethod
    def from_engineering(cls, project: RotorProject) -> "ProjectModel":
        case = project.operating_cases[0]
        attached_mass = sum(m.mass_kg for m in project.distributed_masses) + sum(m.mass_kg for m in project.point_masses)
        segments = [
            ShaftSegment(
                section=s.section,
                length_mm=s.length_mm,
                od_left_mm=s.od_left_mm,
                od_right_mm=s.odr_mm,
                id_left_mm=s.id_left_mm,
                id_right_mm=s.idr_mm,
                material=s.material,
            )
            for s in project.shaft_sections
        ]
        return cls(
            name=project.name,
            description=project.description,
            speed_rpm=round(case.rated_speed_rpm),
            speed_min_rpm=round(case.speed_min_rpm),
            speed_max_rpm=round(case.speed_max_rpm),
            frequency_hz=case.frequency_hz,
            line=project.line,
            frame=project.frame,
            poles=project.poles,
            material=segments[0].material if segments else "Steel",
            total_mass_kg=attached_mass,
            disks=len(project.distributed_masses) + len(project.disks),
            bearings=len(project.bearings),
            supports=len(project.supports),
            segments=segments,
            engineering=project,
        )


def load_reference_project_model() -> ProjectModel:
    resource = Path(__file__).with_name("resources") / "OP-W60-500-60Hz-IC611-P3.txt"
    return ProjectModel.from_engineering(load_irdin_project(resource))


@dataclass(slots=True)
class BearingCoefficientRow:
    rpm: int
    kxx: float
    kxy: float
    kyx: float
    kyy: float
    cxx: float
    cxy: float
    cyx: float
    cyy: float

    @classmethod
    def from_point(cls, point: BearingCoefficientPoint) -> "BearingCoefficientRow":
        return cls(round(point.rpm), point.kxx, point.kxy, point.kyx, point.kyy, point.cxx, point.cxy, point.cyx, point.cyy)


_BEARING_TITLES = {
    "BearingElement": "Coefficient K/C",
    "BallBearingElement": "Ball Bearing",
    "RollerBearingElement": "Roller Bearing",
    "CylindricalBearing": "Cylindrical Bearing",
    "PlainJournal": "Plain Journal",
    "TiltingPad": "Tilting Pad",
    "ThrustPad": "Thrust Pad",
    "SqueezeFilmDamper": "Squeeze Film Damper",
    "MagneticBearingElement": "Active Magnetic Bearing",
}


@dataclass(slots=True)
class BearingModel:
    name: str = "DE Journal Bearing"
    bearing_type: str = "Coefficient K/C"
    ross_class: str = "BearingElement"
    group: str = "General / Parametric"
    node_position: str = "x = 467.8 mm"
    connected_shaft: str = "Rotor"
    shaft_diameter_mm: float = 100.0
    pad_length_mm: float = 80.0
    radial_clearance_mm: float = 0.10
    pad_arc_deg: float = 60.0
    preload: float = 0.50
    number_of_pads: int = 5
    speed_min_rpm: int = 900
    speed_max_rpm: int = 5000
    load_x_n: float = 5000.0
    load_y_n: float = 0.0
    oil_inlet_temperature_c: float = 40.0
    supply_pressure_bar: float = 2.0
    lubricant_grade: str = "ISO VG 32"
    thermal_model: str = "Energy Equation"
    viscosity_model: str = "Roelands"
    mesh: str = "Medium (60 × 30)"
    operating_rpm: int = 3600
    eccentricity_ratio: float = 0.0
    attitude_angle_deg: float = 0.0
    min_film_thickness_mm: float = 0.0
    power_loss_kw: float = 0.0
    flow_rate_l_min: float = 0.0
    max_temperature_c: float = 0.0
    coefficients: list[BearingCoefficientRow] = field(default_factory=list)

    @classmethod
    def from_project(cls, project: RotorProject, index: int = 0) -> "BearingModel":
        if not project.bearings:
            return cls()
        spec = project.bearings[index]
        points = [BearingCoefficientRow.from_point(p) for p in spec.coefficients]
        speeds = [p.rpm for p in spec.coefficients]
        source_model = str(spec.metadata.get("source_model", spec.ross_class))
        speed_metadata = spec.metadata.get("speed_rpm")
        if not speeds and isinstance(speed_metadata, list):
            speeds = [float(value) for value in speed_metadata]
        return cls(
            name=spec.name,
            bearing_type=_BEARING_TITLES.get(source_model, source_model),
            ross_class=source_model,
            group=spec.group.value,
            node_position=f"x = {spec.position_mm:g} mm",
            connected_shaft="Rotor",
            shaft_diameter_mm=float(spec.metadata.get("journal_diameter_m", 0.1)) * 1000.0,
            pad_length_mm=float(spec.metadata.get("bearing_length_m", 0.08)) * 1000.0,
            radial_clearance_mm=float(spec.metadata.get("radial_clearance_m", 1.0e-4)) * 1000.0,
            number_of_pads=int(spec.metadata.get("n_balls", spec.metadata.get("n_rollers", 5))),
            speed_min_rpm=round(min(speeds)) if speeds else 0,
            speed_max_rpm=round(max(speeds)) if speeds else 0,
            load_x_n=float(spec.metadata.get("weight_n", spec.metadata.get("static_load_n", 5000.0))),
            operating_rpm=round(project.operating_cases[0].rated_speed_rpm),
            coefficients=points,
        )
