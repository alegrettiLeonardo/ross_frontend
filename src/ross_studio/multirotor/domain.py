from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite

from ..domain import EngineeringError, RotorProject


class GearModel(StrEnum):
    SIMPLE = "GearElement"
    TVMS = "GearElementTVMS"


class MultiRotorMethodStatus(StrEnum):
    QUALIFIED = "QUALIFIED"
    EXPERIMENTAL = "EXPERIMENTAL"
    BLOCKED = "BLOCKED"


@dataclass(slots=True)
class GearSpec:
    """One physical gear attached to one strict ``RotorProject``.

    ``position_mm`` is resolved through the same exact-node policy used by the
    single-rotor builder; no nearest-node fallback is permitted.
    """

    name: str
    rotor_index: int
    position_mm: float
    model: GearModel = GearModel.SIMPLE
    n_teeth: int = 20
    pressure_angle_deg: float = 20.0
    helix_angle_deg: float = 0.0

    # GearElement mass/inertia realization
    mass_kg: float = 1.0
    id_kg_m2: float = 1e-3
    ip_kg_m2: float = 2e-3
    pitch_diameter_m: float | None = 0.1
    base_diameter_m: float | None = None

    # GearElementTVMS geometry realization
    material_name: str = "Steel"
    width_m: float = 0.02
    bore_diameter_m: float = 0.02
    module_m: float = 0.002
    addendum_coeff: float = 1.0
    tip_clearance_coeff: float = 0.25

    def validate(self, rotor_count: int) -> None:
        if not self.name.strip():
            raise EngineeringError("MultiRotor gear name cannot be empty.")
        if not 0 <= self.rotor_index < rotor_count:
            raise EngineeringError(
                f"Gear {self.name!r} references rotor {self.rotor_index}; "
                f"valid rotor indices are 0..{rotor_count - 1}."
            )
        if not isfinite(self.position_mm) or self.position_mm < 0:
            raise EngineeringError(f"Gear {self.name!r}: position must be finite and >= 0 mm.")
        if self.n_teeth < 1:
            raise EngineeringError(f"Gear {self.name!r}: n_teeth must be >= 1.")
        if not 0 < self.pressure_angle_deg < 90:
            raise EngineeringError(f"Gear {self.name!r}: pressure angle must be between 0 and 90 deg.")

        if self.model == GearModel.SIMPLE:
            if min(self.mass_kg, self.id_kg_m2, self.ip_kg_m2) < 0:
                raise EngineeringError(f"Gear {self.name!r}: mass and inertias must be non-negative.")
            if self.pitch_diameter_m is None and self.base_diameter_m is None:
                raise EngineeringError(
                    f"Gear {self.name!r}: GearElement requires pitch_diameter_m or base_diameter_m."
                )
            for label, value in (
                ("pitch diameter", self.pitch_diameter_m),
                ("base diameter", self.base_diameter_m),
            ):
                if value is not None and value <= 0:
                    raise EngineeringError(f"Gear {self.name!r}: {label} must be positive.")
        elif self.model == GearModel.TVMS:
            if min(self.width_m, self.bore_diameter_m, self.module_m) <= 0:
                raise EngineeringError(
                    f"Gear {self.name!r}: TVMS width, bore diameter and module must be positive."
                )
            if self.addendum_coeff <= 0 or self.tip_clearance_coeff < 0:
                raise EngineeringError(
                    f"Gear {self.name!r}: TVMS addendum coefficient must be positive and tip clearance non-negative."
                )
        else:  # pragma: no cover - enum guard
            raise EngineeringError(f"Unsupported gear model {self.model!r}.")


@dataclass(slots=True)
class GearConnection:
    """One ROSS ``MultiRotor`` coupling step.

    Connections are intentionally ordered. The first connection creates the
    aggregate; every later connection must attach one new driven rotor to a
    rotor already present in the aggregate. This matches ROSS' nested
    ``MultiRotor`` contract for systems with three or more shafts.
    """

    driving_rotor_index: int
    driven_rotor_index: int
    driving_gear_index: int
    driven_gear_index: int
    gear_mesh_stiffness: float | None = 1e8
    update_mesh_stiffness: bool = False
    square_varying_stiffness_enable: bool = False
    square_varying_stiffness_amplitude_ratio: float = 0.0
    backlash_enable: bool = False
    backlash_initial_value_m: float = 0.0
    backlash_error_amp_m: float = 0.0
    backlash_smooth_operator: bool = False
    backlash_sigma: float = 1e4
    orientation_angle_deg: float = 0.0
    position: str = "above"

    def validate(self, rotor_count: int, gear_count: int) -> None:
        for label, value in (
            ("driving_rotor_index", self.driving_rotor_index),
            ("driven_rotor_index", self.driven_rotor_index),
        ):
            if not 0 <= value < rotor_count:
                raise EngineeringError(f"MultiRotor {label}={value} is outside 0..{rotor_count - 1}.")
        if self.driving_rotor_index == self.driven_rotor_index:
            raise EngineeringError("A gear connection cannot drive and be driven by the same rotor.")
        for label, value in (
            ("driving_gear_index", self.driving_gear_index),
            ("driven_gear_index", self.driven_gear_index),
        ):
            if not 0 <= value < gear_count:
                raise EngineeringError(f"MultiRotor {label}={value} is outside 0..{gear_count - 1}.")
        if self.gear_mesh_stiffness is not None and self.gear_mesh_stiffness <= 0:
            raise EngineeringError("Gear mesh stiffness must be positive when supplied.")
        if self.position not in {"above", "below"}:
            raise EngineeringError("MultiRotor relative position must be 'above' or 'below'.")
        if self.square_varying_stiffness_amplitude_ratio < 0:
            raise EngineeringError("Square TVMS amplitude ratio cannot be negative.")
        if min(self.backlash_initial_value_m, self.backlash_error_amp_m, self.backlash_sigma) < 0:
            raise EngineeringError("Backlash values must be non-negative.")


@dataclass(slots=True)
class MultiRotorProject:
    name: str
    rotors: list[RotorProject] = field(default_factory=list)
    gears: list[GearSpec] = field(default_factory=list)
    connections: list[GearConnection] = field(default_factory=list)

    def validate(self) -> None:
        if not self.name.strip():
            raise EngineeringError("MultiRotor project name cannot be empty.")
        if len(self.rotors) < 2:
            raise EngineeringError("MultiRotor requires at least two RotorProject instances.")
        for rotor in self.rotors:
            rotor.validate()
        for gear in self.gears:
            gear.validate(len(self.rotors))
            if gear.position_mm > self.rotors[gear.rotor_index].total_length_mm + 1e-9:
                raise EngineeringError(
                    f"Gear {gear.name!r} at {gear.position_mm:g} mm lies outside rotor "
                    f"{gear.rotor_index} length {self.rotors[gear.rotor_index].total_length_mm:g} mm."
                )
        if len(self.connections) != len(self.rotors) - 1:
            raise EngineeringError(
                "A qualified chained MultiRotor project requires exactly N-1 gear connections."
            )

        attached = {self.connections[0].driving_rotor_index} if self.connections else set()
        used_driven: set[int] = set()
        for order, connection in enumerate(self.connections):
            connection.validate(len(self.rotors), len(self.gears))
            g_drive = self.gears[connection.driving_gear_index]
            g_driven = self.gears[connection.driven_gear_index]
            if g_drive.rotor_index != connection.driving_rotor_index:
                raise EngineeringError(
                    f"Connection {order}: driving gear belongs to rotor {g_drive.rotor_index}, "
                    f"not {connection.driving_rotor_index}."
                )
            if g_driven.rotor_index != connection.driven_rotor_index:
                raise EngineeringError(
                    f"Connection {order}: driven gear belongs to rotor {g_driven.rotor_index}, "
                    f"not {connection.driven_rotor_index}."
                )
            if order == 0:
                attached.add(connection.driven_rotor_index)
                used_driven.add(connection.driven_rotor_index)
                continue
            if connection.driving_rotor_index not in attached:
                raise EngineeringError(
                    f"Connection {order}: driving rotor {connection.driving_rotor_index} is not yet in the nested aggregate."
                )
            if connection.driven_rotor_index in attached or connection.driven_rotor_index in used_driven:
                raise EngineeringError(
                    f"Connection {order}: driven rotor {connection.driven_rotor_index} is already attached; cycles are not qualified."
                )
            attached.add(connection.driven_rotor_index)
            used_driven.add(connection.driven_rotor_index)
        if attached != set(range(len(self.rotors))):
            raise EngineeringError(
                f"MultiRotor connection chain does not include all rotors; attached={sorted(attached)}."
            )


METHOD_QUALIFICATION: dict[str, MultiRotorMethodStatus] = {
    "modal": MultiRotorMethodStatus.QUALIFIED,
    "campbell": MultiRotorMethodStatus.QUALIFIED,
    "frequency_response": MultiRotorMethodStatus.QUALIFIED,
    "unbalance_response": MultiRotorMethodStatus.QUALIFIED,
    "time_response": MultiRotorMethodStatus.QUALIFIED,
    "harmonic_balance": MultiRotorMethodStatus.QUALIFIED,
    "mesh_dynamics": MultiRotorMethodStatus.QUALIFIED,
    "critical_speed": MultiRotorMethodStatus.EXPERIMENTAL,
    "static": MultiRotorMethodStatus.BLOCKED,
    "ucs": MultiRotorMethodStatus.BLOCKED,
    "level1": MultiRotorMethodStatus.BLOCKED,
}


__all__ = [
    "GearConnection",
    "GearModel",
    "GearSpec",
    "METHOD_QUALIFICATION",
    "MultiRotorMethodStatus",
    "MultiRotorProject",
]
