from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite


class EngineeringError(ValueError):
    """Engineering-domain validation error."""


class BearingGroup(StrEnum):
    GENERAL = "General / Parametric"
    THD = "THD"
    AMB = "AMB"


class AdapterStatus(StrEnum):
    VALIDATED = "Validated"
    PLANNED = "Adapter planned"
    BLOCKED = "Blocked"


class FoundationModel(StrEnum):
    """Qualified Foundation Studio model families for ROSS Studio 0.24."""

    RIGID = "RIGID"
    LUMPED_KC = "LUMPED_KC"
    LUMPED_KCM = "LUMPED_KCM"
    FREQUENCY_DEPENDENT_KC = "FREQUENCY_DEPENDENT_KC"
    REDUCED_MATRIX = "REDUCED_MATRIX"


class SealModel(StrEnum):
    """ROSS-native seal model families exposed by Seal Studio."""

    DIRECT = "DIRECT"
    LABYRINTH = "LABYRINTH"
    HOLE_PATTERN = "HOLE_PATTERN"
    HYBRID = "HYBRID"


class LateralConvention(StrEnum):
    """Positive-rotation convention used by lateral dynamic analyses."""

    ROSS_NATIVE = "ROSS_NATIVE"
    ROTORDIN_POSITIVE = "ROTORDIN_POSITIVE"


class ProbeAngleContract(StrEnum):
    """Unit contract for raw lateral probe orientation values."""

    DEGREES = "DEGREES"
    ROTORDIN_FRONTEND_BUG_RAD = "ROTORDIN_FRONTEND_BUG_RAD"


@dataclass(slots=True, frozen=True)
class MaterialSpec:
    name: str = "Steel"
    density_kg_m3: float = 7850.0
    young_pa: float = 207e9
    poisson: float = 0.3

    @property
    def shear_pa(self) -> float:
        return self.young_pa / (2.0 * (1.0 + self.poisson))

    def validate(self) -> None:
        if self.density_kg_m3 <= 0 or self.young_pa <= 0:
            raise EngineeringError("Material density and Young's modulus must be positive.")
        if not -1.0 < self.poisson < 0.5:
            raise EngineeringError("Poisson ratio must be inside the physical isotropic range (-1, 0.5).")


@dataclass(slots=True)
class ShaftSection:
    section: int
    length_mm: float
    od_left_mm: float
    od_right_mm: float | None = None
    id_left_mm: float = 0.0
    id_right_mm: float | None = None
    material: str = "Steel"
    fe_elements: int = 1
    shear_effects: bool = True
    rotary_inertia: bool = True
    gyroscopic: bool = True

    @property
    def odr_mm(self) -> float:
        return self.od_left_mm if self.od_right_mm is None else self.od_right_mm

    @property
    def idr_mm(self) -> float:
        return self.id_left_mm if self.id_right_mm is None else self.id_right_mm

    def validate(self) -> None:
        if self.section < 1 or self.length_mm <= 0:
            raise EngineeringError("Shaft section number and length must be positive.")
        if min(self.od_left_mm, self.odr_mm) <= 0:
            raise EngineeringError(f"Shaft section {self.section}: outer diameter must be positive.")
        if min(self.id_left_mm, self.idr_mm) < 0:
            raise EngineeringError(f"Shaft section {self.section}: inner diameter cannot be negative.")
        if self.id_left_mm >= self.od_left_mm or self.idr_mm >= self.odr_mm:
            raise EngineeringError(f"Shaft section {self.section}: inner diameter must be smaller than outer diameter.")
        if isinstance(self.fe_elements, bool) or not isinstance(self.fe_elements, int) or self.fe_elements < 1:
            raise EngineeringError(
                f"Shaft section {self.section}: FE element count must be an integer >= 1; received {self.fe_elements!r}."
            )
        if self.fe_elements > 1000:
            raise EngineeringError(
                f"Shaft section {self.section}: FE element count {self.fe_elements} exceeds the 1000-element safety limit per physical section."
            )


@dataclass(slots=True, frozen=True)
class BearingCoefficientPoint:
    rpm: float
    kxx: float
    kxy: float
    kyx: float
    kyy: float
    cxx: float
    cxy: float
    cyx: float
    cyy: float


@dataclass(slots=True)
class BearingSpec:
    name: str
    position_mm: float
    ross_class: str = "BearingElement"
    group: BearingGroup = BearingGroup.GENERAL
    kxx: float = 0.0
    kyy: float = 0.0
    kxy: float = 0.0
    kyx: float = 0.0
    cxx: float = 0.0
    cyy: float = 0.0
    cxy: float = 0.0
    cyx: float = 0.0
    coefficients: list[BearingCoefficientPoint] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def frequency_dependent(self) -> bool:
        return bool(self.coefficients)


@dataclass(slots=True)
class DistributedMassSpec:
    name: str
    start_mm: float
    length_mm: float
    mass_kg: float
    od_mm: float = 0.0
    id_mm: float = 0.0
    is_package: bool = False
    ump_enabled: bool = False
    ump_value: float = 0.0

    @property
    def end_mm(self) -> float:
        return self.start_mm + self.length_mm

    @property
    def center_mm(self) -> float:
        return self.start_mm + 0.5 * self.length_mm

    def equivalent_disk_inertias_kg_m2(self) -> tuple[float, float]:
        """Return (Id, Ip) for the finite hollow-cylinder body represented by `[Massas]`."""
        if self.mass_kg < 0:
            raise EngineeringError(f"{self.name}: mass cannot be negative.")
        if self.length_mm <= 0:
            raise EngineeringError(f"{self.name}: axial length must be positive for equivalent-disk realization.")
        if self.od_mm <= 0:
            raise EngineeringError(f"{self.name}: OD must be positive for equivalent-disk realization.")
        if self.id_mm < 0 or self.id_mm >= self.od_mm:
            raise EngineeringError(f"{self.name}: ID must satisfy 0 <= ID < OD for equivalent-disk realization.")

        ro = self.od_mm / 2000.0
        ri = self.id_mm / 2000.0
        length_m = self.length_mm / 1000.0
        ip = 0.5 * self.mass_kg * (ro**2 + ri**2)
        id_ = (self.mass_kg / 12.0) * (3.0 * (ro**2 + ri**2) + length_m**2)
        return id_, ip


@dataclass(slots=True)
class PointMassSpec:
    """Legacy ``[Concent]`` rigid concentrated body."""

    name: str
    position_mm: float
    mass_kg: float
    ix_kg_m2: float = 0.0
    iy_kg_m2: float = 0.0
    iz_kg_m2: float = 0.0


@dataclass(slots=True)
class DiskSpec:
    name: str
    position_mm: float
    mass_kg: float
    id_kg_m2: float
    ip_kg_m2: float


@dataclass(slots=True)
class SupportSpec:
    name: str
    bearing_index: int
    mass_kg: float
    kxx: float = 0.0
    kyy: float = 0.0
    kxy: float = 0.0
    kyx: float = 0.0
    cxx: float = 0.0
    cyy: float = 0.0
    cxy: float = 0.0
    cyx: float = 0.0


@dataclass(slots=True, frozen=True)
class FoundationCoefficientPoint:
    """Frequency-dependent lateral foundation K/C point.

    Frequency is persisted in Hz for an engineering-facing contract and converted
    to rad/s only at the ROSS boundary.
    """

    frequency_hz: float
    kxx: float
    kxy: float
    kyx: float
    kyy: float
    cxx: float
    cxy: float
    cyx: float
    cyy: float


@dataclass(slots=True)
class FoundationSpec:
    """Structural subsystem below one qualified local flexible support.

    ``support_index`` owns the attachment explicitly. Foundation Studio never
    infers ownership from nearest axial position and never reinterprets SupportSpec
    coefficients as foundation coefficients.
    """

    name: str
    support_index: int
    model_type: FoundationModel = FoundationModel.RIGID
    mass_kg: float = 0.0
    dof: int = 2
    kxx: float = 0.0
    kyy: float = 0.0
    kxy: float = 0.0
    kyx: float = 0.0
    cxx: float = 0.0
    cyy: float = 0.0
    cxy: float = 0.0
    cyx: float = 0.0
    coefficients: list[FoundationCoefficientPoint] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
    status: AdapterStatus = AdapterStatus.VALIDATED

    @property
    def frequency_dependent(self) -> bool:
        return self.model_type == FoundationModel.FREQUENCY_DEPENDENT_KC

    def validate(self) -> None:
        if not self.name.strip():
            raise EngineeringError("Foundation name cannot be empty.")
        if not isinstance(self.model_type, FoundationModel):
            try:
                self.model_type = FoundationModel(str(self.model_type))
            except ValueError as exc:
                raise EngineeringError(f"Foundation {self.name!r} uses unsupported model {self.model_type!r}.") from exc
        if self.dof != 2:
            self.status = AdapterStatus.BLOCKED
            raise EngineeringError(
                f"Foundation {self.name!r} requests {self.dof}-DOF dynamics; Foundation Studio 0.24 qualifies only lateral 2-DOF K/C/M. "
                "6-DOF and reduced-matrix foundations remain BLOCKED."
            )
        if self.model_type == FoundationModel.REDUCED_MATRIX:
            self.status = AdapterStatus.BLOCKED
            raise EngineeringError(
                f"Foundation {self.name!r}: REDUCED_MATRIX is visible but BLOCKED in 0.24 until an explicit reduced multi-DOF adapter is qualified."
            )
        scalars = (
            self.mass_kg,
            self.kxx, self.kyy, self.kxy, self.kyx,
            self.cxx, self.cyy, self.cxy, self.cyx,
        )
        if not all(isfinite(value) for value in scalars):
            raise EngineeringError(f"Foundation {self.name!r} contains a non-finite K/C/M value.")
        if self.mass_kg < 0:
            raise EngineeringError(f"Foundation {self.name!r} mass cannot be negative.")

        if self.model_type == FoundationModel.RIGID:
            if self.mass_kg != 0.0 or self.coefficients or any(value != 0.0 for value in scalars[1:]):
                raise EngineeringError(
                    f"Foundation {self.name!r}: RIGID is an exact ground attachment and cannot carry independent K/C/M inputs."
                )
        elif self.model_type == FoundationModel.LUMPED_KC:
            if self.mass_kg != 0.0:
                raise EngineeringError(f"Foundation {self.name!r}: LUMPED_KC requires zero foundation mass; use LUMPED_KCM for Mfoundation.")
            if self.coefficients:
                raise EngineeringError(f"Foundation {self.name!r}: LUMPED_KC cannot contain a frequency-dependent K/C table.")
        elif self.model_type == FoundationModel.LUMPED_KCM:
            if self.mass_kg <= 0.0:
                raise EngineeringError(f"Foundation {self.name!r}: LUMPED_KCM requires positive foundation mass.")
            if self.coefficients:
                raise EngineeringError(f"Foundation {self.name!r}: LUMPED_KCM cannot contain a frequency-dependent K/C table.")
        elif self.model_type == FoundationModel.FREQUENCY_DEPENDENT_KC:
            if self.mass_kg != 0.0:
                raise EngineeringError(
                    f"Foundation {self.name!r}: FREQUENCY_DEPENDENT_KC has no foundation mass in the 0.24 contract; use LUMPED_KCM for mass."
                )
            if not self.coefficients:
                raise EngineeringError(f"Foundation {self.name!r}: FREQUENCY_DEPENDENT_KC requires at least one K/C frequency point.")
            previous = -1.0
            for point in self.coefficients:
                values = (
                    point.frequency_hz,
                    point.kxx, point.kyy, point.kxy, point.kyx,
                    point.cxx, point.cyy, point.cxy, point.cyx,
                )
                if not all(isfinite(value) for value in values):
                    raise EngineeringError(f"Foundation {self.name!r} contains a non-finite frequency-table value.")
                if point.frequency_hz < 0.0 or point.frequency_hz <= previous:
                    raise EngineeringError(
                        f"Foundation {self.name!r} frequency points must be finite, non-negative and strictly increasing."
                    )
                previous = point.frequency_hz
        self.status = AdapterStatus.VALIDATED


@dataclass(slots=True)
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
class LoadSpec:
    name: str
    kind: str
    position_mm: float
    magnitude: float
    phase_deg: float = 0.0
    metadata: dict[str, float | int | str] = field(default_factory=dict)


@dataclass(slots=True)
class ProbeSpec:
    name: str
    position_mm: float
    coordinate: int = 1
    orientation_deg: float = 0.0


@dataclass(slots=True)
class OperatingCase:
    name: str = "Rated / sweep"
    rated_speed_rpm: float = 3600.0
    speed_min_rpm: float = 0.0
    speed_max_rpm: float = 4500.0
    frequency_hz: float = 60.0


@dataclass(slots=True)
class RotorProject:
    name: str
    reference: str = ""
    line: str = ""
    frame: str = ""
    poles: int = 2
    description: str = ""
    lateral_convention: LateralConvention = LateralConvention.ROSS_NATIVE
    probe_angle_contract: ProbeAngleContract = ProbeAngleContract.DEGREES
    materials: dict[str, MaterialSpec] = field(default_factory=lambda: {"Steel": MaterialSpec()})
    shaft_sections: list[ShaftSection] = field(default_factory=list)
    bearings: list[BearingSpec] = field(default_factory=list)
    distributed_masses: list[DistributedMassSpec] = field(default_factory=list)
    point_masses: list[PointMassSpec] = field(default_factory=list)
    disks: list[DiskSpec] = field(default_factory=list)
    supports: list[SupportSpec] = field(default_factory=list)
    foundations: list[FoundationSpec] = field(default_factory=list)
    seals: list[SealSpec] = field(default_factory=list)
    couplings: list[CouplingSpec] = field(default_factory=list)
    loads: list[LoadSpec] = field(default_factory=list)
    probes: list[ProbeSpec] = field(default_factory=list)
    operating_cases: list[OperatingCase] = field(default_factory=lambda: [OperatingCase()])
    warnings: list[str] = field(default_factory=list)

    @property
    def total_length_mm(self) -> float:
        return sum(s.length_mm for s in self.shaft_sections)

    @property
    def physical_section_count(self) -> int:
        return len(self.shaft_sections)

    @property
    def requested_shaft_element_count(self) -> int:
        """User-requested base mesh before exact node insertion for point entities."""
        return sum(section.fe_elements for section in self.shaft_sections)

    def section_boundaries_mm(self) -> list[float]:
        values = [0.0]
        x = 0.0
        for section in self.shaft_sections:
            x += section.length_mm
            values.append(round(x, 10))
        return values

    def topology_split_positions_mm(self) -> list[float]:
        """Return base FE mesh plus all exact physical node insertions."""
        from .topology import NodeInsertionService

        return list(NodeInsertionService.plan(self).positions_mm)

    @property
    def ross_shaft_element_count(self) -> int:
        return max(0, len(self.topology_split_positions_mm()) - 1)

    def validate(self) -> None:
        if not self.name.strip():
            raise EngineeringError("Project name cannot be empty.")
        if self.poles < 1:
            raise EngineeringError("Pole count must be positive.")
        if not self.shaft_sections:
            raise EngineeringError("At least one physical shaft section is required.")
        if not isinstance(self.lateral_convention, LateralConvention):
            try:
                self.lateral_convention = LateralConvention(str(self.lateral_convention))
            except ValueError as exc:
                raise EngineeringError(f"Unsupported lateral convention {self.lateral_convention!r}.") from exc
        if not isinstance(self.probe_angle_contract, ProbeAngleContract):
            try:
                self.probe_angle_contract = ProbeAngleContract(str(self.probe_angle_contract))
            except ValueError as exc:
                raise EngineeringError(f"Unsupported probe angle contract {self.probe_angle_contract!r}.") from exc
        for material in self.materials.values():
            material.validate()
        for section in self.shaft_sections:
            section.validate()
            if section.material not in self.materials:
                raise EngineeringError(f"Unknown material {section.material!r} in shaft section {section.section}.")
        length = self.total_length_mm

        def position_ok(position: float, label: str) -> None:
            if not isfinite(position) or position < -1e-9 or position > length + 1e-9:
                raise EngineeringError(f"{label} position {position:g} mm is outside the shaft [0, {length:g}] mm.")

        for index, bearing in enumerate(self.bearings, 1):
            position_ok(bearing.position_mm, f"Bearing #{index}")
            for point in bearing.coefficients:
                if point.rpm < 0:
                    raise EngineeringError(f"Bearing #{index} contains a negative speed point.")
        for index, mass in enumerate(self.distributed_masses, 1):
            position_ok(mass.start_mm, f"Distributed mass #{index}")
            position_ok(mass.end_mm, f"Distributed mass #{index} end")
            if mass.length_mm <= 0 or mass.mass_kg < 0:
                raise EngineeringError(f"Distributed mass #{index} must have positive length and non-negative mass.")
        for index, mass in enumerate(self.point_masses, 1):
            position_ok(mass.position_mm, f"Concentrated mass #{index}")
            if not all(isfinite(value) for value in (mass.mass_kg, mass.ix_kg_m2, mass.iy_kg_m2, mass.iz_kg_m2)):
                raise EngineeringError(f"Concentrated mass #{index} contains a non-finite mass/inertia value.")
            if mass.mass_kg < 0:
                raise EngineeringError(f"Concentrated mass #{index} cannot have negative mass.")
            if min(mass.ix_kg_m2, mass.iy_kg_m2, mass.iz_kg_m2) < 0:
                raise EngineeringError(f"Concentrated mass #{index}: Ix/Iy/Iz must be non-negative.")
        for index, disk in enumerate(self.disks, 1):
            position_ok(disk.position_mm, f"Disk #{index}")
            if min(disk.mass_kg, disk.id_kg_m2, disk.ip_kg_m2) < 0:
                raise EngineeringError(f"Disk #{index}: mass and inertias must be non-negative.")
        for support in self.supports:
            if not 0 <= support.bearing_index < len(self.bearings):
                raise EngineeringError(f"Support {support.name!r} references an invalid bearing index.")
            if support.mass_kg <= 0:
                raise EngineeringError(f"Support {support.name!r} must have positive mass.")

        foundation_supports: set[int] = set()
        for foundation in self.foundations:
            if not 0 <= foundation.support_index < len(self.supports):
                raise EngineeringError(f"Foundation {foundation.name!r} references an invalid support index.")
            if foundation.support_index in foundation_supports:
                raise EngineeringError(
                    f"Support #{foundation.support_index + 1} has more than one foundation; ownership must be one-to-one."
                )
            foundation.validate()
            foundation_supports.add(foundation.support_index)

        for seal in self.seals:
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
        for case in self.operating_cases:
            if case.speed_min_rpm < 0 or case.speed_max_rpm < case.speed_min_rpm:
                raise EngineeringError(f"Operating case {case.name!r} has an invalid speed range.")
        split = self.topology_split_positions_mm()
        if any(b <= a for a, b in zip(split, split[1:])):
            raise EngineeringError("Computed FE topology contains a zero/negative-length shaft interval.")
