from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from math import isfinite
from typing import Any, TypeAlias


class DomainError(ValueError):
    """Invalid physical or structural input for the ROSS frontend."""


class BearingKind(StrEnum):
    COEFFICIENT = "coefficient"
    BALL = "ball"
    ROLLER = "roller"
    CYLINDRICAL = "cylindrical"
    PLAIN_JOURNAL = "plain_journal"
    TILTING_PAD = "tilting_pad"


@dataclass(slots=True)
class MaterialSpec:
    name: str = "Steel"
    density_kg_m3: float = 7850.0
    young_pa: float = 2.07e11
    poisson: float = 0.3

    def validate(self) -> None:
        if not self.name.strip():
            raise DomainError("Material name cannot be empty.")
        if self.density_kg_m3 <= 0 or self.young_pa <= 0:
            raise DomainError("Material density and Young modulus must be positive.")
        if not -1.0 < self.poisson < 0.5:
            raise DomainError("Poisson ratio must be in (-1, 0.5).")


@dataclass(slots=True)
class ShaftSectionSpec:
    length_mm: float
    outer_diameter_left_mm: float
    inner_diameter_left_mm: float = 0.0
    outer_diameter_right_mm: float | None = None
    inner_diameter_right_mm: float | None = None
    material: str = "Steel"
    shear_effects: bool = True
    rotary_inertia: bool = True
    gyroscopic: bool = True
    tag: str = ""

    @property
    def odr_mm(self) -> float:
        return self.outer_diameter_left_mm if self.outer_diameter_right_mm is None else self.outer_diameter_right_mm

    @property
    def idr_mm(self) -> float:
        return self.inner_diameter_left_mm if self.inner_diameter_right_mm is None else self.inner_diameter_right_mm

    def validate(self) -> None:
        if self.length_mm <= 0:
            raise DomainError("Shaft section length must be positive.")
        for side, od, inner in (
            ("left", self.outer_diameter_left_mm, self.inner_diameter_left_mm),
            ("right", self.odr_mm, self.idr_mm),
        ):
            if od <= 0:
                raise DomainError(f"Shaft outer diameter at {side} must be positive.")
            if inner < 0 or inner >= od:
                raise DomainError(f"Shaft inner diameter at {side} must satisfy 0 <= ID < OD.")


@dataclass(slots=True)
class DiskSpec:
    position_mm: float
    mass_kg: float
    diametral_inertia_kg_m2: float
    polar_inertia_kg_m2: float
    tag: str = ""

    def validate(self) -> None:
        if min(self.mass_kg, self.diametral_inertia_kg_m2, self.polar_inertia_kg_m2) < 0:
            raise DomainError("Disk mass and inertias cannot be negative.")


@dataclass(slots=True)
class PointMassSpec:
    position_mm: float
    mass_kg: float
    tag: str = ""

    def validate(self) -> None:
        if self.mass_kg < 0:
            raise DomainError("Point mass cannot be negative.")


@dataclass(slots=True)
class CoefficientBearingSpec:
    position_mm: float
    kxx: float
    kzz: float
    cxx: float
    czz: float
    kxz: float = 0.0
    kzx: float = 0.0
    cxz: float = 0.0
    czx: float = 0.0
    frequency_rpm: list[float] | None = None
    n_link_position_mm: float | None = None
    tag: str = ""
    kind: BearingKind = field(default=BearingKind.COEFFICIENT, init=False)

    def validate(self) -> None:
        values = [self.kxx, self.kzz, self.kxz, self.kzx, self.cxx, self.czz, self.cxz, self.czx]

        def finite(value) -> bool:
            seq = value if isinstance(value, (list, tuple)) else [value]
            return all(isfinite(float(v)) for v in seq)

        if not all(finite(v) for v in values):
            raise DomainError("Bearing K/C coefficients must be finite.")
        if self.frequency_rpm is not None:
            if not self.frequency_rpm:
                raise DomainError("Speed-dependent bearing frequency list cannot be empty.")
            if any(v < 0 for v in self.frequency_rpm):
                raise DomainError("Bearing frequencies cannot be negative.")
            n = len(self.frequency_rpm)
            for name, value in (
                ("kxx", self.kxx),
                ("kzz", self.kzz),
                ("kxz", self.kxz),
                ("kzx", self.kzx),
                ("cxx", self.cxx),
                ("czz", self.czz),
                ("cxz", self.cxz),
                ("czx", self.czx),
            ):
                if isinstance(value, (list, tuple)) and len(value) != n:
                    raise DomainError(f"{name} must have the same length as frequency_rpm.")


@dataclass(slots=True)
class BallBearingSpec:
    position_mm: float
    n_balls: int
    ball_diameter_mm: float
    static_load_n: float
    contact_angle_deg: float = 0.0
    cxx: float | None = None
    cyy: float | None = None
    tag: str = ""
    kind: BearingKind = field(default=BearingKind.BALL, init=False)

    def validate(self) -> None:
        if self.n_balls <= 0 or self.ball_diameter_mm <= 0 or self.static_load_n <= 0:
            raise DomainError("Ball bearing geometry and static load must be positive.")


@dataclass(slots=True)
class RollerBearingSpec:
    position_mm: float
    n_rollers: int
    roller_length_mm: float
    static_load_n: float
    contact_angle_deg: float = 0.0
    cxx: float | None = None
    cyy: float | None = None
    tag: str = ""
    kind: BearingKind = field(default=BearingKind.ROLLER, init=False)

    def validate(self) -> None:
        if self.n_rollers <= 0 or self.roller_length_mm <= 0 or self.static_load_n <= 0:
            raise DomainError("Roller bearing geometry and static load must be positive.")


@dataclass(slots=True)
class CylindricalBearingSpec:
    position_mm: float
    speed_rpm: list[float]
    weight_n: float
    bearing_length_mm: float
    journal_diameter_mm: float
    radial_clearance_mm: float
    oil_viscosity_pa_s: float
    tag: str = ""
    kind: BearingKind = field(default=BearingKind.CYLINDRICAL, init=False)

    def validate(self) -> None:
        if not self.speed_rpm or any(s < 0 for s in self.speed_rpm):
            raise DomainError("Cylindrical bearing speed list must contain non-negative values.")
        if min(
            self.weight_n,
            self.bearing_length_mm,
            self.journal_diameter_mm,
            self.radial_clearance_mm,
            self.oil_viscosity_pa_s,
        ) <= 0:
            raise DomainError("Cylindrical bearing physical parameters must be positive.")


@dataclass(slots=True)
class PlainJournalBearingSpec:
    position_mm: float
    pad_axial_length_mm: float
    journal_diameter_mm: float
    radial_clearance_mm: float
    n_pads: int
    pad_arc_deg: float
    oil_supply_temperature_c: float
    frequency_rpm: list[float]
    lubricant: str = "ISOVG32"
    preload: float = 0.0
    load_x_n: float = 0.0
    load_y_n: float = 0.0
    oil_supply_pressure_pa: float = 0.0
    oil_flow_l_min: float | None = None
    thermal_type: str | None = None
    equilibrium_type: str = "match_load"
    film_elements_circumferential: int = 20
    film_elements_axial: int = 10
    tag: str = ""
    kind: BearingKind = field(default=BearingKind.PLAIN_JOURNAL, init=False)

    def validate(self) -> None:
        if min(self.pad_axial_length_mm, self.journal_diameter_mm, self.radial_clearance_mm) <= 0:
            raise DomainError("Plain journal dimensions must be positive.")
        if self.n_pads <= 0 or not 0 < self.pad_arc_deg <= 360:
            raise DomainError("Plain journal pad count/arc are invalid.")
        if not self.frequency_rpm or any(s <= 0 for s in self.frequency_rpm):
            raise DomainError("Plain journal calculations require positive operating speeds.")
        if self.oil_flow_l_min is not None and self.oil_flow_l_min <= 0:
            raise DomainError("Oil flow must be positive when specified.")
        if self.oil_supply_pressure_pa < 0:
            raise DomainError("Oil supply pressure cannot be negative.")
        if self.equilibrium_type not in {"match_load", "match_eccentricity"}:
            raise DomainError("Unsupported fluid-film equilibrium type.")


@dataclass(slots=True)
class TiltingPadBearingSpec:
    position_mm: float
    journal_diameter_mm: float
    radial_clearance_mm: float
    pad_axial_length_mm: float
    pad_thickness_mm: float
    pad_arc_deg: float
    pivot_angle_deg: list[float]
    frequency_rpm: list[float]
    oil_supply_temperature_c: float
    lubricant: str = "ISOVG32"
    preload: float = 0.0
    offset: float = 0.5
    load_x_n: float = 0.0
    load_y_n: float = 0.0
    oil_supply_pressure_pa: float = 0.0
    oil_flow_l_min: float | None = None
    thermal_type: str | None = "full"
    equilibrium_type: str = "match_load"
    film_elements_circumferential: int = 30
    film_elements_axial: int = 30
    pad_elements_radial: int = 16
    tag: str = ""
    kind: BearingKind = field(default=BearingKind.TILTING_PAD, init=False)

    def validate(self) -> None:
        if min(
            self.journal_diameter_mm,
            self.radial_clearance_mm,
            self.pad_axial_length_mm,
            self.pad_thickness_mm,
        ) <= 0:
            raise DomainError("Tilting-pad dimensions must be positive.")
        if not 0 < self.pad_arc_deg <= 360 or not self.pivot_angle_deg:
            raise DomainError("Tilting-pad pad arc/pivot angles are invalid.")
        if not self.frequency_rpm or any(s <= 0 for s in self.frequency_rpm):
            raise DomainError("Tilting-pad calculations require positive operating speeds.")
        if self.oil_flow_l_min is not None and self.oil_flow_l_min <= 0:
            raise DomainError("Oil flow must be positive when specified.")
        if self.oil_supply_pressure_pa < 0:
            raise DomainError("Oil supply pressure cannot be negative.")
        if self.equilibrium_type not in {"match_load", "match_eccentricity"}:
            raise DomainError("Unsupported fluid-film equilibrium type.")


BearingSpec: TypeAlias = (
    CoefficientBearingSpec
    | BallBearingSpec
    | RollerBearingSpec
    | CylindricalBearingSpec
    | PlainJournalBearingSpec
    | TiltingPadBearingSpec
)


@dataclass(slots=True)
class AnalysisRequest:
    modal: bool = True
    critical_speed: bool = True
    campbell: bool = True
    static: bool = False
    modal_speed_rpm: float = 0.0
    campbell_initial_rpm: float = 0.0
    campbell_final_rpm: float = 6000.0
    campbell_step_rpm: float = 250.0
    modes: int = 6

    def validate(self) -> None:
        if self.modal_speed_rpm < 0:
            raise DomainError("Modal speed cannot be negative.")
        if self.modes < 1:
            raise DomainError("At least one mode must be requested.")
        if self.campbell:
            if self.campbell_initial_rpm < 0 or self.campbell_final_rpm <= self.campbell_initial_rpm:
                raise DomainError("Campbell speed range is invalid.")
            if self.campbell_step_rpm <= 0:
                raise DomainError("Campbell speed step must be positive.")


@dataclass(slots=True)
class RotorProject:
    reference: str = ""
    materials: list[MaterialSpec] = field(default_factory=lambda: [MaterialSpec()])
    shaft: list[ShaftSectionSpec] = field(default_factory=list)
    disks: list[DiskSpec] = field(default_factory=list)
    point_masses: list[PointMassSpec] = field(default_factory=list)
    bearings: list[BearingSpec] = field(default_factory=list)
    analyses: AnalysisRequest = field(default_factory=AnalysisRequest)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 2

    @property
    def shaft_length_mm(self) -> float:
        return sum(section.length_mm for section in self.shaft)

    def validate(self) -> None:
        if not self.shaft:
            raise DomainError("Define at least one shaft section.")
        for material in self.materials:
            material.validate()
        names = [m.name for m in self.materials]
        if len(set(names)) != len(names):
            raise DomainError("Material names must be unique.")
        known_materials = set(names)
        for section in self.shaft:
            section.validate()
            if section.material not in known_materials:
                raise DomainError(f"Unknown shaft material: {section.material}")
        length = self.shaft_length_mm
        for collection in (self.disks, self.point_masses, self.bearings):
            for item in collection:
                item.validate()
                if not 0 <= item.position_mm <= length:
                    raise DomainError(
                        f"Component at {item.position_mm:g} mm is outside the shaft [0, {length:g}] mm."
                    )
                linked = getattr(item, "n_link_position_mm", None)
                if linked is not None and not 0 <= linked <= length:
                    raise DomainError("Bearing link position is outside the shaft.")
        self.analyses.validate()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
