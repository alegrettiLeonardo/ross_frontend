from __future__ import annotations

from dataclasses import dataclass
from math import pi
from typing import Any

import numpy as np

from .domain import EngineeringError, LateralConvention, RotorProject
from .ross_backend import RossBackend, RossBuildResult
from .ross_compat import RossCompatibilityNote, install_ross_compatibility
from .ross_conventions import rotordin_rotor_class
from .ump import assemble_ump, project_ump_specs, ump_rotor_class


@dataclass(slots=True, frozen=True)
class RossUnbalanceInput:
    """Raw engineering unbalance passed to the ROSS execution boundary."""

    node: int
    raw_magnitude: float
    source_unit: str
    phase_rad: float


@dataclass(slots=True, frozen=True)
class RossAppliedUnbalance:
    """Trace of the exact SI value delivered to ROSS."""

    node: int
    raw_magnitude: float
    source_unit: str
    magnitude_kg_m: float
    phase_rad: float


@dataclass(slots=True)
class RossUnbalanceRun:
    response: Any
    applied_inputs: tuple[RossAppliedUnbalance, ...]


class RossAnalysisBackend(RossBackend):
    """ROSS execution adapter that reuses one strict Rotor build across analyses.

    Engineering-domain values remain in their source units until this class crosses
    into the ROSS API. Legacy iRdin [Desbal] values are preserved as g*mm and
    converted to kg*m only immediately before the ROSS unbalance execution.

    Imported RotorDin projects carry an explicit positive-rotation convention.
    Linearized UMP is implemented as a separate electromagnetic negative-stiffness
    contribution and is composed with either native ROSS or RotorDin-positive
    rotation without modifying mass, damping, mechanical shaft stiffness or bearing
    coefficients.
    """

    def __init__(self, ross_module: Any | None = None) -> None:
        super().__init__(ross_module)
        self.compatibility_notes: tuple[RossCompatibilityNote, ...] = install_ross_compatibility(
            self.builder._ross()
        )

    def build_rotor(self, project: RotorProject, *, strict: bool = True) -> RossBuildResult:
        build = super().build_rotor(project, strict=strict)
        rs = self.builder._ross()

        if project.lateral_convention == LateralConvention.ROSS_NATIVE:
            rotor_cls = rs.Rotor
        elif project.lateral_convention == LateralConvention.ROTORDIN_POSITIVE:
            rotor_cls = rotordin_rotor_class(rs)
        else:
            raise EngineeringError(f"Unsupported lateral convention {project.lateral_convention!r}.")

        ump_specs = project_ump_specs(project)
        if ump_specs:
            rotor_cls = ump_rotor_class(rotor_cls)

        needs_rebuild = rotor_cls is not rs.Rotor
        if needs_rebuild:
            base = build.rotor
            build.rotor = rotor_cls(
                shaft_elements=list(base.shaft_elements),
                disk_elements=list(base.disk_elements) or None,
                bearing_elements=list(base.bearing_elements) or None,
                point_mass_elements=list(base.point_mass_elements) or None,
                tag=base.tag,
            )

        setattr(build.rotor, "lateral_convention", project.lateral_convention.value)

        if ump_specs:
            assembly = assemble_ump(project, build)
            build.rotor.set_ump_assembly(assembly)

        return build

    @staticmethod
    def run_static_build(build: RossBuildResult) -> Any:
        # ROSS run_static() creates auxiliary plain Rotor instances. UMP is an
        # energized dynamic negative stiffness and is therefore not included in
        # the gravity-only static solution, matching the RotorDin mkb policy.
        return build.rotor.run_static()

    @staticmethod
    def run_modal_build(build: RossBuildResult, speed_rpm: float, *, num_modes: int = 12) -> Any:
        speed = float(speed_rpm) * 2.0 * pi / 60.0
        return build.rotor.run_modal(speed=speed, num_modes=num_modes)

    @staticmethod
    def run_campbell_build(
        build: RossBuildResult,
        speeds_rpm: list[float],
        *,
        frequencies: int = 6,
    ) -> Any:
        speeds = np.asarray(speeds_rpm, dtype=float) * 2.0 * pi / 60.0
        return build.rotor.run_campbell(speed_range=speeds, frequencies=frequencies)

    @staticmethod
    def _normalize_unbalance_kg_m(magnitude: float, source_unit: str) -> float:
        unit = str(source_unit).replace(" ", "").lower()
        factors = {
            "kg*m": 1.0,
            "kg.m": 1.0,
            "kgm": 1.0,
            "kg*mm": 1e-3,
            "kg.mm": 1e-3,
            "g*mm": 1e-6,
            "g.mm": 1e-6,
        }
        if unit not in factors:
            raise EngineeringError(f"Unsupported unbalance unit {source_unit!r} at the ROSS boundary.")
        return float(magnitude) * factors[unit]

    @classmethod
    def run_unbalance_build(
        cls,
        build: RossBuildResult,
        inputs: list[RossUnbalanceInput],
        speeds_rpm: list[float],
    ) -> RossUnbalanceRun:
        if not inputs:
            raise EngineeringError("ROSS unbalance execution requires at least one input plane.")

        applied = tuple(
            RossAppliedUnbalance(
                node=int(item.node),
                raw_magnitude=float(item.raw_magnitude),
                source_unit=str(item.source_unit),
                magnitude_kg_m=cls._normalize_unbalance_kg_m(item.raw_magnitude, item.source_unit),
                phase_rad=float(item.phase_rad),
            )
            for item in inputs
        )
        frequency = np.asarray(speeds_rpm, dtype=float) * 2.0 * pi / 60.0
        response = build.rotor.run_unbalance_response(
            node=[item.node for item in applied],
            unbalance_magnitude=[item.magnitude_kg_m for item in applied],
            unbalance_phase=[item.phase_rad for item in applied],
            frequency=frequency,
        )
        return RossUnbalanceRun(response=response, applied_inputs=applied)


__all__ = [
    "RossAnalysisBackend",
    "RossAppliedUnbalance",
    "RossUnbalanceInput",
    "RossUnbalanceRun",
]
