from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite
from typing import Any

from .domain import EngineeringError, SealSpec


class SealModel(StrEnum):
    DIRECT = "DIRECT"
    LABYRINTH = "LABYRINTH"
    HOLE_PATTERN = "HOLE_PATTERN"
    HYBRID = "HYBRID"


@dataclass(slots=True, frozen=True)
class SealCoefficientPoint:
    rpm: float
    kxx: float
    kxy: float
    kyx: float
    kyy: float
    cxx: float
    cxy: float
    cyx: float
    cyy: float
    mxx: float = 0.0
    mxy: float = 0.0
    myx: float = 0.0
    myy: float = 0.0

    def validate(self, name: str) -> None:
        values = (
            self.rpm,
            self.kxx,
            self.kxy,
            self.kyx,
            self.kyy,
            self.cxx,
            self.cxy,
            self.cyx,
            self.cyy,
            self.mxx,
            self.mxy,
            self.myx,
            self.myy,
        )
        if not all(isfinite(float(value)) for value in values):
            raise EngineeringError(f"Seal {name!r} contains a non-finite calculated coefficient.")
        if self.rpm < 0.0:
            raise EngineeringError(f"Seal {name!r} contains a negative calculated speed {self.rpm:g} rpm.")


@dataclass(slots=True, frozen=True)
class HolePatternStageSpec:
    radial_clearance_m: float = 3.0e-4
    length_m: float = 4.0e-2
    roughness: float = 1.0e-4
    cell_length_m: float = 3.0e-3
    cell_width_m: float = 3.0e-3
    cell_depth_m: float = 2.0e-3
    preswirl: float = 0.8
    entr_coef: float = 0.5
    exit_coef: float = 1.0
    whirl_ratio: float = 1.0
    nz: int = 40
    max_iterations: int = 180
    tolerance: float = 1.0e-4
    first_step_size: float = 0.01
    rlx_factor: float = 0.1
    b_suther: float | None = None
    s_suther: float | None = None

    def validate(self, name: str) -> None:
        positive = (
            self.radial_clearance_m,
            self.length_m,
            self.cell_length_m,
            self.cell_width_m,
            self.cell_depth_m,
        )
        if not all(isfinite(value) and value > 0.0 for value in positive):
            raise EngineeringError(f"Seal {name!r} requires positive hole-pattern geometry.")
        if not isfinite(self.roughness) or self.roughness < 0.0:
            raise EngineeringError(f"Seal {name!r} hole-pattern roughness must be finite and non-negative.")
        if self.nz < 4 or self.max_iterations < 1:
            raise EngineeringError(f"Seal {name!r} requires nz >= 4 and max_iterations >= 1.")
        if self.tolerance <= 0.0 or self.first_step_size <= 0.0 or self.rlx_factor <= 0.0:
            raise EngineeringError(f"Seal {name!r} requires positive hole-pattern solver controls.")

    def ross_kwargs(self) -> dict[str, object]:
        values: dict[str, object] = {
            "radial_clearance": self.radial_clearance_m,
            "length": self.length_m,
            "roughness": self.roughness,
            "cell_length": self.cell_length_m,
            "cell_width": self.cell_width_m,
            "cell_depth": self.cell_depth_m,
            "preswirl": self.preswirl,
            "entr_coef": self.entr_coef,
            "exit_coef": self.exit_coef,
            "whirl_ratio": self.whirl_ratio,
            "nz": self.nz,
            "max_iterations": self.max_iterations,
            "tolerance": self.tolerance,
            "first_step_size": self.first_step_size,
            "rlx_factor": self.rlx_factor,
        }
        if self.b_suther is not None:
            values["b_suther"] = self.b_suther
        if self.s_suther is not None:
            values["s_suther"] = self.s_suther
        return values


@dataclass(slots=True, frozen=True)
class LabyrinthStageSpec:
    radial_clearance_m: float = 2.5e-4
    n_teeth: int = 10
    pitch_m: float = 3.0e-3
    tooth_height_m: float = 3.0e-3
    tooth_width_m: float = 1.5e-4
    seal_type: str = "inter"
    preswirl: float = 0.9
    tz_k: tuple[float, float] | None = None
    muz_pa_s: tuple[float, float] | None = None
    analz: str = "FULL"
    nprt: int = 1
    iopt1: int = 0

    def validate(self, name: str) -> None:
        positive = (self.radial_clearance_m, self.pitch_m, self.tooth_height_m, self.tooth_width_m)
        if not all(isfinite(value) and value > 0.0 for value in positive):
            raise EngineeringError(f"Seal {name!r} requires positive labyrinth geometry.")
        if not 1 <= self.n_teeth <= 30:
            raise EngineeringError(f"Seal {name!r} labyrinth tooth count must be inside [1, 30].")
        if self.seal_type not in {"rotor", "stator", "inter"}:
            raise EngineeringError(f"Seal {name!r} labyrinth seal_type must be rotor, stator or inter.")
        if self.analz not in {"FULL", "LEAKAGE"}:
            raise EngineeringError(f"Seal {name!r} labyrinth analz must be FULL or LEAKAGE.")

    def ross_kwargs(self) -> dict[str, object]:
        values: dict[str, object] = {
            "radial_clearance": self.radial_clearance_m,
            "n_teeth": self.n_teeth,
            "pitch": self.pitch_m,
            "tooth_height": self.tooth_height_m,
            "tooth_width": self.tooth_width_m,
            "seal_type": self.seal_type,
            "preswirl": self.preswirl,
            "analz": self.analz,
            "nprt": self.nprt,
            "iopt1": self.iopt1,
        }
        if self.tz_k is not None:
            values["tz"] = list(self.tz_k)
        if self.muz_pa_s is not None:
            values["muz"] = list(self.muz_pa_s)
        return values


def _validate_common_native(
    *,
    name: str,
    shaft_radius_m: float,
    inlet_pressure_pa: float,
    outlet_pressure_pa: float,
    inlet_temperature_k: float,
    frequency_rpm: list[float],
    gas_composition: dict[str, float],
    molar_kg_kmol: float | None,
    gamma: float | None,
) -> None:
    if not name.strip():
        raise EngineeringError("Seal name cannot be empty.")
    if not isfinite(shaft_radius_m) or shaft_radius_m <= 0.0:
        raise EngineeringError(f"Seal {name!r} shaft radius must be positive.")
    if not (isfinite(inlet_pressure_pa) and isfinite(outlet_pressure_pa)):
        raise EngineeringError(f"Seal {name!r} pressures must be finite.")
    if inlet_pressure_pa <= outlet_pressure_pa or outlet_pressure_pa <= 0.0:
        raise EngineeringError(f"Seal {name!r} requires inlet pressure > outlet pressure > 0.")
    if not isfinite(inlet_temperature_k) or inlet_temperature_k <= 0.0:
        raise EngineeringError(f"Seal {name!r} inlet temperature must be positive.")
    if not frequency_rpm:
        raise EngineeringError(f"Seal {name!r} requires at least one speed point.")
    previous = -1.0
    for rpm in frequency_rpm:
        if not isfinite(rpm) or rpm <= 0.0 or rpm <= previous:
            raise EngineeringError(
                f"Seal {name!r} speed points must be finite, positive and strictly increasing."
            )
        previous = rpm
    if gas_composition:
        if any((not isfinite(value) or value <= 0.0) for value in gas_composition.values()):
            raise EngineeringError(f"Seal {name!r} gas composition fractions must be positive and finite.")
        total = sum(gas_composition.values())
        if abs(total - 1.0) > 2.0e-2:
            raise EngineeringError(
                f"Seal {name!r} gas composition fractions must sum to approximately 1.0; received {total:.6g}."
            )
    elif molar_kg_kmol is None or gamma is None:
        raise EngineeringError(
            f"Seal {name!r} requires gas_composition or explicit molar_kg_kmol and gamma."
        )


def _validate_calculated(name: str, coefficients: list[SealCoefficientPoint]) -> None:
    if not coefficients:
        raise EngineeringError(
            f"Seal {name!r} has not been calculated. Use Seal Studio Calculate -> Preview -> Apply before strict rotor assembly."
        )
    previous = -1.0
    for point in coefficients:
        point.validate(name)
        if point.rpm <= previous:
            raise EngineeringError(f"Seal {name!r} calculated speeds must be strictly increasing.")
        previous = point.rpm


@dataclass(slots=True)
class LabyrinthSealSpec(SealSpec):
    model_type: str = field(default=SealModel.LABYRINTH.value, init=False)
    shaft_radius_m: float = 0.0725
    radial_clearance_m: float = 3.0e-4
    n_teeth: int = 16
    pitch_m: float = 3.175e-3
    tooth_height_m: float = 3.175e-3
    tooth_width_m: float = 1.524e-4
    seal_type: str = "inter"
    inlet_pressure_pa: float = 308_000.0
    outlet_pressure_pa: float = 94_300.0
    inlet_temperature_k: float = 283.15
    frequency_rpm: list[float] = field(default_factory=lambda: [5000.0])
    preswirl: float = 0.98
    gas_composition: dict[str, float] = field(default_factory=lambda: {"Nitrogen": 0.79, "Oxygen": 0.21})
    molar_kg_kmol: float | None = None
    gamma: float | None = None
    tz_k: tuple[float, float] | None = None
    muz_pa_s: tuple[float, float] | None = None
    analz: str = "FULL"
    nprt: int = 1
    iopt1: int = 0
    calculated_coefficients: list[SealCoefficientPoint] = field(default_factory=list)
    calculation: dict[str, Any] = field(default_factory=dict)

    def validate_inputs(self) -> None:
        _validate_common_native(
            name=self.name,
            shaft_radius_m=self.shaft_radius_m,
            inlet_pressure_pa=self.inlet_pressure_pa,
            outlet_pressure_pa=self.outlet_pressure_pa,
            inlet_temperature_k=self.inlet_temperature_k,
            frequency_rpm=self.frequency_rpm,
            gas_composition=self.gas_composition,
            molar_kg_kmol=self.molar_kg_kmol,
            gamma=self.gamma,
        )
        LabyrinthStageSpec(
            self.radial_clearance_m,
            self.n_teeth,
            self.pitch_m,
            self.tooth_height_m,
            self.tooth_width_m,
            self.seal_type,
            self.preswirl,
            self.tz_k,
            self.muz_pa_s,
            self.analz,
            self.nprt,
            self.iopt1,
        ).validate(self.name)

    def validate_calculated(self) -> None:
        self.validate_inputs()
        _validate_calculated(self.name, self.calculated_coefficients)


@dataclass(slots=True)
class HolePatternSealSpec(SealSpec):
    model_type: str = field(default=SealModel.HOLE_PATTERN.value, init=False)
    shaft_radius_m: float = 0.09825
    radial_clearance_m: float = 1.8e-4
    length_m: float = 8.49e-2
    roughness: float = 1.0e-4
    cell_length_m: float = 8.49e-2 / 37.0
    cell_width_m: float = 2.1e-3
    cell_depth_m: float = 2.8e-3
    inlet_pressure_pa: float = 1_830_000.0
    outlet_pressure_pa: float = 823_500.0
    inlet_temperature_k: float = 300.0
    frequency_rpm: list[float] = field(default_factory=lambda: [5000.0])
    gas_composition: dict[str, float] = field(
        default_factory=lambda: {"Nitrogen": 0.7812, "Oxygen": 0.2096, "Argon": 0.0092}
    )
    molar_kg_kmol: float | None = None
    gamma: float | None = None
    b_suther: float | None = None
    s_suther: float | None = None
    preswirl: float = 1.0
    entr_coef: float = 0.1
    exit_coef: float = 0.5
    whirl_ratio: float = 1.0
    nz: int = 40
    max_iterations: int = 180
    tolerance: float = 1.0e-4
    first_step_size: float = 0.01
    rlx_factor: float = 0.1
    calculated_coefficients: list[SealCoefficientPoint] = field(default_factory=list)
    calculation: dict[str, Any] = field(default_factory=dict)

    def stage(self) -> HolePatternStageSpec:
        return HolePatternStageSpec(
            radial_clearance_m=self.radial_clearance_m,
            length_m=self.length_m,
            roughness=self.roughness,
            cell_length_m=self.cell_length_m,
            cell_width_m=self.cell_width_m,
            cell_depth_m=self.cell_depth_m,
            preswirl=self.preswirl,
            entr_coef=self.entr_coef,
            exit_coef=self.exit_coef,
            whirl_ratio=self.whirl_ratio,
            nz=self.nz,
            max_iterations=self.max_iterations,
            tolerance=self.tolerance,
            first_step_size=self.first_step_size,
            rlx_factor=self.rlx_factor,
            b_suther=self.b_suther,
            s_suther=self.s_suther,
        )

    def validate_inputs(self) -> None:
        _validate_common_native(
            name=self.name,
            shaft_radius_m=self.shaft_radius_m,
            inlet_pressure_pa=self.inlet_pressure_pa,
            outlet_pressure_pa=self.outlet_pressure_pa,
            inlet_temperature_k=self.inlet_temperature_k,
            frequency_rpm=self.frequency_rpm,
            gas_composition=self.gas_composition,
            molar_kg_kmol=self.molar_kg_kmol,
            gamma=self.gamma,
        )
        self.stage().validate(self.name)

    def validate_calculated(self) -> None:
        self.validate_inputs()
        _validate_calculated(self.name, self.calculated_coefficients)


@dataclass(slots=True)
class HybridSealSpec(SealSpec):
    model_type: str = field(default=SealModel.HYBRID.value, init=False)
    shaft_radius_m: float = 0.025
    inlet_pressure_pa: float = 500_000.0
    outlet_pressure_pa: float = 100_000.0
    inlet_temperature_k: float = 300.0
    frequency_rpm: list[float] = field(default_factory=lambda: [2000.0])
    gas_composition: dict[str, float] = field(
        default_factory=lambda: {"Nitrogen": 0.7812, "Oxygen": 0.2096, "Argon": 0.0092}
    )
    molar_kg_kmol: float | None = None
    gamma: float | None = None
    hole_pattern: HolePatternStageSpec = field(default_factory=HolePatternStageSpec)
    labyrinth: LabyrinthStageSpec = field(default_factory=LabyrinthStageSpec)
    pressure_match_tolerance: float = 1.0e-6
    pressure_match_max_iterations: int = 100
    calculated_coefficients: list[SealCoefficientPoint] = field(default_factory=list)
    calculation: dict[str, Any] = field(default_factory=dict)

    def validate_inputs(self) -> None:
        _validate_common_native(
            name=self.name,
            shaft_radius_m=self.shaft_radius_m,
            inlet_pressure_pa=self.inlet_pressure_pa,
            outlet_pressure_pa=self.outlet_pressure_pa,
            inlet_temperature_k=self.inlet_temperature_k,
            frequency_rpm=self.frequency_rpm,
            gas_composition=self.gas_composition,
            molar_kg_kmol=self.molar_kg_kmol,
            gamma=self.gamma,
        )
        self.hole_pattern.validate(self.name)
        self.labyrinth.validate(self.name)
        if self.pressure_match_tolerance <= 0.0 or self.pressure_match_max_iterations < 1:
            raise EngineeringError(f"Seal {self.name!r} requires positive hybrid convergence controls.")

    def validate_calculated(self) -> None:
        self.validate_inputs()
        _validate_calculated(self.name, self.calculated_coefficients)


AdvancedSealSpec = LabyrinthSealSpec | HolePatternSealSpec | HybridSealSpec
DirectSealSpec = SealSpec


def is_advanced_seal(spec: SealSpec) -> bool:
    return isinstance(spec, (LabyrinthSealSpec, HolePatternSealSpec, HybridSealSpec))


def seal_model(spec: SealSpec) -> SealModel:
    value = getattr(spec, "model_type", SealModel.DIRECT.value)
    return SealModel(str(value))


__all__ = [
    "AdvancedSealSpec",
    "DirectSealSpec",
    "HolePatternSealSpec",
    "HolePatternStageSpec",
    "HybridSealSpec",
    "LabyrinthSealSpec",
    "LabyrinthStageSpec",
    "SealCoefficientPoint",
    "SealModel",
    "is_advanced_seal",
    "seal_model",
]
