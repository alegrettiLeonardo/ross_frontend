from __future__ import annotations

from dataclasses import dataclass
from math import pi
from typing import Any

import numpy as np

from .domain import EngineeringError, LateralConvention, RotorProject
from .ross_backend import RossBackend, RossBuildResult
from .ross_compat import RossCompatibilityNote, install_ross_compatibility
from .ross_conventions import rotordin_rotor_class


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

    Imported RotorDin projects also carry an explicit positive-rotation convention.
    For those projects the ROSS rotor is rebuilt from the same already-qualified
    elements using a thin subclass that changes only G sign and synchronous-force
    handedness. M, K, C, bearing cross coefficients and all physical properties are
    unchanged.
    """

    def __init__(self, ross_module: Any | None = None) -> None:
        super().__init__(ross_module)
        self.compatibility_notes: tuple[RossCompatibilityNote, ...] = install_ross_compatibility(
            self.builder._ross()
        )

    def build_rotor(self, project: RotorProject, *, strict: bool = True) -> RossBuildResult:
        build = super().build_rotor(project, strict=strict)
        if project.lateral_convention == LateralConvention.ROSS_NATIVE:
            setattr(build.rotor, "lateral_convention", LateralConvention.ROSS_NATIVE.value)
            return build
        if project.lateral_convention != LateralConvention.ROTORDIN_POSITIVE:
            raise EngineeringError(f"Unsupported lateral convention {project.lateral_convention!r}.")

        rs = self.builder._ross()
        rotor_cls = rotordin_rotor_class(rs)
        base = build.rotor
        build.rotor = rotor_cls(
            shaft_elements=list(base.shaft_elements),
            disk_elements=list(base.disk_elements) or None,
            bearing_elements=list(base.bearing_elements) or None,
            point_mass_elements=list(base.point_mass_elements) or None,
            tag=base.tag,
        )
        return build

    @staticmethod
    def run_static_build(build: RossBuildResult) -> Any:
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
