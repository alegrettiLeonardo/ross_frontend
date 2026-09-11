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
    """ROSS execution boundary for qualified analysis transactions.

    Engineering values stay in their source units until this class crosses into the
    ROSS API. ROSS 2.3.0 remains the scientific owner of every solver and result
    object. ROSS Studio only normalizes units, preserves exact-node traceability and
    retains the native result objects for plotting/export.
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
    def run_frequency_response_build(
        build: RossBuildResult,
        frequency_rad_s: list[float] | np.ndarray,
        *,
        modes: list[int] | tuple[int, ...] | None = None,
        free_free: bool = False,
    ) -> Any:
        frequency = np.asarray(frequency_rad_s, dtype=float)
        return build.rotor.run_freq_response(
            speed_range=frequency,
            modes=None if modes is None else list(modes),
            free_free=bool(free_free),
        )

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
    def normalize_unbalance_kg_m(cls, magnitude: float, source_unit: str) -> float:
        """Public unit-boundary helper reused by time/HBM/clearance transactions."""

        return cls._normalize_unbalance_kg_m(magnitude, source_unit)

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

    @staticmethod
    def run_time_response_build(
        build: RossBuildResult,
        speed_rad_s: float | np.ndarray,
        force_time: np.ndarray,
        time_s: np.ndarray,
        *,
        method: str = "default",
        **kwargs: Any,
    ) -> Any:
        return build.rotor.run_time_response(
            speed=speed_rad_s,
            F=np.asarray(force_time, dtype=float),
            t=np.asarray(time_s, dtype=float),
            method=str(method),
            **kwargs,
        )

    @staticmethod
    def run_harmonic_balance_build(
        build: RossBuildResult,
        *,
        speed_rad_s: float,
        time_s: np.ndarray,
        harmonic_forces: list[dict[str, Any]],
        gravity: bool = False,
        n_harmonics: int = 1,
    ) -> Any:
        return build.rotor.run_harmonic_balance_response(
            speed=float(speed_rad_s),
            t=np.asarray(time_s, dtype=float),
            harmonic_forces=harmonic_forces,
            gravity=bool(gravity),
            n_harmonics=int(n_harmonics),
        )

    @staticmethod
    def run_ucs_build(
        build: RossBuildResult,
        *,
        stiffness_range: tuple[float, float] | None = None,
        bearing_frequency_range: tuple[float, float] | None = None,
        num_modes: int = 16,
        num: int = 20,
        synchronous: bool = False,
    ) -> Any:
        return build.rotor.run_ucs(
            stiffness_range=stiffness_range,
            bearing_frequency_range=bearing_frequency_range,
            num_modes=int(num_modes),
            num=int(num),
            synchronous=bool(synchronous),
        )

    @staticmethod
    def run_clearance_build(
        build: RossBuildResult,
        *,
        speed_rad_s: float,
        nodes: list[int],
        magnitudes_kg_m: list[float],
        phases_rad: list[float],
        frequency_rad_s: np.ndarray | list[float] | None = None,
        modes: list[int] | tuple[int, ...] | None = None,
    ) -> Any:
        return build.rotor.run_clearance_analysis(
            speed=float(speed_rad_s),
            node=list(nodes),
            unbalance_magnitude=list(magnitudes_kg_m),
            unbalance_phase=list(phases_rad),
            frequency=None if frequency_rad_s is None else np.asarray(frequency_rad_s, dtype=float),
            modes=None if modes is None else list(modes),
        )


__all__ = [
    "RossAnalysisBackend",
    "RossAppliedUnbalance",
    "RossUnbalanceInput",
    "RossUnbalanceRun",
]
